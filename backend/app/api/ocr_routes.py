import time
from fastapi import APIRouter, UploadFile, File, HTTPException
from ..services.ocr_service import ocr_service
from ..services.ocr_space_service import ocr_space_service
from ..services.nlp_parser import nlp_parser
from ..services.matcher_service import matcher_service
from ..db.models import OCRScanResult

router = APIRouter(prefix="/ocr", tags=["OCR & Recognition"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/tiff", "application/octet-stream"}

@router.post("/scan", response_model=OCRScanResult)
async def scan_medicine_strip(file: UploadFile = File(...)):
    """Accepts an image of a tablet strip, packaging, or medicine label.
    1. Preprocesses image and runs EasyOCR text extraction.
    2. Runs NLP entity extraction (brand, salts, strength, dosage form).
    3. Matches against the verified medicine database.
    4. Returns ranked medicine candidates and patient-friendly explanations.
    """
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {file.content_type}. Only JPG, PNG, and WebP images are supported."
        )

    t0 = time.time()
    try:
        contents = await file.read()
        if not contents or len(contents) < 100:
            raise HTTPException(status_code=400, detail="Empty or corrupt image file.")

        # 1. OCR Extraction (OCR.space primary with local EasyOCR fallback)
        if ocr_space_service.is_configured():
            parsed_res = ocr_space_service.parse_image_text(contents, mime_type=file.content_type or "image/jpeg")
            if parsed_res.get("success") and parsed_res.get("raw_text"):
                raw_text = parsed_res["raw_text"]
                detected_lines = parsed_res["detected_lines"]
            else:
                ocr_result = ocr_service.extract_text(contents)
                raw_text = ocr_result["raw_text"]
                detected_lines = ocr_result["detected_lines"]
        else:
            ocr_result = ocr_service.extract_text(contents)
            raw_text = ocr_result["raw_text"]
            detected_lines = ocr_result["detected_lines"]

        if not raw_text.strip():
            elapsed_ms = (time.time() - t0) * 1000
            return OCRScanResult(
                success=False,
                ocr_raw_text="",
                detected_lines=[],
                extracted_entities=nlp_parser.parse(""),
                matched_medicines=[],
                top_match=None,
                processing_time_ms=round(elapsed_ms, 2),
                message="No readable text detected. Please ensure the medicine strip is well-lit and in focus."
            )

        # 2. NLP Entity Extraction
        entities = nlp_parser.parse(raw_text, detected_lines=detected_lines)

        # 3. Database Matching
        matches = matcher_service.match(entities)
        top_match = matches[0] if matches else None

        elapsed_ms = (time.time() - t0) * 1000

        return OCRScanResult(
            success=True,
            ocr_raw_text=raw_text,
            detected_lines=detected_lines,
            extracted_entities=entities,
            matched_medicines=matches,
            top_match=top_match,
            processing_time_ms=round(elapsed_ms, 2),
            message="Medicine recognized successfully." if top_match else "Text extracted, but no matching medicine found in database."
        )

    except HTTPException:
        raise
    except Exception as e:
        elapsed_ms = (time.time() - t0) * 1000
        raise HTTPException(status_code=500, detail=f"Failed to process image: {str(e)}")

