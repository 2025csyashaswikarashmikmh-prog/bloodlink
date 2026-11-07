"""RaktaSetu API - FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import models  # noqa: F401  (register tables)
from .auth import decode_token
from .blood import BLOOD_GROUPS, HOSPITALS, RECIPIENT_CAN_RECEIVE_FROM
from .config import settings
from .database import Base, SessionLocal, engine
from .i18n import LANGS
from .matching import escalation_tick
from .realtime import hub
from .routers import admin_routes, auth_routes, donor_routes, request_routes, voice_routes
from .seed import seed
from .store import store


async def escalation_worker():
    """Background worker: expires unanswered alerts, flags no-shows, escalates to next donors."""
    while True:
        await asyncio.sleep(settings.ESCALATION_TICK_SEC)
        try:
            def _run():
                db = SessionLocal()
                try:
                    return escalation_tick(db)
                finally:
                    db.close()
            await asyncio.to_thread(_run)
        except Exception as e:  # keep the worker alive
            print(f"[worker] tick failed: {e}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.SEED_DEMO_DATA:
        db = SessionLocal()
        try:
            if seed(db):
                print("[seed] demo data inserted")
        finally:
            db.close()
    hub.loop = asyncio.get_running_loop()
    task = asyncio.create_task(escalation_worker())
    yield
    task.cancel()


app = FastAPI(title="RaktaSetu API", version="1.0.0", lifespan=lifespan,
              description="Voice-first multilingual emergency blood donor coordination platform")
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

for r in (auth_routes.router, auth_routes.demo, donor_routes.router, request_routes.router, admin_routes.router,
          admin_routes.public, voice_routes.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    db_ok = ml_ok = False
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    try:
        ml_ok = httpx.get(f"{settings.ML_SERVICE_URL}/health", timeout=2).status_code == 200
    except Exception:
        pass
    return {"status": "ok" if db_ok else "degraded", "database": db_ok, "ml_service": ml_ok, "store": store.backend,
            "db_engine": engine.dialect.name, "demo_mode": settings.DEMO_MODE, "version": app.version}


@app.get("/api/meta")
def meta():
    return {"blood_groups": BLOOD_GROUPS, "compatibility": RECIPIENT_CAN_RECEIVE_FROM, "languages": LANGS,
            "hospitals": [{"name": h["name"], "lat": h["lat"], "lon": h["lon"]} for h in HOSPITALS],
            "response_window_sec": settings.RESPONSE_WINDOW_SEC, "commitment_window_min": settings.COMMITMENT_WINDOW_MIN,
            "demo_mode": settings.DEMO_MODE}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket, channels: str = "", token: str = ""):
    claims = decode_token(token) if token else None
    allowed = []
    for c in filter(None, channels.split(",")):
        if c.startswith("request:"):
            allowed.append(c)
        elif c.startswith("donor:") and claims and c == f"donor:{claims['sub']}":
            allowed.append(c)
        elif c == "admin" and claims and claims.get("role") in {"admin", "staff"}:
            allowed.append(c)
    await hub.connect(ws, allowed)
    await ws.send_json({"type": "subscribed", "channels": allowed})
    try:
        while True:
            await ws.receive_text()  # keep-alive pings from the client
    except WebSocketDisconnect:
        hub.disconnect(ws)


# Optional: serve the static frontend from the API container (single-container / local dev mode).
if settings.STATIC_DIR:
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=settings.STATIC_DIR, html=True), name="frontend")
