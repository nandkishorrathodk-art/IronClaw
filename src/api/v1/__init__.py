"""
API v1 router
Aggregates all v1 endpoints
"""
from fastapi import APIRouter
from src.api.v1 import automation, chat, plugins, voice, learning, websocket, collaboration, security, vision

router = APIRouter()

# Include all endpoint modules
router.include_router(automation.router)
router.include_router(chat.router)
router.include_router(plugins.router)
router.include_router(voice.router)
router.include_router(learning.router)
router.include_router(websocket.router)
router.include_router(collaboration.router)
router.include_router(security.router)
router.include_router(vision.router)
