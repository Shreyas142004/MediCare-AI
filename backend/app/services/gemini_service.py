import json
import logging
import re
from typing import Tuple, Dict, Any, Optional
from google import genai
from google.genai import types

from ..core.config import settings
from ..schemas.gemini_schema import GeminiMedicineExtraction
from .ocr_service import ocr_service
from .nlp_parser import nlp_parser

logger = logging.getLogger(__name__)

GEMINI_ANALYSIS_PROMPT = """You are an expert pharmaceutical vision AI specializing in reading medicine packaging.
Analyze this image of the back side of a tablet strip, blister pack, or medicine package.

Extract ONLY information visibly printed on the package. 
Do not hallucinate, infer, or invent missing information.
If a field is not visible, return null.
Do not confuse manufacturing date (MFG) and expiry date (EXP).
If the image does NOT show a medicine or pharmaceutical product, set "is_medicine_package": false.

Return a valid JSON object matching this schema exactly:
{
  "is_medicine_package": true or false,
  "medicine_name": "Full commercial medicine name with strength if printed, e.g. Evion 400" or null,
  "brand_name": "Commercial brand name only, e.g. Evion" or null,
  "active_ingredient": "Primary active chemical substance, e.g. Tocopheryl Acetate" or null,
  "composition": "Full salt composition text e.g. Tocopheryl Acetate IP 400mg" or null,
  "strength": "Dosage strength e.g. 400mg, 500mg, 10ml" or null,
  "dosage_form": "Tablet, Capsule, Syrup, Injection, Drops, Gel, Ointment" or null,
  "manufacturer": "Manufacturing company name e.g. Procter & Gamble Health Ltd" or null,
  "manufacturing_date": "Visible MFG Date string or null",
  "expiry_date": "Visible EXP Date string or null",
  "batch_number": "Visible Batch/Lot number or null",
  "other_text": ["List of other notable visible lines like storage warnings, instructions"],
  "uncertain_fields": ["List of any fields where text was blurry, obscured, or uncertain"],
  "recognition_status": "success" or "uncertain" or "not_a_medicine" or "unreadable"
}
"""

class GeminiService:
    def __init__(self):
        self._client: Optional[genai.Client] = None

    def get_client(self) -> Optional[genai.Client]:
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY.strip() in ["", "your_gemini_api_key_here"]:
            return None
        if self._client is None:
            try:
                self._client = genai.Client(api_key=settings.GEMINI_API_KEY.strip())
                logger.info("Initialized Google GenAI Client with model %s", settings.GEMINI_MODEL)
            except Exception as e:
                logger.error("Failed to initialize Google GenAI Client: %s", e)
                self._client = None
        return self._client

    def is_configured(self) -> bool:
        return self.get_client() is not None

    def analyze_medicine_image(
        self, 
        image_bytes: bytes, 
        mime_type: str = "image/jpeg"
    ) -> Tuple[GeminiMedicineExtraction, str, bool]:
        """
        Analyzes the uploaded medicine packaging image using Gemini Multimodal Vision API.
        Falls back to local EasyOCR + NLP pipeline if Gemini API is unconfigured or unavailable.
        Returns:
            Tuple[GeminiMedicineExtraction, model_name_str, is_fallback_bool]
        """
        client = self.get_client()

        if client is not None:
            try:
                logger.info("Sending medicine image to Gemini API (%s)...", settings.GEMINI_MODEL)
                
                part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                config = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                )

                response = client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=[part, GEMINI_ANALYSIS_PROMPT],
                    config=config
                )

                if response and response.text:
                    cleaned_json = response.text.strip()
                    # Strip any accidental markdown formatting
                    if cleaned_json.startswith("```json"):
                        cleaned_json = cleaned_json[7:]
                    if cleaned_json.startswith("```"):
                        cleaned_json = cleaned_json[3:]
                    if cleaned_json.endswith("```"):
                        cleaned_json = cleaned_json[:-3]
                    cleaned_json = cleaned_json.strip()

                    parsed_dict = json.loads(cleaned_json)
                    extraction = GeminiMedicineExtraction(**parsed_dict)
                    logger.info("Gemini multimodal extraction successful: %s (%s)", extraction.medicine_name, extraction.recognition_status)
                    return extraction, settings.GEMINI_MODEL, False

            except Exception as e:
                logger.warning("Gemini API call failed (%s). Falling back to local OCR pipeline.", e)

        # Fallback to Local EasyOCR + NLP Pipeline
        logger.info("Processing image via Local OCR fallback pipeline...")
        ocr_result = ocr_service.extract_text(image_bytes)
        raw_text = ocr_result.get("raw_text", "")
        detected_lines = ocr_result.get("detected_lines", [])

        if not raw_text.strip():
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
                uncertain_fields=["all"],
                recognition_status="unreadable"
            ), "EasyOCR (Local Fallback)", True

        # Parse entities
        entities = nlp_parser.parse(raw_text, detected_lines=detected_lines)

        # Extract dates / batch if visible
        mfg_date = None
        exp_date = None
        batch_no = None
        for line in detected_lines:
            ll = line.lower()
            if "mfg" in ll:
                m = re.search(r'\b(?:\d{2}[\/\-]\d{4}|\d{2}[\/\-]\d{2})\b', line)
                if m: mfg_date = m.group(0)
            if "exp" in ll:
                m = re.search(r'\b(?:\d{2}[\/\-]\d{4}|\d{2}[\/\-]\d{2})\b', line)
                if m: exp_date = m.group(0)
            if any(b_kw in ll for b_kw in ["b.no", "batch", "lot"]):
                m = re.search(r'\b[A-Za-z0-9]{5,15}\b', line)
                if m: batch_no = m.group(0)

        brand = entities.brand_candidates[0] if entities.brand_candidates else None
        strength = entities.strengths[0] if entities.strengths else None
        form = entities.dosage_forms[0] if entities.dosage_forms else None
        salt = entities.active_salts[0] if entities.active_salts else None
        mfg = entities.manufacturer_hints[0] if entities.manufacturer_hints else None

        medicine_name = f"{brand} {strength or ''} {form or ''}".strip() if brand else None

        extraction = GeminiMedicineExtraction(
            is_medicine_package=True,
            medicine_name=medicine_name,
            brand_name=brand,
            active_ingredient=salt,
            composition=salt,
            strength=strength,
            dosage_form=form,
            manufacturer=mfg,
            manufacturing_date=mfg_date,
            expiry_date=exp_date,
            batch_number=batch_no,
            other_text=detected_lines[:10],
            uncertain_fields=[],
            recognition_status="success" if brand else "uncertain"
        )

        return extraction, "EasyOCR + NLP (Local Engine)", True

gemini_service = GeminiService()

