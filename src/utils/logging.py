"""
Structured logging configuration with Loguru
"""
import sys
from pathlib import Path
from loguru import logger
from src.config import settings


def setup_logging() -> None:
    """Configure Loguru for structured logging."""
    
    # Remove default handler
    logger.remove()
    
    # Console handler with color
    if settings.log_format == "json":
        logger.add(
            sys.stdout,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            level=settings.log_level,
            colorize=True,
            serialize=False,
        )
    else:
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>",
            level=settings.log_level,
            colorize=True,
        )
    
    # File handler - always JSON for parsing
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    logger.add(
        logs_dir / "ironclaw_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
        level=settings.log_level,
        rotation="500 MB",
        retention="30 days",
        compression="zip",
        serialize=True,  # JSON format for file
    )
    
    # Error log file
    logger.add(
        logs_dir / "ironclaw_errors_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
        level="ERROR",
        rotation="100 MB",
        retention="90 days",
        compression="zip",
        serialize=True,
    )
    
    logger.info(f"Logging initialized - Level: {settings.log_level}, Format: {settings.log_format}")


def get_logger(name: str):
    """Get a logger instance with the given name."""
    return logger.bind(name=name)
