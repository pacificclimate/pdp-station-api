"""pydap model and WSGI adapters."""

import copy
from html import escape
import re
from collections.abc import Callable, Iterator
from datetime import datetime
from time import perf_counter
from typing import Any

import numpy as np
from pydap.handlers.lib import BaseHandler, IterData
from pydap.model import BaseType, DatasetType, SequenceType
from webob import Request, Response

from .application import (
    StationDataset,
    StationDatasetService,
    StationNotFoundError,
)
from .responses import CSVResponse
from .urls import relative_app_root

OPENDAP_LOGO_URL = (
    "https://www.opendap.org/wp-content/uploads/2024/01/"
    "cropped-Group-1000001607-270x270.png"
)


class StationHandler(BaseHandler):
    """A pydap handler that preserves response settings when constrained."""

    def parse(self, projection, selection, buffer_size=None):
        if buffer_size is None:
            dataset = super().parse(projection, selection)
        else:
            dataset = super().parse(projection, selection, buffer_size)
        for name in ("_pcds_spool_max_size", "_pcds_xlsx_engine"):
            if hasattr(self.dataset, name):
                setattr(dataset, name, getattr(self.dataset, name))
        return dataset


class StationRows(IterData):
    """Re-iterable pydap data backed by a database-row factory."""

    def __init__(
        self,
        row_factory: Callable[[], Iterator[tuple[Any, ...]]],
        template: SequenceType,
        dtypes: dict[str, np.dtype],
        ifilter=None,
        imap=None,
        islice=None,
        level: int = 0,
    ):
        self.row_factory = row_factory
        self.template = template
        self.dtypes = dtypes
        self.level = level
        self.ifilter = ifilter or []
        self.imap = imap or []
        self.islice = islice or []
        self.normalization_seconds = 0.0

    @property
    def stream(self):
        for row in self.row_factory():
            started = perf_counter()
            try:
                values = tuple(row)
                if values and isinstance(values[0], datetime):
                    values = (values[0].isoformat(), *values[1:])
                values = tuple(np.nan if value is None else value for value in values)
            finally:
                self.normalization_seconds += perf_counter() - started
            yield values

    @property
    def dtype(self):
        if isinstance(self.template, SequenceType):
            return np.dtype(
                [(name, self.dtypes[name]) for name in self.template.keys()]
            )
        return self.dtypes[self.template.name]

    def __copy__(self):
        return type(self)(
            self.row_factory,
            copy.copy(self.template),
            self.dtypes,
            self.ifilter[:],
            self.imap[:],
            self.islice[:],
            self.level,
        )


def build_dataset(description: StationDataset, row_factory) -> DatasetType:
    dataset = DatasetType(f"station_{description.station_id}")
    dataset.attributes["NC_GLOBAL"] = dict(description.global_attributes)
    sequence = dataset["station_observations"] = SequenceType("station_observations")

    dtypes: dict[str, np.dtype] = {}
    for index, name in enumerate(description.columns):
        dtype = np.dtype("U") if index == 0 else np.dtype("float64")
        dtypes[name] = dtype
        attributes = (
            description.time_attributes
            if index == 0
            else description.variable_attributes.get(name, {})
        )
        sequence[name] = BaseType(name, dtype=dtype, attributes=dict(attributes))

    sequence.data = StationRows(row_factory, copy.copy(sequence), dtypes)
    return dataset


