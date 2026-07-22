"""ASGI composition root."""

from html import escape
from urllib.parse import quote

from starlette.applications import Starlette
from starlette.middleware.wsgi import WSGIMiddleware
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Mount, Route

from .application import StationDatasetService, StationNotFoundError
from .config import Settings
from .dap import StationDapApplication
from .persistence import create_repository


async def health(request):
    return JSONResponse({"status": "ok"})


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
        items = []
        for network in service.networks():
            label = network.display_name or network.name
            href = f"/networks/{quote(network.name, safe='')}"
            items.append(
                f'<li><a href="{href}">{escape(label)}</a> '
                f"<small>({escape(network.name)})</small></li>"
            )
        content = "<ul>" + "".join(items) + "</ul>"
        return HTMLResponse(_page("Station networks", content))

    return endpoint


def _station_index(service: StationDatasetService):
    def endpoint(request):
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
                f"/dap/raw/{quote(network.name, safe='')}/"
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
            '<p><a href="/">All networks</a></p>'
            + description
            + "<ul>"
            + "".join(items)
            + "</ul>"
        )
        return HTMLResponse(_page(title, content))

    return endpoint


def _network_catalog_redirect(request):
    return RedirectResponse(
        request.url_for("network-stations", network=request.path_params["network"])
    )


def _root_catalog_redirect(request):
    return RedirectResponse(request.url_for("networks"))


def create_app(settings: Settings | None = None, repository=None) -> Starlette:
    if repository is None:
        settings = settings or Settings.from_environment()
        repository = create_repository(
            settings.database_url, yield_per=settings.database_yield_per
        )
    service = StationDatasetService(repository)
    dap = StationDapApplication(service, mount_path="/dap")
    return Starlette(
        routes=[
            Route("/health", health),
            Route("/", _network_index(service), name="networks"),
            Route(
                "/networks/{network}",
                _station_index(service),
                name="network-stations",
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
