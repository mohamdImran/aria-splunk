"""
ARIA Backend — FastAPI entry point.
Boots the multi-agent orchestrator, Redis client, and all routers.
"""
import asyncio
import logging
import json
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from splunk.mcp_client import SplunkMCPClient
from agents.orchestrator import ARIAOrchestrator
from routers import incidents, agents, runbooks, websocket as ws_router
from routers.websocket import manager as ws_manager

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)

# ── Singleton instances ───────────────────────────────────────────────────────
_orchestrator: Optional[ARIAOrchestrator] = None
_redis = None

# In-memory state cache — used as Redis fallback for state_snapshot replay.
# Keyed by incident_id, value is the full ARIAState dict.
_state_cache: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle manager."""
    global _orchestrator, _redis

    # 1. Connect to Redis
    try:
        import redis.asyncio as aioredis
        _redis = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        await _redis.ping()
        logger.info(f"Redis connected: {settings.REDIS_URL}")
    except Exception as e:
        logger.warning(f"Redis unavailable ({e}), state will be in-memory only")
        _redis = None

    # 2. Initialize Splunk MCP client
    mcp_client = SplunkMCPClient(
        mcp_server_url=settings.SPLUNK_MCP_URL,
        token=settings.SPLUNK_TOKEN,
    )
    logger.info(
        f"Splunk MCP client ready (demo_mode={mcp_client.demo_mode}, "
        f"url={settings.SPLUNK_MCP_URL})"
    )

    # 3. Create orchestrator with WebSocket broadcast
    _orchestrator = ARIAOrchestrator(
        mcp_client=mcp_client,
        ws_broadcast=_ws_broadcast,
        redis_client=_redis,
    )
    logger.info("ARIA Orchestrator initialized — all 4 agents ready")

    yield

    # Cleanup
    if _redis:
        await _redis.aclose()
    logger.info("ARIA Backend shutdown complete")


app = FastAPI(
    title="ARIA — Agentic Resilience Intelligence Architect",
    description=(
        "Enterprise-grade multi-agent incident intelligence platform. "
        "Causal AI + LangGraph + Splunk MCP."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# In production the frontend is served by nginx which proxies /api → backend,
# so CORS is never triggered. In development Vite's proxy handles it the same way.
#
# This CORS config is a safety net for direct API access (curl, Postman, etc.)
# and for production deployments where the frontend domain differs.
#
# Note: allow_credentials=True requires explicit origins (not "*").
# Using "*" with credentials is spec-invalid and browsers reject it.
_CORS_ORIGINS = [
    "http://localhost:3000",   # Vite dev server
    "http://localhost:5173",   # Vite default fallback
    "http://127.0.0.1:3000",
    "http://localhost:8080",   # Docker nginx
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
    expose_headers=["Content-Type"],
    max_age=600,
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(incidents.router, prefix="/api")
app.include_router(agents.router,    prefix="/api")
app.include_router(runbooks.router,  prefix="/api")
app.include_router(ws_router.router)


# ── Health + info endpoints ───────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "demo_mode": settings.DEMO_MODE,
        "redis": _redis is not None,
        "version": "1.0.0",
    }


@app.get("/")
async def root():
    return {
        "name": "ARIA",
        "tagline": "Agentic Resilience Intelligence Architect",
        "docs": "/docs",
        "health": "/health",
    }


# ── Shared accessors (used by routers to avoid circular imports) ───────────────

def get_orchestrator() -> Optional[ARIAOrchestrator]:
    return _orchestrator


async def get_incident_state(incident_id: str) -> Optional[dict]:
    """
    Fetch the full pipeline state for an incident.
    Tries Redis first, then falls back to the in-memory cache,
    then falls back to a minimal snapshot from the incident record.
    """
    # 1. Redis
    if _redis:
        try:
            raw = await _redis.get(f"aria:incident:{incident_id}")
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning("Redis get failed: %s", e)

    # 2. In-memory cache (populated by orchestrator._persist)
    if incident_id in _state_cache:
        return _state_cache[incident_id]

    return None


def cache_incident_state(incident_id: str, state: dict) -> None:
    """Store a state snapshot in the in-memory cache (used by orchestrator)."""
    _state_cache[incident_id] = state
    # Keep the cache from growing unbounded — evict oldest if > 20 incidents
    if len(_state_cache) > 20:
        oldest = next(iter(_state_cache))
        del _state_cache[oldest]


async def _ws_broadcast(incident_id: str, message: dict):
    """Broadcast a message to all WebSocket clients for an incident."""
    await ws_manager.broadcast(incident_id, message)
