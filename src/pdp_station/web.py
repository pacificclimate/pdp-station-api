"""ASGI composition root."""

from html import escape
import json
import logging
from urllib.parse import quote
from urllib.parse import parse_qs

from starlette.applications import Starlette
from starlette.middleware.wsgi import WSGIMiddleware
from starlette.concurrency import run_in_threadpool
from starlette.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from starlette.routing import Mount, Route

from .application import StationDatasetService, StationNotFoundError
from .aggregate import (
    AggregateRequestError,
    parse_selection,
    prepare_archive,
    stream_archive,
)
from .config import Settings
from .dap import StationDapApplication
from .persistence import create_repository
from .urls import relative_app_root

logger = logging.getLogger(__name__)


def _readiness_endpoint(repository):
    def endpoint(request):
        verbose = "verbose" in request.query_params
        try:
            checks = repository.ready()
        except Exception:
            logger.exception("Readiness check failed: database unavailable")
            content = (
                "[-]database failed\nreadyz check failed\n" if verbose else "not ready"
            )
            return PlainTextResponse(content, status_code=503)
        ready = all(check.ready for check in checks)
        if not ready:
            logger.error("Readiness check failed: required database access unavailable")
        if verbose:
            lines = ["[+]database connection"]
            for check in checks:
                lines.extend(
                    (
                        f"[{'+' if check.exists else '-'}]{check.relation} existence",
                        f"[{'+' if check.schema_usage else '-'}]"
                        f"{check.relation} schema_usage",
                        f"[{'+' if check.select else '-'}]{check.relation} select",
                    )
                )
            lines.append(f"readyz check {'passed' if ready else 'failed'}")
            content = "\n".join(lines) + "\n"
        else:
            content = "ok" if ready else "not ready"
        return PlainTextResponse(content, status_code=200 if ready else 503)

    return endpoint


