"""Setu backend: FastAPI app hosting the intake API, the LangGraph pipeline,
and the static citizen chat page.

Minimal shell for now (task 1.5): health endpoint + citizen-web static mount.
Pipeline routers land with Tracks A/B.
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import db


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.pool.open()
    # Checkpointer tables live in the same database (design D2/D3, task 1.8).
    db.setup_checkpointer()
    yield
    db.pool.close()


app = FastAPI(title="Setu", version="0.1.0", lifespan=lifespan)

# Routers are discovered dynamically: each module in app/routers/ that defines
# `router` is included. Tracks add endpoints by dropping a file — no edits to
# this module, so parallel work never collides here.
import importlib
import pkgutil

from app import routers as _routers_pkg

for _m in pkgutil.iter_modules(_routers_pkg.__path__):
    _mod = importlib.import_module(f"app.routers.{_m.name}")
    if hasattr(_mod, "router"):
        app.include_router(_mod.router)

# The citizen chat page is a static, framework-free page served by the backend
# (design D4) — it must work with the dashboard process stopped. In the container
# it is volume-mounted at /app/citizen-web; locally it sits at the repo root.
_citizen_web = Path(
    os.environ.get(
        "CITIZEN_WEB_DIR",
        Path(__file__).resolve().parent.parent.parent / "citizen-web",
    )
)
if _citizen_web.is_dir():
    app.mount("/citizen", StaticFiles(directory=_citizen_web, html=True), name="citizen")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "setu-backend"}
