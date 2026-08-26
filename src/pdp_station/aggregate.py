"""Aggregate station selection and ZIP download support."""

from collections import defaultdict
from collections.abc import Iterator, Mapping
import csv
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from hashlib import sha256
from io import StringIO
import json
import logging
from pathlib import PurePosixPath
from time import perf_counter
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from pydap.responses.ascii import ASCIIResponse
from shapely import from_wkt
from shapely.errors import GEOSException

from .application import (
    AggregateSelection,
    AggregateStation,
    StationDataset,
    StationDatasetService,
)
from .dap import build_dataset
from .responses import CSVResponse, NetCDFResponse, XLSXResponse

SUPPORTED_FORMATS = {
    "ascii": ("ascii", ASCIIResponse),
    "asc": ("ascii", ASCIIResponse),
    "csv": ("csv", CSVResponse),
    "nc": ("nc", NetCDFResponse),
    "xlsx": ("xlsx", XLSXResponse),
}

logger = logging.getLogger(__name__)


class AggregateRequestError(ValueError):
    """An aggregate request contains invalid or unsupported parameters."""


class TooManyStationsError(AggregateRequestError):
    """An aggregate selection exceeds the configured station limit."""


@dataclass(frozen=True)
class PreparedStation:
    station: AggregateStation
    description: StationDataset


@dataclass(frozen=True)
class PreparedAggregate:
    request_id: str
    selection: AggregateSelection
    stations: tuple[PreparedStation, ...]


@dataclass
class StationTiming:
    query_seconds: float = 0.0
    first_row_seconds: float = 0.0
    remaining_rows_seconds: float = 0.0
    serialization_seconds: float = 0.0
    xlsx_engine: str | None = None
    xlsx_metadata_seconds: float = 0.0
    xlsx_normalization_seconds: float = 0.0
    xlsx_write_seconds: float = 0.0
    xlsx_finalize_seconds: float = 0.0
    xlsx_copy_seconds: float = 0.0
    zip_seconds: float = 0.0
    rows: int = 0
    bytes: int = 0


class TimedRows:
    """Measure active time spent advancing a repository row iterator."""

    def __init__(self, factory, timing: StationTiming):
        self.factory = factory
        self.timing = timing

    def __iter__(self):
        rows = iter(self.factory())
        try:
            while True:
                started = perf_counter()
                try:
                    row = next(rows)
                except StopIteration:
                    self._record_fetch(perf_counter() - started)
                    return
                except Exception:
                    self._record_fetch(perf_counter() - started)
                    raise
                self._record_fetch(perf_counter() - started)
                self.timing.rows += 1
                yield row
        finally:
            close = getattr(rows, "close", None)
            if close is not None:
                close()

    def _record_fetch(self, elapsed: float) -> None:
        self.timing.query_seconds += elapsed
        if self.timing.rows == 0:
            self.timing.first_row_seconds += elapsed
        else:
            self.timing.remaining_rows_seconds += elapsed


class TimedZipMember:
    """Measure active time spent writing and finalizing one ZIP member."""

    def __init__(self, member, timing: StationTiming):
        self.member = member
        self.timing = timing

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def write(self, chunk):
        started = perf_counter()
        try:
            return self.member.write(chunk)
        finally:
            self.timing.zip_seconds += perf_counter() - started

    def close(self):
        started = perf_counter()
        try:
            self.member.close()
        finally:
            self.timing.zip_seconds += perf_counter() - started


def _first(values: Mapping[str, Any], *names: str, default=None):
    for name in names:
        value = values.get(name)
        if value not in (None, ""):
            return value
    return default


def _items(value: Any) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    source = value if isinstance(value, (list, tuple)) else str(value).split(",")
    return tuple(item.strip() for item in source if str(item).strip())


def _boolean(value: Any, *, present: bool = False) -> bool:
    if value is None:
        return present
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "only-with-climatology"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise AggregateRequestError(f"Invalid boolean value: {value}")


def _date(value: Any, name: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for pattern in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(value), pattern).date()
        except ValueError:
            pass
    raise AggregateRequestError(f"{name} must use YYYY-MM-DD or YYYY/MM/DD")


