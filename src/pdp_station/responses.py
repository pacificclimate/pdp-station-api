"""Download responses for station datasets."""

from collections.abc import Iterator, Mapping
import csv
from dataclasses import dataclass
from io import StringIO
from itertools import chain
import math
from tempfile import SpooledTemporaryFile
from time import perf_counter
from typing import Any, BinaryIO

import h5netcdf
import h5py
import numpy as np
from pydap.lib import walk
from pydap.model import SequenceType
from pydap.responses.lib import BaseResponse
from rustpy_xlsxwriter import FastExcel, Format
from xlsxwriter import Workbook

DEFAULT_SPOOL_MAX_SIZE = 1 << 30
COPY_CHUNK_SIZE = 1024 * 1024
CSV_CHUNK_SIZE = 1024 * 1024
EXCEL_MAX_DATA_ROWS = 1_048_575
NETCDF_BATCH_SIZE = 10_000


@dataclass
class XLSXTiming:
    """Active time spent assembling each part of an XLSX response."""

    engine: str = "xlsxwriter"
    metadata_seconds: float = 0.0
    data_seconds: float = 0.0
    normalization_seconds: float = 0.0
    finalize_seconds: float = 0.0


def _spool(dataset) -> BinaryIO:
    max_size = getattr(dataset, "_pcds_spool_max_size", DEFAULT_SPOOL_MAX_SIZE)
    stream = SpooledTemporaryFile(
        max_size=max_size,
        mode="w+b",
    )
    if max_size == 0:
        stream.rollover()
    return stream


def _chunks(stream: BinaryIO) -> Iterator[bytes]:
    try:
        stream.seek(0)
        while chunk := stream.read(COPY_CHUNK_SIZE):
            yield chunk
    finally:
        stream.close()


def _sequences(dataset) -> list[SequenceType]:
    return list(walk(dataset, SequenceType))


def _attribute_rows(
    attributes: Mapping[str, Any], prefix: str = ""
) -> Iterator[tuple[str, Any]]:
    for name, value in attributes.items():
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(value, Mapping):
            yield from _attribute_rows(value, path)
        else:
            yield path, value


def _scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def _excel_value(value: Any) -> Any:
    value = _scalar(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (list, tuple)):
        return ", ".join(map(str, value))
    return value


def _csv_value(value: Any) -> Any:
    value = _scalar(value)
    if value is None or (
        isinstance(value, (float, np.floating)) and not math.isfinite(value)
    ):
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(map(str, value))
    return value


class CSVResponse(BaseResponse):
    """Render one sequence as buffered, standards-compliant CSV."""

    __description__ = "CSV"

    def __init__(self, dataset):
        super().__init__(dataset)
        self.headers.extend(
            [
                ("Content-Type", "text/csv; charset=utf-8"),
                (
                    "Content-Disposition",
                    f'attachment; filename="{dataset.name}.csv"',
                ),
            ]
        )

    def __iter__(self):
        sequences = _sequences(self.dataset)
        if len(sequences) != 1:
            raise ValueError("CSV downloads require exactly one sequence")
        sequence = sequences[0]
        output = StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n")
        writer.writerow(sequence.keys())

        for row in sequence.iterdata():
            writer.writerow(_csv_value(value) for value in row)
            if output.tell() >= CSV_CHUNK_SIZE:
                yield output.getvalue().encode("utf-8")
                output.seek(0)
                output.truncate(0)

        if output.tell():
            yield output.getvalue().encode("utf-8")


