import time
import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Header, HTTPException, status
from ..schemas.gemini_schema import MedicineScanResponse
from ..services.gemini_service import gemini_service
from ..services.ocr_space_service import ocr_space_service
from ..services.medicine_service import medicine_service
from ..db.mongo_client import mongo_manager

from ..core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/medicine", tags=["Medicine Scanner & Recognition"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "application/octet-stream"}
MAX_FILE_SIZE = 12 * 1024 * 1024  # 12 MB limit

@router.post("/scan", response_model=MedicineScanResponse)
async def scan_medicine_package(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None)
):
    """
    Primary MediCare Multimodal Recognition Endpoint.
    1. Receives image of tablet strip or medicine package.
    2. Validates format and size.
    3. Analyzes image using Google Gemini Multimodal Vision API.
    4. Normalizes and validates extracted packaging details with Pydantic.
    5. Matches against the 149,000+ medicine dataset (MongoDB / SQLite).
    6. Generates patient-friendly explanations in simple language.
    7. Logs scan into scan history.
    """
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{file.content_type}'. Please upload a JPG, PNG, or WebP image."
        )

    t0 = time.time()
    try:
        contents = await file.read()
        if not contents or len(contents) < 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty or corrupted image file uploaded."
            )
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Image size exceeds maximum limit of 12MB. Please compress or resize."
            )

        # Extract user_id from token if present
        user_id = "anonymous"
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:].strip()
            from ..services.auth_service import decode_access_token
            payload = decode_access_token(token)
            if payload:
                user_id = payload.get("sub", "anonymous")

        # Step 1: Run OCR / Multimodal Analysis
        # Use OCR.space if configured, else Gemini Vision, with local EasyOCR fallback
        if ocr_space_service.is_configured():
            extraction, model_used, is_fallback = ocr_space_service.extract_medicine_details(
                image_bytes=contents,
                mime_type=file.content_type or "image/jpeg"
            )
        else:
            extraction, model_used, is_fallback = gemini_service.analyze_medicine_image(
                image_bytes=contents,
                mime_type=file.content_type or "image/jpeg"
            )

        elapsed_ms = (time.time() - t0) * 1000

        # Step 2: Match against Medicine Dataset & Formulate Response
        response = medicine_service.process_extracted_medicine(
            extraction=extraction,
            model_name=model_used,
            processing_time_ms=elapsed_ms,
            user_id=user_id
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in scan_medicine_package endpoint: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during medicine scanning: {str(e)}"
        )

@router.get("/scans/history")
def get_scan_history(limit: int = 20, authorization: Optional[str] = Header(None)):
    """Fetches recent medicine scans for the dashboard and scan history page."""
    user_id = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        from ..services.auth_service import decode_access_token
        payload = decode_access_token(token)
        if payload:
            user_id = payload.get("sub")

    db = mongo_manager.get_db()
    if db is None:
        return {"scans": [], "total": 0}

    query = {}
    if user_id:
        query = {"$or": [{"user_id": user_id}, {"user_id": "anonymous"}]}

    cursor = db[settings.MONGO_COLLECTION_SCANS].find(query).sort("timestamp", -1).limit(limit)
    scans = []
    for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        scans.append(doc)

    return {"scans": scans, "total": len(scans)}

@router.delete("/scans/{scan_id}")
def delete_scan_record(scan_id: str, authorization: Optional[str] = Header(None)):
    """Deletes a scan entry from history."""
    db = mongo_manager.get_db()
    if db is None:
        return {"success": True, "message": "Record removed."}
    from bson import ObjectId
    try:
        db[settings.MONGO_COLLECTION_SCANS].delete_one({"_id": ObjectId(scan_id)})
        return {"success": True, "message": "Scan deleted from history."}
    except Exception as e:
        logger.warning("Error deleting scan record: %s", e)
        return {"success": False, "message": str(e)}
