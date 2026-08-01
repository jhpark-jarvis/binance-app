import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import dispose_engine, get_session
from app.core.events import MARKET_EVENTS_CHANNEL
from app.web.dashboard import build_dashboard, build_market_detail, detail_window_minutes

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    yield
    await app.state.redis.aclose()
    await dispose_engine()


app = FastAPI(title="Binance Operations Dashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, session: AsyncSession = Depends(get_session)) -> HTMLResponse:
    data = await build_dashboard(session, settings.symbols)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"dashboard": data, "dashboard_json": json.dumps(data)},
    )


@app.get("/api/dashboard")
async def dashboard_api(session: AsyncSession = Depends(get_session)) -> JSONResponse:
    return JSONResponse(await build_dashboard(session, settings.symbols))


def _configured_symbol(symbol: str) -> str:
    normalized = symbol.upper()
    if normalized not in settings.symbols:
        raise HTTPException(status_code=404, detail="Configured market symbol not found")
    return normalized


@app.get("/markets/{symbol}", response_class=HTMLResponse)
async def market_detail(
    symbol: str, request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    configured_symbol = _configured_symbol(symbol)
    detail = await build_market_detail(session, configured_symbol, "6h")
    return templates.TemplateResponse(
        request,
        "market_detail.html",
        {"detail": detail, "detail_json": json.dumps(detail)},
    )


@app.get("/api/markets/{symbol}/history")
async def market_history(
    symbol: str, window: str = "6h", session: AsyncSession = Depends(get_session)
) -> JSONResponse:
    configured_symbol = _configured_symbol(symbol)
    try:
        detail_window_minutes(window)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return JSONResponse(await build_market_detail(session, configured_symbol, window))


@app.get("/health")
async def health(session: AsyncSession = Depends(get_session)) -> JSONResponse:
    try:
        await session.execute(text("SELECT 1"))
        await app.state.redis.ping()
    except Exception as error:
        raise HTTPException(status_code=503, detail="Dependency unavailable") from error
    return JSONResponse({"status": "ok"})


@app.get("/events")
async def events(request: Request) -> StreamingResponse:
    async def stream():
        pubsub = app.state.redis.pubsub()
        await pubsub.subscribe(MARKET_EVENTS_CHANNEL)
        try:
            yield ": connected\n\n"
            async for message in pubsub.listen():
                if await request.is_disconnected():
                    break
                if message["type"] == "message":
                    yield f"data: {message['data']}\n\n"
        finally:
            await pubsub.unsubscribe(MARKET_EVENTS_CHANNEL)
            await pubsub.aclose()

    return StreamingResponse(stream(), media_type="text/event-stream")