def parse_selection(values: Mapping[str, Any]) -> AggregateSelection:
    """Normalize the JSON and legacy form contracts into one selection."""
    data_format = str(_first(values, "format", "data-format", default="nc")).lower()
    if data_format not in SUPPORTED_FORMATS:
        supported = ", ".join(sorted(SUPPORTED_FORMATS))
        raise AggregateRequestError(f"format must be one of: {supported}")

    from_date = _date(_first(values, "from_date", "from-date"), "from_date")
    to_date = _date(_first(values, "to_date", "to-date"), "to_date")
    if from_date and to_date and from_date > to_date:
        raise AggregateRequestError("from_date must not be after to_date")

    climatology = _boolean(
        _first(values, "climatology"),
        present="download-climatology" in values,
    )
    clip_dates = _boolean(_first(values, "clip_dates"), present="cliptodate" in values)
    only_with_climatology = _boolean(
        _first(values, "only_with_climatology", "only-with-climatology"),
        present=False,
    )
    polygon = _first(values, "polygon", "input-polygon")
    if polygon:
        try:
            geometry = from_wkt(str(polygon))
        except GEOSException as exc:
            raise AggregateRequestError("polygon is not valid WKT") from exc
        if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise AggregateRequestError("polygon must be a Polygon or MultiPolygon")
        if geometry.is_empty or not geometry.is_valid:
            raise AggregateRequestError("polygon must be non-empty and valid")
        polygon = geometry.wkt

    return AggregateSelection(
        networks=_items(_first(values, "networks", "network-name")),
        variables=_items(_first(values, "variables", "input-vars", "input-var")),
        frequencies=_items(_first(values, "frequencies", "input-freq")),
        from_date=from_date,
        to_date=to_date,
        polygon=polygon,
        only_with_climatology=only_with_climatology,
        climatology=climatology,
        clip_dates=clip_dates,
        data_format=data_format,
    )


def request_fingerprint(selection: AggregateSelection) -> str:
    """Return a compact hash of a normalized aggregate request."""
    payload = json.dumps(
        asdict(selection),
        default=lambda value: value.isoformat(),
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(payload).hexdigest()[:16]


def _archive_component(value: str) -> str:
    component = value.replace("/", "_").replace("\\", "_").strip()
    if component in {"", ".", ".."}:
        raise AggregateRequestError("Station identifiers cannot form empty paths")
    return component


def _variable_index(descriptions) -> bytes:
    rows = {}
    for description in descriptions:
        for name, attributes in description.variable_attributes.items():
            rows[name] = (
                name,
                attributes.get("standard_name", ""),
                attributes.get("cell_methods", attributes.get("cell_method", "")),
                attributes.get("units", ""),
            )
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("variable", "standard_name", "cell_method", "unit"))
    writer.writerows(rows[name] for name in sorted(rows))
    return output.getvalue().encode("utf-8")


def prepare_archive(
    service: StationDatasetService,
    selection: AggregateSelection,
    *,
    max_stations: int,
) -> PreparedAggregate:
    """Resolve and describe stations without querying observation rows."""
    request_id = request_fingerprint(selection)
    extra = {"aggregate_request_id": request_id}
    logger.debug(
        "Aggregate request %s preflight started format=%s",
        request_id,
        selection.data_format,
        extra=extra,
    )
    try:
        selection_started = perf_counter()
        stations = service.repository.aggregate_stations(selection)
        selection_seconds = perf_counter() - selection_started
        logger.debug(
            "Aggregate request %s selected %d stations",
            request_id,
            len(stations),
            extra=extra,
        )
        if len(stations) > max_stations:
            raise TooManyStationsError(
                f"Selection contains {len(stations)} stations; limit is {max_stations}"
            )

        prepared = []
        metadata_seconds = 0.0
        for station in stations:
            station_extra = {
                **extra,
                "station_id": station.station_id,
                "station_network": station.network,
                "station_native_id": station.native_id,
            }
            logger.debug(
                "Aggregate request %s preflighting station %s/%s (%d)",
                request_id,
                station.network,
                station.native_id,
                station.station_id,
                extra=station_extra,
            )
            metadata_started = perf_counter()
            try:
                description = service.station(
                    station.station_id, climatology=selection.climatology
                )
            finally:
                metadata_seconds += perf_counter() - metadata_started
            if selection.clip_dates:
                description = replace(
                    description,
                    from_date=selection.from_date,
                    to_date=selection.to_date,
                )
            prepared.append(PreparedStation(station, description))
    except AggregateRequestError:
        logger.warning(
            "Aggregate request %s rejected during preflight",
            request_id,
            extra=extra,
            exc_info=True,
        )
        raise
    except Exception:
        logger.exception(
            "Aggregate request %s failed during preflight",
            request_id,
            extra=extra,
        )
        raise
    logger.debug(
        "Aggregate request %s preflight timing selection=%.6fs "
        "metadata=%.6fs stations=%d",
        request_id,
        selection_seconds,
        metadata_seconds,
        len(prepared),
        extra={
            **extra,
            "aggregate_selection_seconds": selection_seconds,
            "aggregate_metadata_seconds": metadata_seconds,
            "aggregate_station_count": len(prepared),
        },
    )
    return PreparedAggregate(request_id, selection, tuple(prepared))


