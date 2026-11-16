import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from ..schemas.gemini_schema import (
    GeminiMedicineExtraction,
    RecognitionInfo,
    DatasetMatchInfo,
    MedicineScanResponse
)
from ..db.models import ParsedEntities, MatchCandidate
from ..services.matcher_service import matcher_service
from ..services.explanation_service import explanation_service
from ..services.nlp_parser import nlp_parser
from ..db.mongo_client import mongo_manager

logger = logging.getLogger(__name__)

class MedicineService:
    @staticmethod
    def process_extracted_medicine(
        extraction: GeminiMedicineExtraction,
        model_name: str,
        processing_time_ms: float,
        user_id: Optional[str] = None
    ) -> MedicineScanResponse:
        """
        Takes structured packaging details extracted from the image,
        performs normalization and similarity matching against the medicine dataset,
        generates simple language guidance, and returns a verified MedicineScanResponse.
        """
        # Case 1: Image is not a medicine package
        if not extraction.is_medicine_package:
            return MedicineScanResponse(
                success=False,
                message="The uploaded image does not appear to be a medicine package or tablet strip. Please upload a clear photo of the printed back side of a medicine package.",
                recognition=RecognitionInfo(
                    status="NOT_A_MEDICINE",
                    model_used=model_name,
                    is_medicine_package=False,
                    confidence="LOW",
                    processing_time_ms=round(processing_time_ms, 2)
                ),
                extracted_package_details=extraction,
                dataset_match=DatasetMatchInfo(
                    match_status="NO_MATCH",
                    match_score=0.0,
                    match_type="none"
                ),
                medicine_information=None,
                warnings_and_uncertain_fields=["Image rejected: Not a recognized pharmaceutical product."]
            )

        # Case 2: Unreadable text
        if extraction.recognition_status == "unreadable" or (not extraction.medicine_name and not extraction.brand_name and not extraction.composition):
            return MedicineScanResponse(
                success=False,
                message="Text on the medicine packaging could not be clearly read. Please ensure proper lighting, avoid glare, and keep the packaging in sharp focus.",
                recognition=RecognitionInfo(
                    status="UNREADABLE",
                    model_used=model_name,
                    is_medicine_package=True,
                    confidence="LOW",
                    processing_time_ms=round(processing_time_ms, 2)
                ),
                extracted_package_details=extraction,
                dataset_match=DatasetMatchInfo(
                    match_status="NO_MATCH",
                    match_score=0.0,
                    match_type="none"
                ),
                medicine_information=None,
                warnings_and_uncertain_fields=["Image text unreadable or severely obscured."]
            )

        # Step 3: Prepare parsed entities for dataset matcher
        brand_candidates = []
        if extraction.brand_name:
            brand_candidates.append(extraction.brand_name)
        if extraction.medicine_name and extraction.medicine_name not in brand_candidates:
            brand_candidates.append(extraction.medicine_name)

        if extraction.other_text:
            extra_entities = nlp_parser.parse("\n".join(extraction.other_text), detected_lines=extraction.other_text)
            for b in extra_entities.brand_candidates:
                if b not in brand_candidates and len(b) >= 3:
                    brand_candidates.append(b)

        active_salts = []
        if extraction.active_ingredient:
            active_salts.append(extraction.active_ingredient)
        if extraction.composition and extraction.composition not in active_salts:
            active_salts.append(extraction.composition)

        strengths = [extraction.strength] if extraction.strength else []
        dosage_forms = [extraction.dosage_form] if extraction.dosage_form else []
        mfg_hints = [extraction.manufacturer] if extraction.manufacturer else []

        normalized_query = f"{extraction.brand_name or extraction.medicine_name or ''} {extraction.strength or ''}".strip()

        entities = ParsedEntities(
            brand_candidates=brand_candidates,
            active_salts=active_salts,
            strengths=strengths,
            dosage_forms=dosage_forms,
            manufacturer_hints=mfg_hints,
            normalized_query=normalized_query
        )

        # Step 4: Query dataset via Hybrid Matcher
        matches: List[MatchCandidate] = matcher_service.match(entities, max_results=5)

        warnings: List[str] = list(extraction.uncertain_fields or [])
        if extraction.recognition_status == "uncertain":
            warnings.append("Packaging text had minor ambiguity; verified candidate shown below.")

        top_match: Optional[MatchCandidate] = matches[0] if matches else None

        # Defense-in-depth: Never allow an Injection to beat a Tablet/Capsule when packaging is oral solid
        target_is_oral = any(f.lower() in ["tablet", "capsule", "caplet", "dt", "sr", "er"] for f in dosage_forms)
        if target_is_oral and top_match and "injection" in (top_match.medicine.dosage_form or "").lower():
            for alt in matches[1:]:
                alt_form = (alt.medicine.dosage_form or "").lower()
                if "tablet" in alt_form or "capsule" in alt_form:
                    matches.remove(alt)
                    matches.insert(0, alt)
                    top_match = alt
                    break

        # Build response sections
        if top_match and top_match.match_score >= 60.0:
            match_status = "MATCHED" if top_match.match_score >= 80.0 else "UNCERTAIN"
            matched_med_dict = top_match.medicine.model_dump()

            # Preserve extracted package-specific details separately
            med_info = top_match.simple_explanation.model_dump()

            dataset_match = DatasetMatchInfo(
                match_status=match_status,
                match_score=top_match.match_score,
                match_type=top_match.match_type,
                matched_medicine=matched_med_dict,
                alternative_matches=[m.medicine.model_dump() for m in matches[1:4]]
            )

            response = MedicineScanResponse(
                success=True,
                message="Medicine recognized and matched successfully with verified database.",
                recognition=RecognitionInfo(
                    status="SUCCESS",
                    model_used=model_name,
                    is_medicine_package=True,
                    confidence=top_match.confidence,
                    processing_time_ms=round(processing_time_ms, 2)
                ),
                extracted_package_details=extraction,
                dataset_match=dataset_match,
                medicine_information=med_info,
                warnings_and_uncertain_fields=warnings
            )
        else:
            # Packaging read successfully, but not present in dataset
            dataset_match = DatasetMatchInfo(
                match_status="NO_MATCH",
                match_score=top_match.match_score if top_match else 0.0,
                match_type="none",
                matched_medicine=None,
                alternative_matches=[m.medicine.model_dump() for m in matches[:3]] if matches else []
            )

            # Build a best-effort explanation from packaging details
            placeholder_info = {
                "medicine_name": extraction.medicine_name or extraction.brand_name or "Uncataloged Medicine",
                "active_ingredients": extraction.composition or extraction.active_ingredient or "Information not available in dataset.",
                "dosage_and_form": f"{extraction.dosage_form or 'Medicine'} ({extraction.strength or 'Standard'})",
                "primary_uses": ["This specific commercial brand was not found in our 149,000+ medicine catalog.", "Please consult your doctor or pharmacist for medical uses."],
                "how_it_works": "Mechanism details not available in dataset catalog.",
                "how_to_take": "Take strictly as prescribed on packaging or by physician.",
                "common_side_effects": ["Side effect profile not available in local catalog."],
                "critical_safety_alerts": {},
                "habit_forming_warning": False,
                "manufacturer": extraction.manufacturer or "Printed on packaging",
                "approx_price": "Not available"
            }

            warnings.append("Medicine details extracted from packaging, but no exact catalog record matched.")

            response = MedicineScanResponse(
                success=True,
                message="Packaging details read successfully. However, this specific brand entry was not found in our catalog.",
                recognition=RecognitionInfo(
                    status="EXTRACTED_NO_DATASET_MATCH",
                    model_used=model_name,
                    is_medicine_package=True,
                    confidence="MEDIUM" if extraction.brand_name else "LOW",
                    processing_time_ms=round(processing_time_ms, 2)
                ),
                extracted_package_details=extraction,
                dataset_match=dataset_match,
                medicine_information=placeholder_info,
                warnings_and_uncertain_fields=warnings
            )

        # Step 5: Log scan into MongoDB scanhistories
        try:
            scan_log_entry = {
                "user_id": user_id or "anonymous",
                "timestamp": datetime.utcnow().isoformat(),
                "medicine_name": extraction.medicine_name or extraction.brand_name,
                "brand_name": extraction.brand_name,
                "strength": extraction.strength,
                "dosage_form": extraction.dosage_form,
                "matched_name": top_match.medicine.name if top_match else None,
                "match_score": top_match.match_score if top_match else 0.0,
                "confidence": top_match.confidence if top_match else "LOW",
                "model_used": model_name,
                "processing_time_ms": processing_time_ms
            }
            mongo_manager.log_scan_history(scan_log_entry)
        except Exception as e:
            logger.warning("Could not persist scan history: %s", e)

        return response

medicine_service = MedicineService()

