"""FastAPI application factory.

Serves the verification API plus well-known plugin discovery endpoints
so that ChatGPT, Claude, Gemini, and MCP clients can all connect.

Well-known endpoints:
  GET /.well-known/ai-plugin.json   — ChatGPT plugin manifest
  GET /openapi.json                 — OpenAPI spec (all platforms)
  GET /openapi.yaml                 — OpenAPI spec (YAML)
  GET /.well-known/plugin.json      — Generic plugin manifest
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.db.models import init_db

logger = logging.getLogger(__name__)

# Resolve paths relative to this file
_HERE = os.path.dirname(os.path.abspath(__file__))
_MANIFESTS_DIR = os.path.join(_HERE, "..", "plugin_manifests")
_STATIC_DIR = os.path.join(_HERE, "..", "static")


def _load_manifest(rel_path: str) -> dict:
    full = os.path.join(_MANIFESTS_DIR, rel_path)
    if os.path.exists(full):
        with open(full) as f:
            return json.load(f)
    return {}


def _load_openapi_yaml() -> str:
    full = os.path.join(_MANIFESTS_DIR, "chatgpt", "openapi.yaml")
    if os.path.exists(full):
        with open(full) as f:
            return f.read()
    return ""


def create_app() -> FastAPI:
    app = FastAPI(
        title="HalluGuard — Hallucination Prevention Plugin",
        description=(
            "A production-grade verification layer that enforces evidence-based generation. "
            "Compatible with ChatGPT Actions, Claude plugins, Gemini Extensions, and MCP."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS: open to all origins so external agents can call the API ──────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,   # must be False when allow_origins=["*"]
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request ID + timing middleware ─────────────────────────────────────────
    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.1f}"
        return response

    # ── Global error handler ───────────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_error_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})

    # ── Plugin discovery endpoints ─────────────────────────────────────────────

    @app.get("/.well-known/ai-plugin.json", include_in_schema=False)
    async def chatgpt_plugin_manifest():
        """ChatGPT / OpenAI Actions plugin manifest."""
        manifest = _load_manifest("chatgpt/ai-plugin.json")
        return JSONResponse(content=manifest)

    @app.get("/.well-known/plugin.json", include_in_schema=False)
    async def generic_plugin_manifest():
        """Generic plugin manifest (Claude .claude-plugin format)."""
        manifest = _load_manifest("claude/.claude-plugin/plugin.json")
        return JSONResponse(content=manifest)

    @app.get("/openapi.yaml", include_in_schema=False)
    async def openapi_yaml():
        """OpenAPI spec in YAML — used by ChatGPT Actions and Gemini Extensions."""
        content = _load_openapi_yaml()
        return PlainTextResponse(content=content, media_type="application/yaml")

    @app.get("/openapi.json", include_in_schema=False)
    async def openapi_json_override():
        """OpenAPI spec in JSON — redirected from FastAPI's default /openapi.json."""
        content = _load_openapi_yaml()
        if content:
            data = yaml.safe_load(content)
            return JSONResponse(content=data)
        # Fall back to FastAPI's auto-generated spec
        return JSONResponse(content=app.openapi())

    # ── Static assets (logo etc.) ──────────────────────────────────────────────
    os.makedirs(_STATIC_DIR, exist_ok=True)
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    # ── API routes ─────────────────────────────────────────────────────────────
    from app.api.routes import verify, claims, sources, health, metrics
    app.include_router(health.router, tags=["health"])
    app.include_router(verify.router, prefix="/v1", tags=["verification"])
    app.include_router(claims.router, prefix="/v1", tags=["claims"])
    app.include_router(sources.router, prefix="/v1", tags=["sources"])
    app.include_router(metrics.router, prefix="/v1", tags=["metrics"])

    @app.on_event("startup")
    async def on_startup():
        try:
            await init_db()
            logger.info("Database initialised.")
        except Exception as exc:
            logger.warning("DB init skipped (no DB configured): %s", exc)

    return app


app = create_app()