class StreamingZipBuffer:
    """A non-seekable ZIP sink whose writes can be drained incrementally."""

    def __init__(self):
        # The response emits the first two signature bytes before ZipFile runs.
        # ZipFile must still see the logical archive as starting at offset zero.
        self.position = 0
        self._prefix_pending = True
        self._chunks: list[bytes] = []

    def write(self, value):
        value = bytes(value)
        original_length = len(value)
        if self._prefix_pending and value:
            if not value.startswith(b"PK"):
                raise RuntimeError("ZIP output did not start with a PK signature")
            value = value[2:]
            self._prefix_pending = False
        self.position += original_length
        if value:
            self._chunks.append(value)
        return original_length

    def tell(self):
        return self.position

    def seek(self, *args):
        raise OSError("streaming ZIP output is not seekable")

    def flush(self):
        pass

    def drain(self) -> Iterator[bytes]:
        chunks, self._chunks = self._chunks, []
        yield from chunks


def stream_archive(
    service: StationDatasetService,
    prepared: PreparedAggregate,
    *,
    spool_max_size: int,
    xlsx_engine: str = "xlsxwriter",
) -> Iterator[bytes]:
    """Stream a valid ZIP, querying observation rows only after its signature."""
    request_id = prepared.request_id
    extra = {"aggregate_request_id": request_id}
    current_station = None
    logger.debug(
        "Aggregate request %s response generation started",
        request_id,
        extra=extra,
    )
    try:
        yield b"PK"

        extension, response_type = SUPPORTED_FORMATS[prepared.selection.data_format]
        output = StreamingZipBuffer()
        descriptions_by_network = defaultdict(list)
        with ZipFile(output, "w", ZIP_DEFLATED, allowZip64=True) as archive:
            for item in prepared.stations:
                current_station = item.station
                station = item.station
                description = item.description
                station_extra = {
                    **extra,
                    "station_id": station.station_id,
                    "station_network": station.network,
                    "station_native_id": station.native_id,
                }
                logger.debug(
                    "Aggregate request %s retrieving station %s/%s (%d)",
                    request_id,
                    station.network,
                    station.native_id,
                    station.station_id,
                    extra=station_extra,
                )
                descriptions_by_network[station.network].append(description)
                network = _archive_component(station.network)
                native_id = _archive_component(station.native_id)
                filename = str(PurePosixPath(network, f"{native_id}.{extension}"))
                timing = StationTiming()
                try:
                    with TimedZipMember(
                        archive.open(filename, "w", force_zip64=True), timing
                    ) as member:
                        yield from output.drain()
                        timed_rows = TimedRows(
                            lambda description=description: service.repository.rows(
                                description
                            ),
                            timing,
                        )
                        dataset = build_dataset(description, lambda: iter(timed_rows))
                        dataset._pcds_spool_max_size = spool_max_size
                        dataset._pcds_xlsx_engine = xlsx_engine
                        response_seconds = 0.0
                        response_object = response_type(dataset)
                        response = None
                        try:
                            response_started = perf_counter()
                            try:
                                response = iter(response_object)
                            finally:
                                response_seconds += perf_counter() - response_started
                            while True:
                                response_started = perf_counter()
                                try:
                                    chunk = next(response)
                                except StopIteration:
                                    response_seconds += (
                                        perf_counter() - response_started
                                    )
                                    break
                                except Exception:
                                    response_seconds += (
                                        perf_counter() - response_started
                                    )
                                    raise
                                response_seconds += perf_counter() - response_started
                                timing.bytes += len(chunk)
                                member.write(chunk)
                                yield from output.drain()
                        finally:
                            close = getattr(response, "close", None)
                            if close is not None:
                                close()
                            timing.serialization_seconds = max(
                                0.0, response_seconds - timing.query_seconds
                            )
                            xlsx_timing = getattr(response_object, "timing", None)
                            if xlsx_timing is not None:
                                timing.xlsx_engine = xlsx_timing.engine
                                timing.xlsx_metadata_seconds = (
                                    xlsx_timing.metadata_seconds
                                )
                                timing.xlsx_normalization_seconds = (
                                    xlsx_timing.normalization_seconds
                                )
                                timing.xlsx_write_seconds = max(
                                    0.0,
                                    xlsx_timing.data_seconds
                                    - timing.query_seconds
                                    - timing.xlsx_normalization_seconds,
                                )
                                timing.xlsx_finalize_seconds = (
                                    xlsx_timing.finalize_seconds
                                )
                                timing.xlsx_copy_seconds = max(
                                    0.0,
                                    timing.serialization_seconds
                                    - timing.xlsx_metadata_seconds
                                    - timing.xlsx_normalization_seconds
                                    - timing.xlsx_write_seconds
                                    - timing.xlsx_finalize_seconds,
                                )
                    yield from output.drain()
                finally:
                    logger.debug(
                        "Aggregate request %s station %s/%s (%d) timing "
                        "query=%.6fs first_row=%.6fs remaining_rows=%.6fs "
                        "serialization=%.6fs zip=%.6fs rows=%d bytes=%d",
                        request_id,
                        station.network,
                        station.native_id,
                        station.station_id,
                        timing.query_seconds,
                        timing.first_row_seconds,
                        timing.remaining_rows_seconds,
                        timing.serialization_seconds,
                        timing.zip_seconds,
                        timing.rows,
                        timing.bytes,
                        extra={
                            **station_extra,
                            "aggregate_query_seconds": timing.query_seconds,
                            "aggregate_first_row_seconds": (timing.first_row_seconds),
                            "aggregate_remaining_rows_seconds": (
                                timing.remaining_rows_seconds
                            ),
                            "aggregate_serialization_seconds": (
                                timing.serialization_seconds
                            ),
                            "aggregate_zip_seconds": timing.zip_seconds,
                            "aggregate_row_count": timing.rows,
                            "aggregate_uncompressed_bytes": timing.bytes,
                        },
                    )
                    if timing.xlsx_engine is not None:
                        logger.debug(
                            "Aggregate request %s station %s/%s (%d) XLSX timing "
                            "engine=%s metadata=%.6fs normalization=%.6fs write=%.6fs "
                            "finalize=%.6fs copy=%.6fs",
                            request_id,
                            station.network,
                            station.native_id,
                            station.station_id,
                            timing.xlsx_engine,
                            timing.xlsx_metadata_seconds,
                            timing.xlsx_normalization_seconds,
                            timing.xlsx_write_seconds,
                            timing.xlsx_finalize_seconds,
                            timing.xlsx_copy_seconds,
                            extra={
                                **station_extra,
                                "aggregate_xlsx_engine": timing.xlsx_engine,
                                "aggregate_xlsx_metadata_seconds": (
                                    timing.xlsx_metadata_seconds
                                ),
                                "aggregate_xlsx_normalization_seconds": (
                                    timing.xlsx_normalization_seconds
                                ),
                                "aggregate_xlsx_write_seconds": (
                                    timing.xlsx_write_seconds
                                ),
                                "aggregate_xlsx_finalize_seconds": (
                                    timing.xlsx_finalize_seconds
                                ),
                                "aggregate_xlsx_copy_seconds": (
                                    timing.xlsx_copy_seconds
                                ),
                            },
                        )
                logger.debug(
                    "Aggregate request %s completed station %s/%s (%d)",
                    request_id,
                    station.network,
                    station.native_id,
                    station.station_id,
                    extra=station_extra,
                )
                current_station = None

            for network, descriptions in descriptions_by_network.items():
                filename = str(
                    PurePosixPath(_archive_component(network), "variables.csv")
                )
                with archive.open(filename, "w") as member:
                    yield from output.drain()
                    member.write(_variable_index(descriptions))
                    yield from output.drain()
                yield from output.drain()
        yield from output.drain()
    except Exception:
        if current_station is None:
            logger.exception(
                "Aggregate request %s response generation failed",
                request_id,
                extra=extra,
            )
        else:
            logger.exception(
                "Aggregate request %s failed while retrieving station %s/%s (%d)",
                request_id,
                current_station.network,
                current_station.native_id,
                current_station.station_id,
                extra={
                    **extra,
                    "station_id": current_station.station_id,
                    "station_network": current_station.network,
                    "station_native_id": current_station.native_id,
                },
            )
        raise
    logger.debug(
        "Aggregate request %s response generation completed",
        request_id,
        extra=extra,
    )
