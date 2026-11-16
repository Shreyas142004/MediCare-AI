import logging
import cv2
import numpy as np
from typing import Union, List, Dict, Any, Tuple
import easyocr
from ..core.config import settings
from ..utils.image_utils import preprocess_medicine_image, load_image_from_bytes
from ..utils.text_utils import clean_ocr_text

logger = logging.getLogger(__name__)

class OCRService:
    _reader_instance: easyocr.Reader = None

    @classmethod
    def get_reader(cls) -> easyocr.Reader:
        if cls._reader_instance is None:
            logger.info("Initializing EasyOCR reader (languages=%s, gpu=%s)...", settings.OCR_LANGUAGES, settings.OCR_GPU)
            cls._reader_instance = easyocr.Reader(settings.OCR_LANGUAGES, gpu=settings.OCR_GPU)
        return cls._reader_instance

    @classmethod
    def _evaluate_orientation(cls, reader: easyocr.Reader, img_variant: np.ndarray) -> Tuple[List[Any], float]:
        """Evaluates an orientation based on pharmaceutical alphabetic words and confidence."""
        results = reader.readtext(img_variant)
        # We value tokens with >= 3 characters that contain letters (real words, not single digits)
        alpha_tokens = [r for r in results if len(r[1].strip()) >= 3 and any(c.isalpha() for c in r[1]) and r[2] >= 0.25]
        # Length-weighted confidence score
        total_score = sum(len(r[1].strip()) * r[2] for r in alpha_tokens)
        return results, total_score

    @classmethod
    def extract_text(cls, image_input: Union[bytes, str, np.ndarray]) -> Dict[str, Any]:
        """Runs orientation-aware, multi-stage OCR extraction on a medicine strip or packaging image.
        1. Tests cardinal orientations (0 deg, 90 deg CW, 180 deg, 270 deg) to overcome rotated camera angles.
        2. Applies CLAHE contrast enhancement for foil glare suppression.
        3. Extracts detected lines, bounding boxes, and confidence scores.
        """
        reader = cls.get_reader()

        # Load raw BGR image
        if isinstance(image_input, bytes):
            base_img = load_image_from_bytes(image_input)
        elif isinstance(image_input, str):
            base_img = cv2.imread(image_input)
            if base_img is None:
                raise FileNotFoundError(f"Could not load image at path: {image_input}")
        elif isinstance(image_input, np.ndarray):
            base_img = image_input
        else:
            raise ValueError("Unsupported image input type.")

        rotations = [
            ("0_deg", base_img),
            ("90_deg_CW", cv2.rotate(base_img, cv2.ROTATE_90_CLOCKWISE)),
            ("180_deg", cv2.rotate(base_img, cv2.ROTATE_180)),
            ("270_deg_CW", cv2.rotate(base_img, cv2.ROTATE_90_COUNTERCLOCKWISE))
        ]

        scored_rotations = []
        for rot_name, rot_img in rotations:
            preprocessed = preprocess_medicine_image(rot_img)
            res_clahe, score_clahe = cls._evaluate_orientation(reader, preprocessed["enhanced_contrast"])
            res_orig, score_orig = cls._evaluate_orientation(reader, preprocessed["original"])
            
            if score_clahe >= score_orig:
                scored_rotations.append((rot_name, res_clahe, score_clahe))
            else:
                scored_rotations.append((rot_name, res_orig, score_orig))

        # Sort descending by score
        scored_rotations.sort(key=lambda x: x[2], reverse=True)
        best_rot_name, best_results, best_score = scored_rotations[0]

        logger.info("OCR selected best orientation: %s (alpha score: %.2f)", best_rot_name, best_score)

        detected_lines: List[str] = []
        confidences: List[float] = []
        detailed_results: List[Dict[str, Any]] = []
        seen_lines_lower = set()

        # Primary orientation lines
        for bbox, text, conf in best_results:
            cleaned = text.strip()
            if cleaned and conf >= 0.20:
                t_low = cleaned.lower()
                if t_low not in seen_lines_lower:
                    seen_lines_lower.add(t_low)
                    detected_lines.append(cleaned)
                    confidences.append(float(conf))
                    bbox_serializable = [[float(pt[0]), float(pt[1])] for pt in bbox]
                    detailed_results.append({
                        "text": cleaned,
                        "confidence": round(float(conf), 3),
                        "bbox": bbox_serializable
                    })

        # Also incorporate secondary orientation lines if they have high confidence and don't duplicate
        # (e.g. batch / expiry / MRP numbers printed along the perpendicular margin)
        if len(scored_rotations) > 1:
            sec_rot_name, sec_results, sec_score = scored_rotations[1]
            if sec_score > 30.0:  # significant secondary text detected
                for bbox, text, conf in sec_results:
                    cleaned = text.strip()
                    if cleaned and conf >= 0.35 and len(cleaned) >= 4:
                        t_low = cleaned.lower()
                        if t_low not in seen_lines_lower and any(kw in t_low for kw in ["mrp", "mfg", "exp", "b.no", "capsule", "tablet", "batch", "rs."]):
                            seen_lines_lower.add(t_low)
                            detected_lines.append(cleaned)
                            confidences.append(float(conf))

        full_raw_text = " ".join(detected_lines)
        clean_full = clean_ocr_text(full_raw_text)
        avg_conf = (sum(confidences) / len(confidences)) if confidences else 0.0

        return {
            "raw_text": clean_full,
            "detected_lines": detected_lines,
            "detailed_results": detailed_results,
            "average_confidence": round(avg_conf, 3),
            "orientation": best_rot_name
        }

ocr_service = OCRService()
