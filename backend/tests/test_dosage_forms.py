"""
Tests for Dosage Form Resolution & Tablet vs Injection Disambiguation.
Ensures oral solid formulations (tablets, capsules) are never erroneously
predicted as parenteral injections.
"""

import pytest
from backend.app.services.nlp_parser import nlp_parser
from backend.app.services.matcher_service import matcher_service

def test_nlp_extracts_tablet_and_capsule_variants():
    # Various oral solid annotations
    samples = [
        ("Advent 625mg Tab", ["Tablet"]),
        ("Pantocid 40 DT", ["Tablet"]),
        ("Augmentin Film-Coated Tablets", ["Tablet"]),
        ("Dolo 650 Dispersible Tablet", ["Tablet"]),
        ("Evion 400 Soft Gelatin Capsules", ["Capsule"]),
        ("Becosules Caps 500mg", ["Capsule"]),
        ("Ceftriaxone Injection IP 1g", ["Injection"]),
        ("Amikacin 500mg/2ml Vial for I.V. Infusion", ["Injection"]),
    ]
    for text, expected_forms in samples:
        parsed = nlp_parser.parse(text)
        for ef in expected_forms:
            assert ef in parsed.dosage_forms, f"Failed to extract {ef} from '{text}'"

def test_tablet_never_matches_injection():
    """When target packaging is a tablet, injection candidates must be penalised."""
    parsed = nlp_parser.parse("Advent 625mg Tab")
    matches = matcher_service.match(parsed, max_results=5)
    assert len(matches) > 0
    top = matches[0]
    assert top.medicine.dosage_form == "Tablet"
    assert "injection" not in top.medicine.name.lower()
    assert "injection" not in (top.medicine.dosage_form or "").lower()

def test_unspecified_oral_strip_prefers_tablet_over_injection():
    """When brand has both tablet and injection, and no form is specified, prefer tablet."""
    parsed = nlp_parser.parse("Advent 600")
    matches = matcher_service.match(parsed, max_results=5)
    assert len(matches) > 0
    top = matches[0]
    # In an oral strip scanner, Advent Tablet must outscore Advent Injection
    assert top.medicine.dosage_form == "Tablet"

def test_genuine_injection_matches_injection():
    """When explicit injection text is provided, injection must be matched."""
    parsed = nlp_parser.parse("Advent 1.2gm Injection")
    matches = matcher_service.match(parsed, max_results=5)
    assert len(matches) > 0
    top = matches[0]
    assert top.medicine.dosage_form == "Injection"
