"""FastAPI application lifecycle and health endpoints."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.workflows import router
from app.core.config import settings
from app.core.scheduler import initialize_scheduler, shutdown_scheduler
from app.mcp.postgres_client import PostgresMCPError
from app.services.postgres_workflows import get_postgres_workflows

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start and stop the scheduler without opening database connections."""
    await initialize_scheduler()
    try:
        yield
    finally:
        await shutdown_scheduler()


app = FastAPI(
    title="Smoothie Email Subscription Service",
    description="Subscription workflow management with email execution disabled",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)
app.include_router(router, prefix="/api")


@app.get("/health")
async def health():
    """Return a liveness response."""
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness_check():
    """Report data readiness while email execution remains disabled."""
    try:
        database_ready = await get_postgres_workflows().ready()
    except PostgresMCPError as error:
        logger.warning("PostgreSQL MCP readiness failed: %s", error.code)
        database_ready = False
    payload = {
        "status": "unhealthy",
        "database": "connected" if database_ready else "disconnected",
        "email_delivery": "unavailable",
    }
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
