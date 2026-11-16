import re
from typing import Dict, Any, List
from ..db.models import MedicineRecord, SimpleExplanation

def clean_bullet_points(raw_text: str) -> List[str]:
    """Splits newline or comma-separated text into clean bullet points."""
    if not raw_text:
        return []
    items = []
    # Replace common delimiters
    lines = re.split(r'[\r\n\t\•\-\*]+|(?<=[a-z])\.\s+(?=[A-Z])', raw_text)
    for line in lines:
        cleaned = line.strip(" ,.-:;")
        if cleaned and len(cleaned) > 2 and cleaned.lower() not in ["none", "na", "null"]:
            items.append(cleaned)
    return items

class ExplanationService:
    @staticmethod
    def generate_explanation(med: Dict[str, Any]) -> SimpleExplanation:
        name = med.get("name", "Unknown Medicine")
        composition = med.get("composition", "Not specified")
        dosage_form = med.get("dosage_form", "")
        strength = med.get("strength", "")
        
        form_strength = f"{dosage_form} ({strength})".strip(" ()") if (dosage_form or strength) else "Standard Dosage"

        # 1. Parse primary uses
        raw_uses = med.get("uses", "") or med.get("introduction", "")
        parsed_uses = []
        if raw_uses:
            for item in clean_bullet_points(raw_uses)[:4]:
                # Remove boilerplate phrases like "Treatment of"
                clean_item = re.sub(r'^(treatment of|prevention of|management of)\s+', '', item, flags=re.IGNORECASE)
                parsed_uses.append(clean_item.capitalize())
        if not parsed_uses:
            parsed_uses = ["Used as prescribed by a licensed healthcare professional."]

        # 2. How it works
        how_works = med.get("how_works") or ""
        if not how_works or len(how_works) < 10:
            intro = med.get("introduction", "")
            how_works = intro if intro else "Works by delivering the active therapeutic compounds to target tissues to alleviate symptoms."

        # 3. How to take
        how_to_take = med.get("how_to_use") or ""
        if not how_to_take or len(how_to_take) < 10:
            how_to_take = f"Take this {dosage_form or 'medicine'} strictly in the dose and duration advised by your doctor. Swallow it whole with water. Do not crush or chew."

        # 4. Common side effects
        raw_side = med.get("side_effects", "")
        common_side_effects = []
        if raw_side:
            for s in clean_bullet_points(raw_side)[:6]:
                # Filter out generic filler sentences
                if "most side effects" not in s.lower() and "consult your doctor" not in s.lower():
                    common_side_effects.append(s)
        if not common_side_effects:
            common_side_effects = ["Generally well-tolerated. Consult your physician if you experience unexpected symptoms."]

        # 5. Critical Safety Alerts
        critical_alerts: Dict[str, str] = {}
        
        if med.get("safety_alcohol"):
            critical_alerts["Alcohol"] = med["safety_alcohol"]
        if med.get("safety_pregnancy"):
            critical_alerts["Pregnancy"] = med["safety_pregnancy"]
        if med.get("safety_breastfeeding"):
            critical_alerts["Breastfeeding"] = med["safety_breastfeeding"]
        if med.get("safety_driving"):
            critical_alerts["Driving & Machinery"] = med["safety_driving"]
        if med.get("safety_kidney"):
            critical_alerts["Kidney"] = med["safety_kidney"]
        if med.get("safety_liver"):
            critical_alerts["Liver"] = med["safety_liver"]

        habit_flag = str(med.get("habit_forming", "No")).strip().lower() == "yes"

        return SimpleExplanation(
            medicine_name=name,
            active_ingredients=composition,
            dosage_and_form=form_strength,
            primary_uses=parsed_uses,
            how_it_works=how_works,
            how_to_take=how_to_take,
            common_side_effects=common_side_effects,
            critical_safety_alerts=critical_alerts,
            habit_forming_warning=habit_flag,
            manufacturer=med.get("manufacturer") if med.get("manufacturer") != "Not specified" else None,
            approx_price=med.get("price") if med.get("price") != "Not specified" else None
        )

explanation_service = ExplanationService()

