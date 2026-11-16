import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .core.config import settings
from .api import api_router
from .db.database import get_total_medicine_count
from .db.mongo_client import mongo_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("medicare")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing MediCare AI Backend Application...")
    try:
        count = get_total_medicine_count()
        logger.info("Connected to database successfully. Total indexed medicines: %d", count)
        if mongo_manager.is_connected():
            mongo_manager.init_indexes()
            logger.info("MongoDB initialized with user, scan, and medicine collections.")
    except Exception as e:
        logger.error("Database connection check failed: %s", str(e))
    yield
    logger.info("Shutting down MediCare AI Backend Application...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="MediCare AI: Multimodal medicine packaging scanner with Google Gemini vision, NLP matching, and patient-friendly explanations.",
    lifespan=lifespan
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all API routes under /api
app.include_router(api_router, prefix=settings.API_V1_PREFIX)

@app.get("/api")
def api_info():
    return {
        "app": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "status": "online",
        "docs_url": "/docs",
        "health_url": f"{settings.API_V1_PREFIX}/health",
        "gemini_model": settings.GEMINI_MODEL,
        "gemini_active": bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.strip() not in ["", "your_gemini_api_key_here"]),
        "ocr_space_active": bool(settings.OCR_SPACE_API_KEY and settings.OCR_SPACE_API_KEY.strip() not in ["", "your_ocr_space_api_key_here"]),
        "database": "mongodb" if mongo_manager.is_connected() else "sqlite"
    }

# Ensure frontend directory exists and mount static files
if settings.FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(settings.FRONTEND_DIR), html=True), name="frontend")
else:
    @app.get("/")
    def root():
        return api_info()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
