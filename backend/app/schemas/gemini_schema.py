from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class GeminiMedicineExtraction(BaseModel):
    """Structured extraction of visible packaging details parsed by Gemini Multimodal API."""
    is_medicine_package: bool = Field(default=True, description="Whether the image represents a medicine package, strip, blister, or bottle")
    medicine_name: Optional[str] = Field(default=None, description="Commercial medicine name visible on the package")
    brand_name: Optional[str] = Field(default=None, description="Commercial brand name")
    active_ingredient: Optional[str] = Field(default=None, description="Active chemical ingredient/substance")
    composition: Optional[str] = Field(default=None, description="Full salt formulation and strength clause")
    strength: Optional[str] = Field(default=None, description="Dosage strength (e.g. 400mg, 500 mg, 10 ml)")
    dosage_form: Optional[str] = Field(default=None, description="Dosage form (e.g. Tablet, Capsule, Syrup, Injection)")
    manufacturer: Optional[str] = Field(default=None, description="Manufacturing pharmaceutical company")
    manufacturing_date: Optional[str] = Field(default=None, description="MFG Date if clearly readable")
    expiry_date: Optional[str] = Field(default=None, description="EXP Date if clearly readable")
    batch_number: Optional[str] = Field(default=None, description="Batch / Lot number if readable")
    other_text: List[str] = Field(default_factory=list, description="Other notable visible text lines (storage, directions, etc.)")
    uncertain_fields: List[str] = Field(default_factory=list, description="List of fields where text was partially obscured or ambiguous")
    recognition_status: str = Field(default="success", description="Status flag: success, uncertain, not_a_medicine, unreadable")

class RecognitionInfo(BaseModel):
    status: str
    model_used: str
    is_medicine_package: bool
    confidence: str
    processing_time_ms: float

class DatasetMatchInfo(BaseModel):
    match_status: str  # 'MATCHED', 'MULTIPLE_CANDIDATES', 'NO_MATCH', 'UNCERTAIN'
    match_score: float
    match_type: str
    matched_medicine: Optional[Dict[str, Any]] = None
    alternative_matches: List[Dict[str, Any]] = Field(default_factory=list)

class MedicineScanResponse(BaseModel):
    success: bool
    message: str
    recognition: RecognitionInfo
    extracted_package_details: GeminiMedicineExtraction
    dataset_match: DatasetMatchInfo
    medicine_information: Optional[Dict[str, Any]] = None
    warnings_and_uncertain_fields: List[str] = Field(default_factory=list)

