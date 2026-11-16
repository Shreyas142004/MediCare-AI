import os
import sys
import pytest
import numpy as np
import cv2
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.main import app
from backend.app.core.config import settings
from backend.app.db.database import get_db_connection, search_medicines_fts, get_medicine_by_id, get_total_medicine_count
from backend.app.services.nlp_parser import nlp_parser
from backend.app.services.matcher_service import matcher_service
from backend.app.services.explanation_service import explanation_service
from backend.app.utils.image_utils import preprocess_medicine_image
from backend.app.utils.text_utils import clean_ocr_text, normalize_for_matching

client = TestClient(app)

def test_database_connection_and_count():
    """Verify that SQLite DB exists and contains indexed medicines."""
    count = get_total_medicine_count()
    assert count > 100000, f"Expected >100,000 medicines, found {count}"

def test_fts5_search():
    """Verify full text search works for paracetamol."""
    results = search_medicines_fts("Paracetamol 500", limit=5)
    assert len(results) > 0
    assert any("paracetamol" in r["name"].lower() for r in results)

def test_nlp_entity_parser():
    """Verify regex and rule-based entity parsing from simulated OCR text."""
    sample_ocr = (
        "ANDOL 0.5mg Tablets IP\n"
        "Each uncoated tablet contains: Haloperidol IP 0.5 mg\n"
        "Mfg Lic No: 25/UA/2015\n"
        "Store below 25 C. Protect from light.\n"
        "Mfg by: Sun Pharma Laboratories Ltd"
    )
    entities = nlp_parser.parse(sample_ocr)
    
    # Assertions
    assert any("0.5mg" in s.lower().replace(" ", "") for s in entities.strengths)
    assert "Tablet" in entities.dosage_forms
    assert any("haloperidol" in s.lower() for s in entities.active_salts)
    assert any("andol" in b.lower() for b in entities.brand_candidates)

def test_medicine_matcher():
    """Verify hybrid matcher finds the exact medicine for noisy OCR entities."""
    sample_ocr = "Andol 0.5mg Haloperidol Tablets"
    entities = nlp_parser.parse(sample_ocr)
    matches = matcher_service.match(entities, max_results=3)
    
    assert len(matches) > 0
    top = matches[0]
    assert "andol" in top.medicine.name.lower()
    assert top.match_score >= 80.0
    assert top.confidence in ["HIGH", "MEDIUM"]
    assert top.simple_explanation is not None

def test_explanation_service():
    """Verify that patient-friendly explanation is properly constructed."""
    med = get_medicine_by_id(1)
    assert med is not None
    explanation = explanation_service.generate_explanation(med)
    
    assert explanation.medicine_name == med["name"]
    assert len(explanation.primary_uses) > 0
    assert len(explanation.how_it_works) > 0
    assert len(explanation.how_to_take) > 0
    assert isinstance(explanation.critical_safety_alerts, dict)

def test_image_preprocessing_pipeline():
    """Verify that synthetic image input is processed through CLAHE, denoising, and thresholding."""
    synthetic_img = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.putText(synthetic_img, "TEST", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    variants = preprocess_medicine_image(synthetic_img)
    assert "original" in variants
    assert "grayscale" in variants
    assert "enhanced_contrast" in variants
    assert "thresholded" in variants
    assert variants["enhanced_contrast"].shape == (100, 100)
    assert variants["thresholded"].shape == (100, 100)

def test_api_health_endpoint():
    """Verify GET /api/health."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["database"]["total_medicines"] > 100000

def test_api_search_endpoint():
    """Verify GET /api/medicine/search matches by generic salt or brand name."""
    res = client.get("/api/medicine/search?q=Metformin 500")
    assert res.status_code == 200
    data = res.json()
    assert len(data) > 0
    first_med = data[0]["medicine"]
    name_or_comp = (first_med["name"] + " " + (first_med["composition"] or "")).lower()
    assert "metformin" in name_or_comp

def test_api_ocr_scan_endpoint_with_image():
    """Verify POST /api/ocr/scan with synthetic medicine label image."""
    test_img = np.ones((120, 400, 3), dtype=np.uint8) * 240
    cv2.putText(test_img, "Andol 0.5mg", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
    cv2.putText(test_img, "Haloperidol Tablets IP", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    
    _, img_encoded = cv2.imencode(".png", test_img)
    img_bytes = img_encoded.tobytes()
    
    response = client.post(
        "/api/ocr/scan",
        files={"file": ("test_strip.png", img_bytes, "image/png")}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["ocr_raw_text"]) > 0
    assert len(data["matched_medicines"]) > 0
    assert data["top_match"] is not None
    assert "andol" in data["top_match"]["medicine"]["name"].lower()
