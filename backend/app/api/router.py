"""Routers de la API."""

from fastapi import APIRouter

from app.api.routes import health, users

api_router = APIRouter()
api_router.include_router(health.router, tags=["operacion"])
api_router.include_router(users.router, prefix="/me", tags=["usuario"])
