"""bgpeek FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from bgpeek import __version__
from bgpeek.api import auth as auth_api
from bgpeek.api import devices as devices_api
from bgpeek.api import query as query_api
from bgpeek.config import settings
from bgpeek.core.auth import optional_auth
from bgpeek.core.redis import close_redis, init_redis
from bgpeek.core.time_utils import timeago
from bgpeek.db import devices as device_crud
from bgpeek.db.pool import close_pool, get_pool, init_pool
from bgpeek.db.results import list_results
from bgpeek.models.user import User

log = structlog.get_logger()

templates = Jinja2Templates(directory=str(settings.templates_dir))
templates.env.filters["timeago"] = timeago


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown hooks."""
    log.info("bgpeek starting", version=__version__, host=settings.host, port=settings.port)
    await init_pool(settings.database_url)
    try:
        await init_redis(settings.redis_url)
    except Exception:
        log.warning("redis unavailable — cache disabled", exc_info=True)
    yield
    await close_redis()
    await close_pool()
    log.info("bgpeek shutting down")


app = FastAPI(
    title="bgpeek",
    description="Open-source looking glass for ISPs and IX operators",
    version=__version__,
    lifespan=lifespan,
)

app.mount(
    "/static",
    StaticFiles(directory=str(settings.static_dir)),
    name="static",
)

app.include_router(auth_api.router)
app.include_router(devices_api.router)
app.include_router(query_api.router)


@app.get("/api/health", response_class=JSONResponse)
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "version": __version__}


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    user: User | None = Depends(optional_auth),  # noqa: B008
) -> HTMLResponse:
    """Main looking glass form — loads devices from DB for the dropdown."""
    try:
        devices = await device_crud.list_devices(get_pool(), enabled_only=True)
    except RuntimeError:
        devices = []
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"version": __version__, "devices": devices, "user": user},
    )


_HISTORY_PAGE_SIZE = 25


@app.get("/history", response_class=HTMLResponse)
async def history(
    request: Request,
    offset: int = 0,
    partial: int = 0,
    user: User | None = Depends(optional_auth),  # noqa: B008
) -> HTMLResponse:
    """Query history page with offset-based pagination."""
    user_id = user.id if user else None
    try:
        results = await list_results(
            get_pool(),
            user_id=user_id,
            limit=_HISTORY_PAGE_SIZE + 1,
            offset=max(offset, 0),
        )
    except RuntimeError:
        results = []

    has_more = len(results) > _HISTORY_PAGE_SIZE
    if has_more:
        results = results[:_HISTORY_PAGE_SIZE]

    next_offset = max(offset, 0) + _HISTORY_PAGE_SIZE
    ctx = {
        "results": results,
        "has_more": has_more,
        "next_offset": next_offset,
        "user": user,
    }

    if partial:
        return templates.TemplateResponse(
            request=request,
            name="partials/history_rows.html",
            context=ctx,
        )
    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context=ctx,
    )


def run() -> None:
    """Console entry point: start uvicorn."""
    import uvicorn

    uvicorn.run(
        "bgpeek.main:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        log_config=None,
    )


if __name__ == "__main__":
    run()
