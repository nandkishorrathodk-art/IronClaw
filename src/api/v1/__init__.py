"""
API v1 router
Aggregates all v1 endpoints
"""
from fastapi import APIRouter
from src.api.v1 import automation, chat, plugins, voice, learning

router = APIRouter()

# Include all endpoint modules
router.include_router(automation.router)
router.include_router(chat.router)
router.include_router(plugins.router)
router.include_router(voice.router)
router.include_router(learning.router)