class XLSXResponse(BaseResponse):
    """Render sequence data and metadata as an Excel workbook."""

    __description__ = "Excel workbook"

    def __init__(self, dataset):
        super().__init__(dataset)
        self.timing = XLSXTiming()
        self.headers.extend(
            [
                (
                    "Content-Type",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                (
                    "Content-Disposition",
                    f'attachment; filename="{dataset.name}.xlsx"',
                ),
            ]
        )

    def __iter__(self):
        engine = getattr(self.dataset, "_pcds_xlsx_engine", "xlsxwriter")
        if engine == "rustpy":
            return self._iter_rustpy()
        return self._iter_xlsxwriter()

    def _iter_xlsxwriter(self):
        output = _spool(self.dataset)
        workbook = Workbook(
            output,
            {
                "constant_memory": True,
                "strings_to_formulas": False,
                "strings_to_urls": False,
            },
        )
        header = workbook.add_format(
            {"bold": True, "font_color": "white", "bg_color": "#4F81BD"}
        )

        started = perf_counter()
        global_sheet = workbook.add_worksheet("Global attributes")
        global_sheet.write_row(0, 0, ("Attribute", "Value"), header)
        global_attributes = self.dataset.attributes.get(
            "NC_GLOBAL", self.dataset.attributes
        )
        for row_number, (name, value) in enumerate(
            _attribute_rows(global_attributes), start=1
        ):
            global_sheet.write_row(row_number, 0, (name, _excel_value(value)))

        variable_sheet = workbook.add_worksheet("Variable attributes")
        variable_sheet.write_row(0, 0, ("Variable", "Attribute", "Value"), header)
        attribute_row = 1
        sequences = _sequences(self.dataset)
        for sequence in sequences:
            for variable in sequence.children():
                for name, value in _attribute_rows(variable.attributes):
                    variable_sheet.write_row(
                        attribute_row,
                        0,
                        (variable.name, name, _excel_value(value)),
                    )
                    attribute_row += 1
        self.timing.metadata_seconds = perf_counter() - started

        started = perf_counter()
        for sequence in sequences:
            sheet = workbook.add_worksheet(sequence.name[:31])
            sheet.write_row(0, 0, list(sequence.keys()), header)
            for row_number, row in enumerate(sequence.iterdata(), start=1):
                if row_number > EXCEL_MAX_DATA_ROWS:
                    workbook.close()
                    output.close()
                    raise ValueError(
                        "Excel downloads cannot exceed 1,048,575 observations"
                    )
                sheet.write_string(row_number, 0, str(row[0]))
                for column_number, value in enumerate(row[1:], start=1):
                    value = _scalar(value)
                    if value is None or (
                        isinstance(value, (float, np.floating))
                        and not math.isfinite(value)
                    ):
                        continue
                    sheet.write_number(row_number, column_number, value)
        self.timing.data_seconds = perf_counter() - started
        self.timing.normalization_seconds = sum(
            getattr(sequence.data, "normalization_seconds", 0.0)
            for sequence in sequences
        )

        started = perf_counter()
        workbook.close()
        self.timing.finalize_seconds = perf_counter() - started
        return _chunks(output)

    def _iter_rustpy(self):
        self.timing.engine = "rustpy"
        output = _spool(self.dataset)
        sequences = _sequences(self.dataset)
        started = perf_counter()
        prepared_sequences = []
        for sequence in sequences:
            rows = iter(sequence.iterdata())
            try:
                first = next(rows)
            except StopIteration:
                output.close()
                self.timing.engine = "xlsxwriter-fallback-empty"
                return self._iter_xlsxwriter()
            prepared_sequences.append((sequence, chain((first,), rows)))
        header = (
            Format().set_bold().set_font_color("white").set_background_color("#4F81BD")
        )

        global_attributes = self.dataset.attributes.get(
            "NC_GLOBAL", self.dataset.attributes
        )
        global_rows = (
            {"Attribute": name, "Value": _excel_value(value)}
            for name, value in _attribute_rows(global_attributes)
        )

        def variable_rows():
            for sequence in sequences:
                for variable in sequence.children():
                    for name, value in _attribute_rows(variable.attributes):
                        yield {
                            "Variable": variable.name,
                            "Attribute": name,
                            "Value": _excel_value(value),
                        }

        writer = FastExcel(output, autofit=False)
        writer.sheet("Global attributes", global_rows, header_format=header).sheet(
            "Variable attributes", variable_rows(), header_format=header
        )

        for sequence, rows in prepared_sequences:
            columns = tuple(sequence.keys())

            def observation_rows(rows=rows, columns=columns):
                for row_number, row in enumerate(rows, start=1):
                    if row_number > EXCEL_MAX_DATA_ROWS:
                        raise ValueError(
                            "Excel downloads cannot exceed 1,048,575 observations"
                        )
                    yield {
                        name: _excel_value(value)
                        for name, value in zip(columns, row, strict=True)
                    }

            writer.sheet(sequence.name[:31], observation_rows(), header_format=header)

        writer.save()
        self.timing.data_seconds = perf_counter() - started
        self.timing.normalization_seconds = sum(
            getattr(sequence.data, "normalization_seconds", 0.0)
            for sequence in sequences
        )
        return _chunks(output)


def _netcdf_attribute(value: Any) -> Any:
    value = _scalar(value)
    if value is None:
        return ""
    if isinstance(value, (str, bytes, int, float, np.number, np.ndarray)):
        return value
    if isinstance(value, (list, tuple)):
        return np.asarray(value) if value else ""
    return str(value)


class NetCDFResponse(BaseResponse):
    """Render sequence data as an unlimited-dimension NetCDF4 file."""

    __description__ = "NetCDF4 file"

    def __init__(self, dataset):
        super().__init__(dataset)
        self.headers.extend(
            [
                ("Content-Type", "application/x-netcdf"),
                (
                    "Content-Disposition",
                    f'attachment; filename="{dataset.name}.nc"',
                ),
            ]
        )

    def __iter__(self):
        output = _spool(self.dataset)
        with h5netcdf.File(output, "w") as target:
            global_attributes = self.dataset.attributes.get(
                "NC_GLOBAL", self.dataset.attributes
            )
            for name, value in _attribute_rows(global_attributes):
                target.attrs[name] = _netcdf_attribute(value)

            sequences = _sequences(self.dataset)
            if len(sequences) != 1:
                raise ValueError("NetCDF downloads require exactly one sequence")
            sequence = sequences[0]
            target.dimensions["obs"] = None

            variables = {}
            for variable in sequence.children():
                dtype = (
                    h5py.string_dtype(encoding="utf-8")
                    if variable.dtype.kind in "OUS"
                    else variable.dtype
                )
                output_variable = target.create_variable(
                    variable.name, ("obs",), dtype=dtype
                )
                for name, value in _attribute_rows(variable.attributes):
                    output_variable.attrs[name] = _netcdf_attribute(value)
                variables[variable.name] = output_variable

            start = 0
            batch = []
            for row in sequence.iterdata():
                batch.append(tuple(row))
                if len(batch) == NETCDF_BATCH_SIZE:
                    start = self._write_batch(target, variables, batch, start)
                    batch.clear()
            if batch:
                self._write_batch(target, variables, batch, start)

        return _chunks(output)

    @staticmethod
    def _write_batch(target, variables, rows, start):
        stop = start + len(rows)
        target.resize_dimension("obs", stop)
        for index, variable in enumerate(variables.values()):
            values = [row[index] for row in rows]
            variable[start:stop] = values
        return stop
