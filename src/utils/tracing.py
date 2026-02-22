"""
OpenTelemetry distributed tracing for Ironclaw
"""
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from typing import Optional
from fastapi import FastAPI

from src.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


def setup_tracing(app: FastAPI) -> Optional[TracerProvider]:
    """
    Set up OpenTelemetry distributed tracing.
    
    Args:
        app: FastAPI application instance
    
    Returns:
        TracerProvider if tracing is enabled, None otherwise
    """
    if not settings.enable_opentelemetry:
        logger.info("OpenTelemetry tracing disabled")
        return None
    
    try:
        # Create resource with service information
        resource = Resource(attributes={
            SERVICE_NAME: "ironclaw-api",
            "service.version": "0.1.0",
            "deployment.environment": settings.environment,
        })
        
        # Create tracer provider
        tracer_provider = TracerProvider(resource=resource)
        
        # Add span processors
        if settings.otel_exporter_endpoint:
            # Export to OTLP collector (Jaeger, etc.)
            otlp_exporter = OTLPSpanExporter(
                endpoint=settings.otel_exporter_endpoint,
                insecure=not settings.is_production,
            )
            tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info(f"OTLP exporter configured: {settings.otel_exporter_endpoint}")
        
        if settings.is_development:
            # Also log traces to console in development
            console_exporter = ConsoleSpanExporter()
            tracer_provider.add_span_processor(BatchSpanProcessor(console_exporter))
            logger.info("Console exporter enabled for development")
        
        # Set global tracer provider
        trace.set_tracer_provider(tracer_provider)
        
        # Instrument FastAPI
        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI instrumented for tracing")
        
        # Instrument HTTP client
        HTTPXClientInstrumentor().instrument()
        logger.info("HTTPX client instrumented for tracing")
        
        # Instrument SQLAlchemy (will be auto-detected)
        try:
            SQLAlchemyInstrumentor().instrument()
            logger.info("SQLAlchemy instrumented for tracing")
        except Exception as e:
            logger.warning(f"SQLAlchemy instrumentation failed: {e}")
        
        # Instrument Redis (will be auto-detected)
        try:
            RedisInstrumentor().instrument()
            logger.info("Redis instrumented for tracing")
        except Exception as e:
            logger.warning(f"Redis instrumentation failed: {e}")
        
        logger.info("✅ OpenTelemetry tracing setup complete")
        return tracer_provider
    
    except Exception as e:
        logger.error(f"Failed to set up tracing: {e}", exc_info=True)
        return None


def get_tracer(name: str) -> trace.Tracer:
    """
    Get a tracer instance.
    
    Args:
        name: Name of the tracer (usually module name)
    
    Returns:
        Tracer instance
    """
    return trace.get_tracer(name)


def create_span(name: str, attributes: Optional[dict] = None):
    """
    Create a new span with optional attributes.
    
    Args:
        name: Span name
        attributes: Optional span attributes
    
    Returns:
        Span context manager
    """
    tracer = trace.get_tracer(__name__)
    span = tracer.start_as_current_span(name)
    
    if attributes:
        for key, value in attributes.items():
            span.set_attribute(key, value)
    
    return span


def record_exception(exc: Exception, span: Optional[trace.Span] = None):
    """
    Record an exception in the current span.
    
    Args:
        exc: Exception to record
        span: Optional span to record exception in (uses current if None)
    """
    if span is None:
        span = trace.get_current_span()
    
    if span.is_recording():
        span.record_exception(exc)
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
