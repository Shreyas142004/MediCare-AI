from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class ParsedEntities(BaseModel):
    brand_candidates: List[str] = Field(default_factory=list, description="Extracted commercial brand candidate names")
    active_salts: List[str] = Field(default_factory=list, description="Detected active pharmaceutical substances")
    strengths: List[str] = Field(default_factory=list, description="Extracted strengths (e.g. 500mg, 10mg/ml)")
    dosage_forms: List[str] = Field(default_factory=list, description="Detected dosage forms (e.g. Tablet, Capsule)")
    manufacturer_hints: List[str] = Field(default_factory=list, description="Detected manufacturer hints or abbreviations")
    normalized_query: str = Field("", description="Consolidated normalized search query")

class MedicineRecord(BaseModel):
    id: int
    name: str
    brand_name: Optional[str] = None
    dosage_form: Optional[str] = None
    strength: Optional[str] = None
    composition: Optional[str] = None
    manufacturer: Optional[str] = "Not specified"
    price: Optional[str] = "Not specified"
    introduction: Optional[str] = None
    uses: Optional[str] = None
    benefits: Optional[str] = None
    side_effects: Optional[str] = None
    how_to_use: Optional[str] = None
    how_works: Optional[str] = None
    quick_tips: Optional[str] = None
    habit_forming: Optional[str] = "No"
    therapeutic_class: Optional[str] = None
    safety_alcohol: Optional[str] = None
    safety_pregnancy: Optional[str] = None
    safety_breastfeeding: Optional[str] = None
    safety_driving: Optional[str] = None
    safety_kidney: Optional[str] = None
    safety_liver: Optional[str] = None
    drug_interactions: Optional[str] = None
    link: Optional[str] = None

class SimpleExplanation(BaseModel):
    medicine_name: str
    active_ingredients: str
    dosage_and_form: str
    primary_uses: List[str]
    how_it_works: str
    how_to_take: str
    common_side_effects: List[str]
    critical_safety_alerts: Dict[str, str]
    habit_forming_warning: bool
    manufacturer: Optional[str] = None
    approx_price: Optional[str] = None

class MatchCandidate(BaseModel):
    medicine: MedicineRecord
    match_score: float
    match_type: str  # 'exact_name', 'fuzzy_name', 'salt_strength_match', 'fts_query'
    confidence: str  # 'HIGH', 'MEDIUM', 'LOW'
    simple_explanation: SimpleExplanation

class OCRScanResult(BaseModel):
    success: bool
    ocr_raw_text: str
    detected_lines: List[str]
    extracted_entities: ParsedEntities
    matched_medicines: List[MatchCandidate]
    top_match: Optional[MatchCandidate] = None
    processing_time_ms: float
    message: Optional[str] = None

