from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from ..db.database import get_medicine_by_id, search_medicines_fts
from ..services.explanation_service import explanation_service
from ..services.nlp_parser import nlp_parser
from ..services.matcher_service import matcher_service
from ..db.models import MedicineRecord, SimpleExplanation, MatchCandidate

router = APIRouter(prefix="/medicine", tags=["Medicines"])

@router.get("/search", response_model=List[MatchCandidate])
def search_medicines(
    q: str = Query(..., min_length=2, description="Search keyword, brand name, or salt"),
    limit: int = Query(5, ge=1, le=20)
):
    """Searches medicines by brand, active salt, composition, or generic query."""
    entities = nlp_parser.parse(q)
    matches = matcher_service.match(entities, max_results=limit)
    return matches

@router.get("/{med_id}")
def get_medicine(med_id: int):
    """Retrieves full clinical records and simple-language explanation by medicine ID."""
    med = get_medicine_by_id(med_id)
    if not med:
        raise HTTPException(status_code=404, detail=f"Medicine with ID {med_id} not found.")
        
    explanation = explanation_service.generate_explanation(med)
    return {
        "medicine": med,
        "simple_explanation": explanation
    }

