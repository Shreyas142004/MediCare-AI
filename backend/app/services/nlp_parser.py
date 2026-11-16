import re
from typing import List, Dict, Any, Set
from ..db.models import ParsedEntities
from ..utils.text_utils import clean_ocr_text, tokenize_words

DOSAGE_FORMS = [
    "tablet", "tablets", "tab", "tabs", "capsule", "capsules", "cap", "caps",
    "caplet", "caplets", "injection", "injections", "syrup", "suspension",
    "drops", "ointment", "cream", "gel", "lotion", "solution", "inhaler",
    "spray", "powder", "granules", "respules", "softgel", "softgels"
]

STRENGTH_PATTERN = re.compile(
    r'\b(\d+(?:\.\d+)?\s*(?:mg|mcg|gm|g|iu|ml|%|w/v|w/w|iu/ml|mg/ml|mg/5ml))\b', 
    re.IGNORECASE
)

PHARMACOPOEIA_TAGS = {"ip", "bp", "usp", "ep", "nf"}

EXCLUDED_WORDS = {
    "mfg", "lic", "no", "batch", "exp", "date", "mrp", "rs", "incl", "taxes",
    "store", "below", "keep", "reach", "children", "schedule", "prescription",
    "drug", "caution", "sold", "retail", "warning", "direction", "dosage",
    "physician", "protect", "light", "moisture", "temperature", "not", "exceed",
    "pack", "strip", "for", "use", "only", "oral", "external", "each", "uncoated",
    "film", "coated", "contains", "colour", "titanium", "dioxide", "iron", "oxide",
    "excipients", "preservative", "q.s", "qs", "as", "directed", "by", "the",
    "powerful", "antioxidant", "repair", "protect", "cells", "panel", "see"
}

KNOWN_SALT_SUFFIXES = (
    "cillin", "mycin", "olol", "pril", "statin", "prazole", "sartan",
    "dipine", "floxacin", "clovir", "zepam", "asone", "tidine", "dopa",
    "profen", "setron", "triptan", "gliptin", "gliflozin", "glitazone",
    "tinib", "mab", "parin", "cycline", "nazole", "vir", "fenac", "amol",
    "peridol", "caine", "mine", "barbital", "tocopherol", "tocopheryl", "acetate"
)

KNOWN_MANUFACTURERS = [
    "sun pharma", "cipla", "dr reddy", "lupin", "mankind", "abbott", 
    "alkem", "torrent", "zydus", "glenmark", "cadila", "intad",
    "pfizer", "gsk", "sanofi", "novartis", "bayer", "astrazeneca", "biocon",
    "micro labs", "aristo", "hetero", "fdc", "usv", "ipca", "emcure",
    "procter & gamble", "procter and gamble", "p&g", "pg health", "merck"
]

CONTAINS_REGEX = re.compile(
    r'(?:contains|composition|contains:)\s*[:\-]?\s*([a-zA-Z\s]+?)(?:ip|bp|usp|\d|\(|$)', 
    re.IGNORECASE
)

