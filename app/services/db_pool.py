import logging
import asyncpg
from typing import Optional
from app.core.config import settings
from app.exceptions.database_exception import DatabaseExecutionException

logger = logging.getLogger(__name__)


class DatabasePool:
    _pool: Optional[asyncpg.Pool] = None  # private class variable annoted "_"

    @classmethod
    async def initalize_pool(cls) -> None:

        if cls._pool is None:
            logger.info("Initializing PostgreSQL connection pool..")
            cls._pool = await asyncpg.create_pool(
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                database=settings.DB_NAME,
                min_size=settings.DB_MIN_POOL_SIZE,
                max_size=settings.DB_POOL_SIZE,
                max_inactive_connection_lifetime=settings.DB_POOL_RECYCLE,
                timeout=settings.DB_POOL_TIMEOUT,
            )

    @classmethod
    async def get_pool(cls) -> asyncpg.Pool:
        if cls._pool is None:
            raise DatabaseExecutionException(
                error_message="Database pool has not been intialized."
            )
        return cls._pool

    @classmethod
    async def close_pool(cls) -> None:
        if cls._pool is not None:
            logger.info("Closing PostgresSQL connecton pool...")
            await cls._pool.close()
            cls._pool = None
