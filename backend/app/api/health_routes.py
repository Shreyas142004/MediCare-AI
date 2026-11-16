from fastapi import APIRouter
from ..db.database import get_total_medicine_count
from ..db.mongo_client import mongo_manager
from ..core.config import settings

router = APIRouter(prefix="", tags=["Health"])

@router.get("/health")
def health_check():
    mongo_active = mongo_manager.is_connected()
    try:
        med_count = get_total_medicine_count()
        db_status = "connected"
    except Exception as e:
        med_count = 0
        db_status = f"error: {str(e)}"
        
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "database": {
            "configured_type": settings.DATABASE_TYPE,
            "status": db_status,
            "total_medicines": med_count,
            "mongodb": {
                "active": mongo_active,
                "uri": settings.MONGO_URI,
                "database": settings.MONGO_DB_NAME,
                "medicines_count": mongo_manager.count_medicines() if mongo_active else 0
            },
            "sqlite_fallback": {
                "path": str(settings.DB_PATH)
            }
        },
        "ocr_engine": "EasyOCR (PyTorch)",
        "nlp_engine": "Hybrid FTS5 / MongoDB Text + RapidFuzz"
    }
