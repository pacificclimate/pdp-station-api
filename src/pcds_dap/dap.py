"""pydap model and WSGI adapters."""

import copy
import re
from collections.abc import Callable, Iterator
from typing import Any

import numpy as np
from pydap.handlers.lib import BaseHandler, IterData
from pydap.model import BaseType, DatasetType, SequenceType
from webob import Request, Response

from .application import StationDataset, StationDatasetService


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

    @property
    def stream(self):
        for row in self.row_factory():
            values = tuple(row)
            # DAP2 has no datetime scalar, so expose ISO-8601 text.
            if values and hasattr(values[0], "isoformat"):
                values = (values[0].isoformat(), *values[1:])
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
    dataset.attributes["station_id"] = description.station_id
    dataset.attributes["climatology"] = description.climatology
    sequence = dataset["station_observations"] = SequenceType("station_observations")

    dtypes: dict[str, np.dtype] = {}
    for index, name in enumerate(description.columns):
        dtype = np.dtype("U") if index == 0 else np.dtype("float64")
        dtypes[name] = dtype
        sequence[name] = BaseType(name, dtype=dtype)

    sequence.data = StationRows(row_factory, copy.copy(sequence), dtypes)
    return dataset


class StationDapApplication:
    """Resolve a station URL and delegate protocol output to pydap."""

    _path = re.compile(
        r"^/(?P<kind>stations|climatologies)/(?P<station_id>[1-9][0-9]*)"
        r"\.(?P<response>dds|das|dods|asc|ascii|html|ver)$"
    )

    def __init__(self, service: StationDatasetService):
        self.service = service

    def __call__(self, environ, start_response):
        request = Request(environ)
        match = self._path.fullmatch(request.path_info)
        if match is None:
            return Response(status=404, text="DAP station dataset not found")(
                environ, start_response
            )

        station_id = int(match.group("station_id"))
        climatology = match.group("kind") == "climatologies"
        query = self.service.station(station_id, climatology=climatology)
        dataset = build_dataset(query, lambda: self.service.repository.rows(query))
        return BaseHandler(dataset)(environ, start_response)