class NLPParser:
    @staticmethod
    def parse(ocr_raw_text: str, detected_lines: List[str] = None) -> ParsedEntities:
        lines = detected_lines or [l.strip() for l in ocr_raw_text.splitlines() if l.strip()]
        clean_text = clean_ocr_text(ocr_raw_text)
        
        # 1. Extract Strengths
        strengths = []
        for match in STRENGTH_PATTERN.finditer(clean_text):
            val = match.group(1).strip()
            norm_val = re.sub(r'\s+', '', val.lower())
            if norm_val not in [s.lower().replace(" ", "") for s in strengths]:
                strengths.append(val)

        # Also look for standalone numbers that frequently mean mg (e.g. 400, 500, 650)
        tokens_all = tokenize_words(clean_text)
        for t in tokens_all:
            if t in ["400", "500", "650", "250", "100", "200", "1000", "50", "20", "10", "5"]:
                inferred = f"{t}mg"
                if not any(t in s for s in strengths):
                    strengths.append(inferred)

        # 2. Extract Dosage Forms (with OCR typo tolerance and robust regex)
        found_forms = set()
        text_lower = clean_text.lower()

        # Robust Tablet patterns (e.g. tablet, tabs, tab, film-coated, uncoated, DT, dispersible)
        tablet_pattern = re.compile(
            r'\b(tablets?|tabs?|tabl\w*|f\.?c\.?\s*tabs?|film[\s\-]coated(\s+tablets?)?|'
            r'uncoated(\s+tablets?)?|dispersible(\s+tablets?)?|chewable(\s+tablets?)?|'
            r'effervescent(\s+tablets?)?|mouth[\s\-]dissolving|sustained[\s\-]release|'
            r'extended[\s\-]release|d\.?t\.?|s\.?r\.?|e\.?r\.?|c\.?r\.?|caplets?)\b',
            re.IGNORECASE
        )
        if tablet_pattern.search(text_lower):
            found_forms.add("Tablet")

        # Robust Capsule patterns (e.g. capsule, caps, softgel, soft gelatin)
        capsule_pattern = re.compile(
            r'\b(capsules?|caps?|capsu\w*|copsu\w*|softgels?|soft[\s\-]gelatin(\s+capsules?)?|'
            r'hard[\s\-]gelatin(\s+capsules?)?)\b',
            re.IGNORECASE
        )
        if capsule_pattern.search(text_lower):
            found_forms.add("Capsule")

        # Injection patterns (strictly require explicit injection / parenteral markers)
        injection_pattern = re.compile(
            r'\b(injections?|infusions?|vials?|ampoules?|ampules?|prefilled[\s\-]syringe|'
            r'sterile[\s\-]water[\s\-]for[\s\-]injection|for\s+i\.?v\.?\s*(/|\s*or\s*)\s*i\.?m\.?|'
            r'i\.?v\.?\s*infusion|inj\.)\b',
            re.IGNORECASE
        )
        if injection_pattern.search(text_lower):
            found_forms.add("Injection")

        # Other liquid or topical formulations
        for other_form, pattern in [
            ("Syrup", r'\b(syrup|suspension|elixir)\b'),
            ("Drops", r'\b(drops?|eye[\s\-]drops?|ear[\s\-]drops?)\b'),
            ("Ointment", r'\b(ointments?|creams?|gels?|lotions?)\b'),
            ("Inhaler", r'\b(inhalers?|respules?|rotacaps?)\b')
        ]:
            if re.search(pattern, text_lower):
                found_forms.add(other_form)

        # 3. Extract Manufacturer Hints
        mfg_hints = []
        text_lower = clean_text.lower()
        for mfg in KNOWN_MANUFACTURERS:
            if mfg in text_lower:
                mfg_hints.append(mfg.title())
                
        for line in lines:
            ll = line.lower()
            if any(k in ll for k in ["mfg by", "marketed by", "manufactured by", "pvt ltd", "laboratories", "pharma", "proct"]):
                cleaned_line = clean_ocr_text(line)
                if cleaned_line and cleaned_line not in mfg_hints:
                    mfg_hints.append(cleaned_line)

        # 4. Extract Active Salts
        active_salts = []
        contains_matches = CONTAINS_REGEX.findall(ocr_raw_text)
        for cm in contains_matches:
            salt_candidate = cm.strip()
            if len(salt_candidate) > 3 and salt_candidate.lower() not in EXCLUDED_WORDS:
                tokens = [t for t in salt_candidate.split() if t.lower() not in EXCLUDED_WORDS]
                if tokens:
                    candidate_full = " ".join(tokens)
                    if candidate_full not in active_salts:
                        active_salts.append(candidate_full)

        for i, token in enumerate(tokens_all):
            t_lower = token.lower()
            if t_lower in EXCLUDED_WORDS or len(t_lower) < 4:
                continue
            if any(t_lower.endswith(sfx) for sfx in KNOWN_SALT_SUFFIXES) or (i + 1 < len(tokens_all) and tokens_all[i+1].lower() in PHARMACOPOEIA_TAGS):
                if token not in active_salts and not any(token.lower() == s.lower() for s in active_salts):
                    active_salts.append(token)

        # 5. Extract Brand Candidates
        brand_candidates = []
        for line in lines:
            clean_l = clean_ocr_text(line)
            tokens = tokenize_words(clean_l)
            if not tokens:
                continue
            
            filtered_tokens = []
            for t in tokens:
                tl = t.lower()
                if tl in EXCLUDED_WORDS or tl in DOSAGE_FORMS or tl in PHARMACOPOEIA_TAGS or STRENGTH_PATTERN.search(tl):
                    continue
                if "capsu" in tl or "copsu" in tl or "tabl" in tl:
                    continue
                filtered_tokens.append(t)

            if filtered_tokens:
                full_cand = " ".join(filtered_tokens[:2])
                if full_cand and full_cand not in brand_candidates and len(full_cand) >= 3:
                    brand_candidates.append(full_cand)
                first_word = filtered_tokens[0]
                if len(first_word) >= 3 and first_word not in brand_candidates:
                    brand_candidates.append(first_word)

        # Build normalized search query prioritizing short brand candidates
        query_parts = []
        # Prefer a clean single-word brand if present (like "Evion", "Andol", "Calpol")
        single_word_brands = [b for b in brand_candidates if " " not in b and b.lower() not in ["vitam", "vitamins", "vitamin"]]
        if single_word_brands:
            query_parts.append(single_word_brands[0])
        elif brand_candidates:
            query_parts.append(brand_candidates[0])
        elif active_salts:
            query_parts.append(active_salts[0])

        if strengths:
            query_parts.append(strengths[0])

        normalized_query = " ".join(query_parts).strip()

        return ParsedEntities(
            brand_candidates=brand_candidates[:5],
            active_salts=active_salts[:5],
            strengths=strengths[:5],
            dosage_forms=list(found_forms),
            manufacturer_hints=mfg_hints[:3],
            normalized_query=normalized_query
        )

nlp_parser = NLPParser()
