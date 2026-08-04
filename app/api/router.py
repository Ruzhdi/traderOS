from fastapi import APIRouter

from app.api.routes import auth, health, trade_imports, trades

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(health.router)
api_router.include_router(trades.router)
api_router.include_router(trade_imports.router)
