import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.services.ocr_space_service import ocr_space_service
from backend.app.main import app

TEST_IMAGE_PATH = Path(__file__).resolve().parent / "evion_test_strip.jpeg"

def test_ocr_space_service_configured():
    """Verifies OCR.space service detects the configured API key and masks it."""
    assert ocr_space_service.is_configured() is True
    masked = ocr_space_service._get_masked_key()
    assert "***" in masked
    assert settings.OCR_SPACE_API_KEY not in masked  # Never exposed in full

def test_ocr_space_live_parse_evion_strip():
    """Performs live OCR.space text parsing on the Evion 400 test strip image."""
    assert TEST_IMAGE_PATH.exists(), f"Missing test image at {TEST_IMAGE_PATH}"
    with open(TEST_IMAGE_PATH, "rb") as f:
        img_bytes = f.read()

    res = ocr_space_service.parse_image_text(img_bytes)
    # If free tier returned temporary 503 overload, retry once after short backoff
    if not res.get("success") and "503" in res.get("error", ""):
        time.sleep(2.5)
        res = ocr_space_service.parse_image_text(img_bytes)

    if res.get("success"):
        raw_text = res.get("raw_text", "")
        assert len(raw_text) > 30
        assert any(term in raw_text.lower() for term in ["evion", "vitamin", "tocopheryl", "400"])
    else:
        # Gracefully accept server-level throttling / timeout from OCR.space free tier
        err = res.get("error", "").lower()
        assert "503" in err or "time" in err or "throttle" in err

def test_ocr_space_medicine_details_extraction():
    """Tests NLP entity resolution from packaging image without guessing."""
    with open(TEST_IMAGE_PATH, "rb") as f:
        img_bytes = f.read()

    time.sleep(1.0)
    extraction, model_used, is_fallback = ocr_space_service.extract_medicine_details(img_bytes)
    assert extraction.is_medicine_package is True
    assert extraction.recognition_status == "success"
    assert extraction.brand_name is not None
    brand_or_other = extraction.brand_name.lower() + " " + " ".join(t.lower() for t in extraction.other_text)
    assert any(k in brand_or_other for k in ["evion", "vitam", "tocopheryl", "400"])
    assert extraction.strength is not None
    assert any(term in str(extraction.strength).lower() for term in ["400", "mg"])

def test_fastapi_scan_endpoint_with_ocr_space():
    """Tests the full FastAPI /api/medicine/scan endpoint backed by OCR.space."""
    client = TestClient(app)
    with open(TEST_IMAGE_PATH, "rb") as f:
        files = {"file": ("evion_test_strip.jpeg", f, "image/jpeg")}
        resp = client.post("/api/medicine/scan", files=files)

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["dataset_match"]["match_status"] in ("MATCHED", "UNCERTAIN")
    assert "Evion" in data["dataset_match"]["matched_medicine"]["name"]
    assert data["dataset_match"]["match_score"] >= 80.0

def test_unreadable_blank_image_no_guessing():
    """Verifies that unreadable or blank images do not produce guessed medicine names."""
    import cv2
    import numpy as np
    blank_img = np.full((200, 200, 3), 128, dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", blank_img)
    blank_jpeg_bytes = buf.tobytes()

    client = TestClient(app)
    files = {"file": ("blank.jpg", blank_jpeg_bytes, "image/jpeg")}
    resp = client.post("/api/medicine/scan", files=files)

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["recognition"]["status"] in ("NOT_A_MEDICINE", "UNREADABLE")
    assert data["extracted_package_details"]["medicine_name"] is None
    assert data["dataset_match"]["match_status"] == "NO_MATCH"

def test_invalid_empty_image_raises_400():
    """Verifies corrupted/empty files under 200 bytes are rejected with HTTP 400."""
    client = TestClient(app)
    files = {"file": ("empty.jpg", b"tiny corrupt string", "image/jpeg")}
    resp = client.post("/api/medicine/scan", files=files)
    assert resp.status_code == 400
