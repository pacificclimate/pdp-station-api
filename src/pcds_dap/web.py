"""ASGI composition root."""

from starlette.applications import Starlette
from starlette.middleware.wsgi import WSGIMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .application import StationDatasetService
from .config import Settings
from .dap import StationDapApplication
from .persistence import create_repository


async def health(request):
    return JSONResponse({"status": "ok"})


def create_app(settings: Settings | None = None) -> Starlette:
    settings = settings or Settings.from_environment()
    repository = create_repository(
        settings.database_url, yield_per=settings.database_yield_per
    )
    service = StationDatasetService(repository)
    dap = StationDapApplication(service)
    return Starlette(
        routes=[
            Route("/health", health),
            Mount("/dap", app=WSGIMiddleware(dap)),
        ]
    )
