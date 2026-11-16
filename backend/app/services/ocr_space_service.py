import re
import time
import logging
from typing import Tuple, Dict, Any, List, Optional
import requests

from ..core.config import settings
from ..schemas.gemini_schema import GeminiMedicineExtraction
from .nlp_parser import nlp_parser
from .ocr_service import ocr_service
from .gemini_service import gemini_service

logger = logging.getLogger(__name__)

class OCRSpaceService:
    def __init__(self):
        self.endpoint = settings.OCR_SPACE_URL
        self.timeout = settings.OCR_SPACE_TIMEOUT_SECONDS

    def is_configured(self) -> bool:
        """Returns True if a valid OCR.space API key is present."""
        key = settings.OCR_SPACE_API_KEY
        return bool(key and key.strip() not in ["", "your_ocr_space_api_key_here"])

    def _get_masked_key(self) -> str:
        """Helper to safely log the API key without exposure."""
        k = settings.OCR_SPACE_API_KEY.strip()
        if len(k) <= 6:
            return "***"
        return f"{k[:4]}***{k[-3:]}"

    def parse_image_text(
        self,
        image_bytes: bytes,
        filename: str = "medicine_strip.jpg",
        mime_type: str = "image/jpeg"
    ) -> Dict[str, Any]:
        """
        Sends image bytes to OCR.space API and extracts raw text and detected lines.
        Returns dictionary with raw_text, detected_lines, and status flags.
        """
        if not self.is_configured():
            raise ValueError("OCR.space API key is not configured in backend .env file.")

        logger.info(
            "Calling OCR.space API at %s (Key: %s, Engine: %s, Timeout: %ds)...",
            self.endpoint,
            self._get_masked_key(),
            settings.OCR_SPACE_ENGINE,
            self.timeout
        )

        payload = {
            "apikey": settings.OCR_SPACE_API_KEY.strip(),
            "language": "eng",
            "detectOrientation": "true",
            "scale": "true",
            "OCREngine": settings.OCR_SPACE_ENGINE,
            "isTable": "false"
        }

        files = {
            "file": (filename, image_bytes, mime_type)
        }

        try:
            response = requests.post(
                self.endpoint,
                files=files,
                data=payload,
                timeout=self.timeout
            )

            if response.status_code != 200:
                logger.warning("OCR.space returned HTTP status %d: %s", response.status_code, response.text[:200])
                return {
                    "success": False,
                    "error": f"OCR.space HTTP {response.status_code}",
                    "raw_text": "",
                    "detected_lines": []
                }

            result_json = response.json()
            is_errored = result_json.get("IsErroredOnProcessing", False)
            exit_code = result_json.get("OCRExitCode", 0)

            if is_errored or exit_code not in (1, 2):
                err_msg = result_json.get("ErrorMessage") or "Unknown processing error from OCR.space"
                logger.warning("OCR.space processing error: %s", err_msg)
                return {
                    "success": False,
                    "error": str(err_msg),
                    "raw_text": "",
                    "detected_lines": []
                }

            parsed_results = result_json.get("ParsedResults", [])
            if not parsed_results:
                return {
                    "success": True,
                    "raw_text": "",
                    "detected_lines": []
                }

            first_result = parsed_results[0]
            parsed_text = first_result.get("ParsedText", "").strip()
            lines = [l.strip() for l in parsed_text.splitlines() if l.strip()]

            logger.info("OCR.space extraction successful (%d lines read).", len(lines))
            return {
                "success": True,
                "raw_text": parsed_text,
                "detected_lines": lines,
                "exit_code": exit_code
            }

        except requests.Timeout:
            logger.warning("OCR.space request timed out after %d seconds.", self.timeout)
            return {
                "success": False,
                "error": f"OCR.space request timed out after {self.timeout}s.",
                "raw_text": "",
                "detected_lines": []
            }
        except Exception as e:
            logger.error("OCR.space API call exception: %s", e)
            return {
                "success": False,
                "error": str(e),
                "raw_text": "",
                "detected_lines": []
            }

    def extract_medicine_details(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg"
    ) -> Tuple[GeminiMedicineExtraction, str, bool]:
        """
        Processes medicine strip image via OCR.space, extracts packaging entities
        and dates using NLP parser without guessing unreadable details.
        Falls back to local EasyOCR if OCR.space encounters a network error or timeout.
        Returns:
            Tuple[GeminiMedicineExtraction, model_name, is_fallback]
        """
        ocr_res = self.parse_image_text(
            image_bytes=image_bytes,
            mime_type=mime_type
        )

        raw_text = ocr_res.get("raw_text", "").strip()
        detected_lines = ocr_res.get("detected_lines", [])

        # If OCR.space failed with network error, throttling or timeout, attempt fallback
        if not ocr_res.get("success") and not raw_text:
            logger.info("OCR.space unavailable (%s). Attempting fallback pipeline...", ocr_res.get("error"))
            
            # Primary Fallback: Gemini Vision if configured
            if gemini_service.is_configured():
                try:
                    logger.info("Falling back to Gemini Vision API (%s)...", settings.GEMINI_MODEL)
                    ext, g_model, _ = gemini_service.analyze_medicine_image(image_bytes, mime_type)
                    return ext, f"{g_model} (Fallback)", True
                except Exception as ge:
                    logger.warning("Gemini fallback exception: %s", ge)

            # Secondary Fallback: Local Orientation-Aware EasyOCR
            local_res = ocr_service.extract_text(image_bytes)
            raw_text = local_res.get("raw_text", "").strip()
            detected_lines = local_res.get("detected_lines", [])
            model_name = "EasyOCR (Local Fallback)"
            is_fallback = True
        else:
            model_name = f"OCR.space (Engine {settings.OCR_SPACE_ENGINE})"
            is_fallback = False

        # Case 1: Absolutely unreadable or empty text
        if not raw_text:
            return GeminiMedicineExtraction(
                is_medicine_package=False,
                medicine_name=None,
                brand_name=None,
                active_ingredient=None,
                composition=None,
                strength=None,
                dosage_form=None,
                manufacturer=None,
                manufacturing_date=None,
                expiry_date=None,
                batch_number=None,
                other_text=[],
                uncertain_fields=["all_text_unreadable"],
                recognition_status="unreadable"
            ), model_name, is_fallback

        # Step 2: Extract explicit package dates and batch number from text lines
        mfg_date = None
        exp_date = None
        batch_no = None

        for line in detected_lines:
            ll = line.lower()
            # Manufacturing Date
            if any(k in ll for k in ["mfg", "mfd", "mig", "manufactured"]):
                m = re.search(r'(?:mfg|mfd|mig|date)[:\s\.]*([0-9]{1,2}[\/\-\.][0-9]{2,4})', line, re.IGNORECASE)
                if not m:
                    m = re.search(r'\b(?:\d{2}[\/\-]\d{4}|\d{2}[\/\-]\d{2})\b', line)
                if m and not mfg_date:
                    mfg_date = m.group(1) if m.lastindex else m.group(0)

            # Expiry Date
            if any(k in ll for k in ["exp", "expiry", "val"]):
                m = re.search(r'(?:exp|expiry)[:\s\.]*([0-9]{1,2}[\/\-\.][0-9]{2,4})', line, re.IGNORECASE)
                if not m:
                    m = re.search(r'\b(?:\d{2}[\/\-]\d{4}|\d{2}[\/\-]\d{2})\b', line)
                if m and not exp_date:
                    exp_date = m.group(1) if m.lastindex else m.group(0)

            # Batch Number
            if any(k in ll for k in ["b.no", "batch", "lot"]):
                m = re.search(r'(?:b\.?no|batch|lot)[:\s\.]*([A-Za-z0-9\-]{4,15})', line, re.IGNORECASE)
                if not m:
                    m = re.search(r'\b[A-Za-z0-9]{5,15}\b', line)
                if m and not batch_no:
                    batch_no = m.group(1) if m.lastindex else m.group(0)

        # Step 3: Run domain NLP parser to extract entities
        entities = nlp_parser.parse(raw_text, detected_lines=detected_lines)

        # Detect registered trademarks (e.g. Evion®)
        tm_brands = re.findall(r'\b([A-Za-z0-9\-]{3,})[\s]*[®™]', raw_text)

        ordered_brands: List[str] = list(tm_brands)
        for b in entities.brand_candidates:
            b_clean = b.strip()
            if b_clean not in ordered_brands and not b_clean.lower().startswith("vitamin") and not b_clean.lower().startswith("soft"):
                ordered_brands.append(b_clean)
        for b in entities.brand_candidates:
            b_clean = b.strip()
            if b_clean not in ordered_brands:
                ordered_brands.append(b_clean)

        brand = ordered_brands[0] if ordered_brands else None
        strength = entities.strengths[0] if entities.strengths else None
        form = entities.dosage_forms[0] if entities.dosage_forms else None
        salt = entities.active_salts[0] if entities.active_salts else None
        mfg = entities.manufacturer_hints[0] if entities.manufacturer_hints else None

        # Build clean medicine name strictly from visible items (never guess!)
        if brand and strength and form:
            med_name = f"{brand} {strength} {form}"
        elif brand and strength:
            med_name = f"{brand} {strength}"
        elif brand:
            med_name = brand
        else:
            med_name = None

        # Determine pharmaceutical package likelihood
        has_pharma_hints = bool(
            brand or salt or form or strength or
            any(w in raw_text.lower() for w in ["capsule", "tablet", "syrup", "dosage", "suspension", "mg", "usp", "ip"])
        )

        uncertain_fields = []
        if not mfg_date:
            uncertain_fields.append("Manufacturing date not visible on image")
        if not exp_date:
            uncertain_fields.append("Expiry date not visible on image")
        if not batch_no:
            uncertain_fields.append("Batch/Lot number not visible on image")
        if not brand:
            uncertain_fields.append("Brand name could not be reliably determined")

        status = "success" if (brand and has_pharma_hints) else ("uncertain" if has_pharma_hints else "not_a_medicine")

        extraction = GeminiMedicineExtraction(
            is_medicine_package=has_pharma_hints,
            medicine_name=med_name,
            brand_name=brand,
            active_ingredient=salt,
            composition=salt,
            strength=strength,
            dosage_form=form,
            manufacturer=mfg,
            manufacturing_date=mfg_date,
            expiry_date=exp_date,
            batch_number=batch_no,
            other_text=detected_lines[:15],
            uncertain_fields=uncertain_fields,
            recognition_status=status
        )

        return extraction, model_name, is_fallback

ocr_space_service = OCRSpaceService()
