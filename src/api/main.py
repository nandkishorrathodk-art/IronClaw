"""
Ironclaw FastAPI Application
Main entry point with async optimization for Acer Swift Neo
"""
import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.config import settings
from src.utils.logging import setup_logging, get_logger
from src.utils.metrics import (
    http_requests_total,
    http_request_duration_seconds,
    http_requests_in_progress,
    update_system_metrics,
)
from src.database.connection import init_database, close_database, check_database_health
from src.database.redis_client import init_redis, close_redis, check_redis_health

# Initialize logging
setup_logging()
logger = get_logger(__name__)


# Rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Lifecycle manager for FastAPI application.
    Handles startup and shutdown tasks.
    """
    logger.info("🚀 Ironclaw starting up...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"Available AI providers: {settings.available_ai_providers}")
    
    # Initialize database connection
    await init_database()
    
    # Initialize Redis connection
    await init_redis()
    
    # Start background tasks
    metrics_task = None
    if settings.enable_prometheus:
        logger.info("Starting system metrics monitoring...")
        metrics_task = asyncio.create_task(update_system_metrics())
    
    logger.info("✅ Ironclaw startup complete!")
    
    yield
    
    # Shutdown
    logger.info("🛑 Ironclaw shutting down...")
    
    if metrics_task:
        metrics_task.cancel()
        try:
            await metrics_task
        except asyncio.CancelledError:
            pass
    
    # Close database connections
    await close_database()
    
    # Close Redis connection
    await close_redis()
    
    logger.info("✅ Ironclaw shutdown complete!")


# Create FastAPI app
app = FastAPI(
    title="Ironclaw API",
    description="Next-generation AI assistant - 10x more powerful than Aether AI",
    version="0.1.0",
    docs_url="/docs" if settings.enable_swagger_ui else None,
    redoc_url="/redoc" if settings.enable_redoc else None,
    lifespan=lifespan,
)

# Add rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# CORS Middleware
if settings.enable_cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info(f"CORS enabled for origins: {settings.allowed_origins}")


# Gzip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Metrics middleware
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Record HTTP metrics for Prometheus."""
    method = request.method
    path = request.url.path
    
    # Skip metrics endpoint itself
    if path == "/metrics":
        return await call_next(request)
    
    # Track in-progress requests
    http_requests_in_progress.labels(method=method, endpoint=path).inc()
    
    # Time the request
    start_time = time.time()
    
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as e:
        logger.error(f"Request failed: {e}")
        status_code = 500
        response = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )
    finally:
        # Record metrics
        duration = time.time() - start_time
        http_requests_in_progress.labels(method=method, endpoint=path).dec()
        http_requests_total.labels(
            method=method, endpoint=path, status_code=status_code
        ).inc()
        http_request_duration_seconds.labels(method=method, endpoint=path).observe(
            duration
        )
    
    return response


# Exception handler for unhandled errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An internal error occurred. Please try again later."
            if settings.is_production
            else str(exc)
        },
    )


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint.
    Returns 200 OK if the service is running.
    """
    return {
        "status": "healthy",
        "version": "0.1.0",
        "environment": settings.environment,
    }


@app.get("/health/live", tags=["Health"])
async def liveness_probe():
    """
    Kubernetes liveness probe.
    Returns 200 if the application is alive.
    """
    return {"status": "alive"}


@app.get("/health/ready", tags=["Health"])
async def readiness_probe():
    """
    Kubernetes readiness probe.
    Returns 200 if the application is ready to serve traffic.
    """
    # Check database connection
    db_healthy = await check_database_health()
    
    # Check Redis connection
    redis_healthy = await check_redis_health()
    
    if not (db_healthy and redis_healthy):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "database": db_healthy,
                "redis": redis_healthy,
            },
        )
    
    return {
        "status": "ready",
        "database": db_healthy,
        "redis": redis_healthy,
    }


# Mount Prometheus metrics endpoint
if settings.enable_prometheus:
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)
    logger.info("Prometheus metrics available at /metrics")


# API v1 router
from src.api.v1 import router as v1_router
app.include_router(v1_router, prefix="/api/v1")


@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint with API information.
    """
    return {
        "name": "Ironclaw API",
        "version": "0.1.0",
        "description": "Next-generation AI assistant - 10x more powerful than Aether AI",
        "docs": "/docs" if settings.enable_swagger_ui else None,
        "health": "/health",
        "metrics": "/metrics" if settings.enable_prometheus else None,
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload and settings.is_development,
        workers=settings.api_workers,
        log_level=settings.log_level.lower(),
    )
