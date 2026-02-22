"""
Sentry error tracking integration for Ironclaw
"""
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from typing import Optional

from src.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


def setup_sentry() -> bool:
    """
    Set up Sentry error tracking.
    
    Returns:
        True if Sentry was successfully initialized, False otherwise
    """
    if not settings.enable_sentry or not settings.sentry_dsn:
        logger.info("Sentry error tracking disabled")
        return False
    
    try:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            release=f"ironclaw@0.1.0",
            traces_sample_rate=1.0 if settings.is_development else 0.1,
            profiles_sample_rate=1.0 if settings.is_development else 0.1,
            integrations=[
                FastApiIntegration(),
                HttpxIntegration(),
                RedisIntegration(),
                SqlalchemyIntegration(),
            ],
            before_send=before_send,
            before_breadcrumb=before_breadcrumb,
        )
        
        logger.info("✅ Sentry error tracking initialized")
        return True
    
    except Exception as e:
        logger.error(f"Failed to initialize Sentry: {e}", exc_info=True)
        return False


def before_send(event: dict, hint: dict) -> Optional[dict]:
    """
    Filter events before sending to Sentry.
    
    Args:
        event: Sentry event dictionary
        hint: Event hint with exception info
    
    Returns:
        Modified event or None to skip sending
    """
    # Don't send health check errors
    if "url" in event.get("request", {}):
        url = event["request"]["url"]
        if "/health" in url or "/metrics" in url:
            return None
    
    # Don't send 404 errors
    if event.get("status_code") == 404:
        return None
    
    # Add custom tags
    event.setdefault("tags", {})
    event["tags"]["app"] = "ironclaw"
    
    return event


def before_breadcrumb(crumb: dict, hint: dict) -> Optional[dict]:
    """
    Filter breadcrumbs before adding to event.
    
    Args:
        crumb: Breadcrumb dictionary
        hint: Breadcrumb hint
    
    Returns:
        Modified breadcrumb or None to skip
    """
    # Skip SQL query breadcrumbs in production (too verbose)
    if settings.is_production and crumb.get("category") == "query":
        return None
    
    return crumb


def capture_exception(exc: Exception, **kwargs):
    """
    Capture exception with Sentry.
    
    Args:
        exc: Exception to capture
        **kwargs: Additional context
    """
    if settings.enable_sentry and settings.sentry_dsn:
        sentry_sdk.capture_exception(exc, **kwargs)


def capture_message(message: str, level: str = "info", **kwargs):
    """
    Capture message with Sentry.
    
    Args:
        message: Message to capture
        level: Severity level (debug, info, warning, error, fatal)
        **kwargs: Additional context
    """
    if settings.enable_sentry and settings.sentry_dsn:
        sentry_sdk.capture_message(message, level=level, **kwargs)


def set_user(user_id: str, **kwargs):
    """
    Set user context for error tracking.
    
    Args:
        user_id: User identifier
        **kwargs: Additional user attributes (email, username, etc.)
    """
    if settings.enable_sentry and settings.sentry_dsn:
        sentry_sdk.set_user({"id": user_id, **kwargs})


def set_tag(key: str, value: str):
    """
    Set a tag for all future events.
    
    Args:
        key: Tag key
        value: Tag value
    """
    if settings.enable_sentry and settings.sentry_dsn:
        sentry_sdk.set_tag(key, value)


def set_context(name: str, context: dict):
    """
    Set a context for all future events.
    
    Args:
        name: Context name
        context: Context data
    """
    if settings.enable_sentry and settings.sentry_dsn:
        sentry_sdk.set_context(name, context)
