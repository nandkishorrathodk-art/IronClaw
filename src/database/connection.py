"""
Async database connection management with SQLAlchemy
Optimized for PostgreSQL with connection pooling
"""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool, QueuePool

from src.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Base class for all models
Base = declarative_base()

# Global engine and session maker
engine = None
async_session_maker = None


async def init_database() -> None:
    """
    Initialize database engine and session maker.
    Called during application startup.
    """
    global engine, async_session_maker
    
    logger.info(f"Initializing database connection to: {settings.database_url.split('@')[1]}")
    
    # Create async engine with connection pooling
    engine = create_async_engine(
        settings.database_url,
        echo=settings.database_echo,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=3600,  # Recycle connections after 1 hour
        poolclass=QueuePool if settings.is_production else NullPool,
    )
    
    # Create session maker
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    # Create tables if they don't exist (for development)
    if settings.is_development:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created (if not exist)")
    
    logger.info("✅ Database initialized successfully")


async def close_database() -> None:
    """
    Close database connections.
    Called during application shutdown.
    """
    global engine
    
    if engine:
        logger.info("Closing database connections...")
        await engine.dispose()
        logger.info("✅ Database connections closed")


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async database session.
    
    Usage in FastAPI:
        @app.get("/")
        async def endpoint(db: AsyncSession = Depends(get_db_session)):
            result = await db.execute(select(User))
            return result.scalars().all()
    """
    if async_session_maker is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()


async def check_database_health() -> bool:
    """
    Check if database connection is healthy.
    Used for readiness probes.
    """
    try:
        if engine is None:
            return False
        
        async with engine.begin() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False
