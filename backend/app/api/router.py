"""Routers de la API."""

from fastapi import APIRouter

from app.api.routes import (
    credentials,
    game_accounts,
    health,
    replays,
    stats,
    sync,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["operacion"])
api_router.include_router(users.router, prefix="/me", tags=["usuario"])
api_router.include_router(credentials.router, prefix="/me", tags=["ballchasing"])
api_router.include_router(game_accounts.router, prefix="/me/game-accounts", tags=["ballchasing"])
api_router.include_router(sync.router, tags=["sync"])
api_router.include_router(replays.router, tags=["datos"])
api_router.include_router(stats.router, tags=["datos"])