def _page(title: str, content: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
</head>
<body>
  <main>
    <h1>{escape(title)}</h1>
    {content}
  </main>
</body>
</html>
"""


def _network_index(service: StationDatasetService):
    def endpoint(request):
        root = relative_app_root(request.url.path)
        items = []
        for network in service.networks():
            label = network.display_name or network.name
            href = f"{root}networks/{quote(network.name, safe='')}"
            items.append(
                f'<li><a href="{href}">{escape(label)}</a> '
                f"<small>({escape(network.name)})</small></li>"
            )
        content = "<ul>" + "".join(items) + "</ul>"
        return HTMLResponse(_page("Station networks", content))

    return endpoint


def _station_index(service: StationDatasetService):
    def endpoint(request):
        root = relative_app_root(request.url.path)
        network_name = request.path_params["network"]
        try:
            network, stations = service.network_stations(network_name)
        except StationNotFoundError as exc:
            return HTMLResponse(
                _page("Network not found", f"<p>{escape(str(exc))}</p>"),
                status_code=404,
            )

        items = []
        for station in stations:
            href = (
                f"{root}dap/raw/{quote(network.name, safe='')}/"
                f"{quote(station.native_id, safe='')}.html"
            )
            station_name = (
                f" <small>{escape(station.name)}</small>" if station.name else ""
            )
            items.append(
                f'<li><a href="{href}">{escape(station.native_id)}</a>'
                f"{station_name}</li>"
            )
        title = network.display_name or network.name
        description = (
            f"<p>{escape(network.description)}</p>" if network.description else ""
        )
        content = (
            f'<p><a href="{root}">All networks</a></p>'
            + description
            + "<ul>"
            + "".join(items)
            + "</ul>"
        )
        return HTMLResponse(_page(title, content))

    return endpoint


def _network_catalog_redirect(request):
    return RedirectResponse(
        relative_app_root(request.url.path)
        + "networks/"
        + quote(request.path_params["network"], safe="")
    )


def _root_catalog_redirect(request):
    return RedirectResponse(relative_app_root(request.url.path))


async def _aggregate_parameters(request):
    if request.method == "GET":
        return dict(request.query_params)
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if not content_type:
        raise AggregateRequestError("QUERY and POST requests require Content-Type")
    if content_type == "application/json":
        try:
            value = await request.json()
        except json.JSONDecodeError as exc:
            raise AggregateRequestError("Request body is not valid JSON") from exc
        if not isinstance(value, dict):
            raise AggregateRequestError("JSON request body must be an object")
        return value
    if content_type == "application/x-www-form-urlencoded":
        body = (await request.body()).decode("utf-8")
        return {
            key: values if len(values) > 1 else values[0]
            for key, values in parse_qs(body, keep_blank_values=True).items()
        }
    raise AggregateRequestError(
        "Content-Type must be application/json or application/x-www-form-urlencoded"
    )


def _aggregate_endpoint(
    service: StationDatasetService,
    spool_max_size: int,
    max_stations: int,
    xlsx_engine: str,
):
    async def endpoint(request):
        headers = {
            "Accept-Query": "application/json, application/x-www-form-urlencoded"
        }
        if request.method == "OPTIONS":
            headers["Allow"] = "GET, POST, QUERY, OPTIONS"
            return Response(status_code=204, headers=headers)
        try:
            parameters = await _aggregate_parameters(request)
            selection = parse_selection(parameters)
            prepared = await run_in_threadpool(
                prepare_archive,
                service,
                selection,
                max_stations=max_stations,
            )
        except AggregateRequestError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422, headers=headers)
        headers["Content-Disposition"] = 'attachment; filename="pcds_data.zip"'
        return StreamingResponse(
            stream_archive(
                service,
                prepared,
                spool_max_size=spool_max_size,
                xlsx_engine=xlsx_engine,
            ),
            media_type="application/zip",
            headers=headers,
        )

    return endpoint


def create_app(settings: Settings | None = None, repository=None) -> Starlette:
    if repository is None:
        settings = settings or Settings.from_environment()
        repository = create_repository(
            settings.database_url,
            yield_per=settings.database_yield_per,
            explain_analyze_station_ids=settings.explain_analyze_station_ids,
        )
    service = StationDatasetService(repository)
    spool_max_size = settings.spool_max_size if settings is not None else 1 << 30
    aggregate_max_stations = (
        settings.aggregate_max_stations if settings is not None else 1_000
    )
    xlsx_engine = settings.xlsx_engine if settings is not None else "xlsxwriter"
    dap = StationDapApplication(
        service,
        mount_path="/dap",
        spool_max_size=spool_max_size,
        xlsx_engine=xlsx_engine,
    )
    return Starlette(
        routes=[
            Route("/readyz", _readiness_endpoint(repository), name="readiness"),
            Route("/", _network_index(service), name="networks"),
            Route(
                "/networks/{network}",
                _station_index(service),
                name="network-stations",
            ),
            Route(
                "/agg",
                _aggregate_endpoint(
                    service,
                    spool_max_size,
                    aggregate_max_stations,
                    xlsx_engine,
                ),
                methods=["GET", "POST", "QUERY", "OPTIONS"],
                name="aggregate-download",
            ),
            Route(
                "/agg/",
                _aggregate_endpoint(
                    service,
                    spool_max_size,
                    aggregate_max_stations,
                    xlsx_engine,
                ),
                methods=["GET", "POST", "QUERY", "OPTIONS"],
            ),
            # Pydap constructs breadcrumbs from every DAP path segment. These
            # intermediate URLs do not represent datasets, so route them to the
            # equivalent ASGI catalog pages instead of exposing dead links.
            Route("/dap", _root_catalog_redirect),
            Route("/dap/", _root_catalog_redirect),
            Route("/dap/raw", _root_catalog_redirect),
            Route("/dap/raw/", _root_catalog_redirect),
            Route("/dap/raw/{network}", _network_catalog_redirect),
            Route("/dap/raw/{network}/", _network_catalog_redirect),
            Route("/dap/climo", _root_catalog_redirect),
            Route("/dap/climo/", _root_catalog_redirect),
            Route("/dap/climo/{network}", _network_catalog_redirect),
            Route("/dap/climo/{network}/", _network_catalog_redirect),
            Route("/dap/stations", _root_catalog_redirect),
            Route("/dap/stations/", _root_catalog_redirect),
            Route("/dap/climatologies", _root_catalog_redirect),
            Route("/dap/climatologies/", _root_catalog_redirect),
            Mount("/dap", app=WSGIMiddleware(dap)),
        ]
    )