class StationDapApplication:
    """Resolve a station URL and delegate protocol output to pydap."""

    _numeric_path = re.compile(
        r"^/(?P<kind>stations|climatologies)/(?P<station_id>[1-9][0-9]*)"
        r"\.(?P<response>dds|das|dods|asc|ascii|html|ver|xlsx|nc|csv)$"
    )
    _public_path = re.compile(
        r"^/(?P<kind>raw|climo)/(?P<network>[^/]+)/(?P<native_id>[^/]+)"
        r"\.(?P<response>dds|das|dods|asc|ascii|html|ver|xlsx|nc|csv)$"
    )

    def __init__(
        self,
        service: StationDatasetService,
        mount_path: str = "",
        spool_max_size: int = 1 << 30,
        xlsx_engine: str = "xlsxwriter",
    ):
        self.service = service
        self.mount_path = mount_path.rstrip("/")
        self.spool_max_size = spool_max_size
        self.xlsx_engine = xlsx_engine

    def __call__(self, environ, start_response):
        request = Request(environ)
        path_info = request.path_info
        # WSGI servers should remove SCRIPT_NAME from PATH_INFO, but some ASGI
        # bridges retain the mount prefix. Accept both forms at this boundary.
        if self.mount_path and path_info.startswith(f"{self.mount_path}/"):
            path_info = path_info[len(self.mount_path) :]
        numeric_match = self._numeric_path.fullmatch(path_info)
        public_match = self._public_path.fullmatch(path_info)
        if numeric_match is None and public_match is None:
            return Response(status=404, text="DAP station dataset not found")(
                environ, start_response
            )

        try:
            if numeric_match is not None:
                description = self.service.station(
                    int(numeric_match.group("station_id")),
                    climatology=numeric_match.group("kind") == "climatologies",
                )
            else:
                description = self.service.public_station(
                    public_match.group("network"),
                    public_match.group("native_id"),
                    climatology=public_match.group("kind") == "climo",
                )
        except StationNotFoundError as exc:
            return Response(status=404, text=str(exc))(environ, start_response)

        dataset = build_dataset(
            description, lambda: self.service.repository.rows(description)
        )
        dataset._pcds_spool_max_size = self.spool_max_size
        dataset._pcds_xlsx_engine = self.xlsx_engine
        handler = StationHandler(dataset)
        handler.responses = {**handler.responses, "csv": CSVResponse}
        response = numeric_match or public_match
        if response.group("response") == "html":
            return self._relative_html(handler, request, environ, start_response)
        return handler(environ, start_response)

    @staticmethod
    def _relative_html(handler, request, environ, start_response):
        """Rewrite pydap's same-origin HTML URLs relative to the app root."""
        captured = {}
        written = []

        def capture_response(status, headers, exc_info=None):
            captured["status"] = status
            captured["headers"] = headers
            captured["exc_info"] = exc_info
            return written.append

        iterable = handler(environ, capture_response)
        try:
            body = b"".join((*written, *iterable))
        finally:
            close = getattr(iterable, "close", None)
            if close is not None:
                close()

        path = request.path_info
        script_name = request.script_name.rstrip("/")
        if script_name and not path.startswith(f"{script_name}/"):
            path = script_name + path
        root = relative_app_root(path).encode()
        origin = request.host_url.rstrip("/").encode()
        logo_sources = {
            origin + b"/static/logo.png",
            request.application_url.rstrip("/").encode() + b"/static/logo.png",
        }
        for logo_source in logo_sources:
            body = body.replace(logo_source, OPENDAP_LOGO_URL.encode())
        body = body.replace(origin + b"/", root).replace(origin, root)

        relative_page = root + path.lstrip("/").encode()
        body = body.replace(
            b'href="' + relative_page + b'/"',
            b'href="' + relative_page + b'"',
            1,
        )

        forwarded_prefix = request.headers.get("X-Forwarded-Prefix", "").rstrip("/")
        if not forwarded_prefix.startswith("/") or any(
            character in forwarded_prefix for character in '\r\n"<>'
        ):
            forwarded_prefix = ""
        relative_data_url = root + path.lstrip("/").removesuffix(".html").encode()
        public_data_url = escape(
            request.host_url.rstrip("/")
            + forwarded_prefix
            + path.removesuffix(".html"),
            quote=True,
        ).encode()
        body = body.replace(
            b'value="' + relative_data_url + b'"',
            b'value="' + public_data_url + b'"',
            1,
        )

        headers = []
        for name, value in captured["headers"]:
            if name.lower() == "content-length":
                value = str(len(body))
            elif name.lower() == "location":
                encoded = value.encode()
                value = (
                    encoded.replace(origin + b"/", root).replace(origin, root).decode()
                )
            headers.append((name, value))
        start_response(captured["status"], headers, captured["exc_info"])
        return [body]
