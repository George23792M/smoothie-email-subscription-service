from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
import logging
import asyncio
from app.api import router
from app.core.config import settings
from app.services.db_pool import DatabasePool
from app.core.scheduler import initialize_scheduler, shutdown_scheduler
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database pool on startup, close on shutdown."""

    # Run database initialization with timeout
    try:
        await asyncio.wait_for(DatabasePool.initalize_pool(), timeout=5.0)
        logger.info("✓ Database pool initialized successfully")
        await initialize_scheduler()
        logger.info("Scheduler initialzied successfully")
    except asyncio.TimeoutError:
        logger.warning("⚠ Database initialization timed out after 5 seconds")
        logger.warning(
            "Application started without database. API endpoints requiring DB will return 500 errors."
        )
    except Exception as e:
        logger.error(f"⚠ Database initialization failed: {e}")

    yield  # continue

    # Shutdown
    try:
        await shutdown_scheduler()
        logger.info("Scheduler stopped successfully")
        await DatabasePool.close_pool()
        logger.info("✓ Database pool closed successfully")

    except Exception as e:
        logger.error(f"⚠ Error closing database pool: {e}")


app = FastAPI(
    title="Smoothie Email Subscription Service",
    description="AI-powered email generation with LangGraph",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router, prefix="/api")


# Health check
@app.get("/health")
async def health():
    """Basic health check to confirm service is up"""
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness_check():
    """Check if the downstream service db are healthy and ready for serve traffic"""
    try:
        is_connected = (
            await DatabasePool.ping() if hasattr(DatabasePool, "ping") else True
        )
        if not is_connected:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "unhealthy", "database": "disconnected"},
            )
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "database": "error"},
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
