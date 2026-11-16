from fastapi import APIRouter
from .health_routes import router as health_router
from .medicine_routes import router as medicine_router
from .ocr_routes import router as ocr_router
from .medicine_scan_routes import router as medicine_scan_router
from .auth_routes import router as auth_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(medicine_router)
api_router.include_router(ocr_router)
api_router.include_router(medicine_scan_router)
api_router.include_router(auth_router)

__all__ = ["api_router"]
