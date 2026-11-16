import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(ROOT_DIR / ".env")

class Settings(BaseModel):
    PROJECT_NAME: str = "MediCare AI Backend"
    PROJECT_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api"
    
    # Path configuration
    APP_DIR: Path = Path(__file__).resolve().parent.parent
    BACKEND_DIR: Path = BACKEND_DIR
    ROOT_DIR: Path = ROOT_DIR
    DATASET_DIR: Path = ROOT_DIR / "dataset"
    FRONTEND_DIR: Path = ROOT_DIR / "frontend"
    
    # Database configuration
    DATABASE_TYPE: str = os.getenv("DATABASE_TYPE", "mongodb")
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "medicare_db")
    MONGO_COLLECTION_MEDICINES: str = "medicines"
    MONGO_COLLECTION_SCANS: str = "scanhistories"
    MONGO_COLLECTION_USERS: str = "users"
    MONGO_COLLECTION_OTPS: str = "otps"
    
    # SQLite Fallback Settings
    DB_PATH: Path = BACKEND_DIR / "medicare.db"
    
    # Raw dataset paths
    CSV_PATH: Path = DATASET_DIR / "medicine_data.csv"
    XLSX_PATH: Path = DATASET_DIR / "MID.xlsx"
    
    # Models and Training outputs
    MODELS_DIR: Path = BACKEND_DIR / "models"
    
    # OCR.space API Settings
    OCR_SPACE_API_KEY: str = os.getenv("OCR_SPACE_API_KEY", "")
    OCR_SPACE_URL: str = os.getenv("OCR_SPACE_URL", "https://api.ocr.space/parse/image")
    OCR_SPACE_ENGINE: str = os.getenv("OCR_SPACE_ENGINE", "2")
    OCR_SPACE_TIMEOUT_SECONDS: int = int(os.getenv("OCR_SPACE_TIMEOUT_SECONDS", "25"))
    
    # Google Gemini API Settings
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_TIMEOUT_SECONDS: int = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "30"))
    
    # Authentication & Security
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "medicare_ai_production_jwt_secret_key_2026_secure")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRATION_HOURS: int = int(os.getenv("JWT_EXPIRATION_HOURS", "72"))
    
    # OCR Settings
    OCR_LANGUAGES: list[str] = ["en"]
    OCR_GPU: bool = os.getenv("OCR_GPU", "false").lower() == "true"
    
    # Matching thresholds
    MATCH_SCORE_THRESHOLD: float = 60.0
    MAX_CANDIDATE_RESULTS: int = 5

settings = Settings()
