"""
API v1 router
Aggregates all v1 endpoints
"""
from fastapi import APIRouter
from src.api.v1 import chat, plugins

router = APIRouter()

# Include all endpoint modules
router.include_router(chat.router)
router.include_router(plugins.router)
