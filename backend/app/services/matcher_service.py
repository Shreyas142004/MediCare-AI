import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from rapidfuzz import fuzz
from ..db.database import get_db_connection, search_medicines_fts
from ..db.mongo_client import mongo_manager
from ..db.models import ParsedEntities, MatchCandidate, MedicineRecord
from ..utils.text_utils import normalize_for_matching
from .explanation_service import explanation_service
from ..core.config import settings

logger = logging.getLogger(__name__)

class MatcherService:
    @staticmethod
    def _fetch_candidates_mongo(entities: ParsedEntities, limit: int = 40) -> List[Dict[str, Any]]:
        db = mongo_manager.get_db()
        if db is None:
            return []
            
        coll = db[settings.MONGO_COLLECTION_MEDICINES]
        candidates_dict: Dict[int, Dict[str, Any]] = {}

        # 1. Direct regex / equality match by brand candidates
        for brand in entities.brand_candidates:
            if len(brand) >= 3:
                cur = coll.find({
                    "$or": [
                        {"brand_name": {"$regex": f"^{re.escape(brand)}$", "$options": "i"}},
                        {"normalized_name": {"$regex": f"^{re.escape(normalize_for_matching(brand))}", "$options": "i"}}
                    ]
                }).limit(15)
                for doc in cur:
                    m_id = doc.get("med_id", doc.get("id", 0))
                    doc["id"] = m_id
                    doc.pop("_id", None)
                    candidates_dict[m_id] = doc

        # 2. Active salt search in MongoDB
        for salt in entities.active_salts:
            if len(salt) >= 4:
                cur = coll.find({
                    "normalized_composition": {"$regex": re.escape(normalize_for_matching(salt)), "$options": "i"}
                }).limit(15)
                for doc in cur:
                    m_id = doc.get("med_id", doc.get("id", 0))
                    doc["id"] = m_id
                    doc.pop("_id", None)
                    candidates_dict[m_id] = doc

        # 3. Text search
        search_terms = []
        if entities.brand_candidates:
            search_terms.append(entities.brand_candidates[0])
        if entities.active_salts:
            search_terms.append(entities.active_salts[0])
        if entities.strengths:
            search_terms.append(entities.strengths[0])

        if search_terms:
            text_query = " ".join(search_terms)
            text_results = mongo_manager.search_medicines(text_query, limit=25)
            for doc in text_results:
                candidates_dict[doc["id"]] = doc

        if len(candidates_dict) < 5 and entities.normalized_query:
            fallback = mongo_manager.search_medicines(entities.normalized_query, limit=20)
            for doc in fallback:
                candidates_dict[doc["id"]] = doc

        return list(candidates_dict.values())[:limit]

    @classmethod
    def _fetch_candidates(cls, entities: ParsedEntities, limit: int = 40) -> List[Dict[str, Any]]:
        # Use MongoDB if active
        if settings.DATABASE_TYPE == "mongodb" and mongo_manager.is_connected():
            mongo_cands = cls._fetch_candidates_mongo(entities, limit=limit)
            if mongo_cands:
                return mongo_cands

        # Fallback to SQLite
        conn = get_db_connection()
        cur = conn.cursor()
        candidates_dict: Dict[int, Dict[str, Any]] = {}

        for brand in entities.brand_candidates:
            norm_brand = normalize_for_matching(brand)
            if len(norm_brand) >= 3:
                cur.execute(
                    "SELECT * FROM medicines WHERE brand_name = ? COLLATE NOCASE LIMIT 15",
                    (brand,)
                )
                for r in cur.fetchall():
                    candidates_dict[r["id"]] = dict(r)

                cur.execute(
                    "SELECT * FROM medicines WHERE normalized_name LIKE ? LIMIT 15",
                    (f"{norm_brand}%",)
                )
                for r in cur.fetchall():
                    candidates_dict[r["id"]] = dict(r)

        for salt in entities.active_salts:
            norm_salt = normalize_for_matching(salt)
            if len(norm_salt) >= 4:
                cur.execute(
                    "SELECT * FROM medicines WHERE normalized_composition LIKE ? LIMIT 15",
                    (f"%{norm_salt}%",)
                )
                for r in cur.fetchall():
                    candidates_dict[r["id"]] = dict(r)

        search_terms = []
        if entities.brand_candidates:
            search_terms.append(entities.brand_candidates[0])
        if entities.active_salts:
            search_terms.append(entities.active_salts[0])
        if entities.strengths:
            search_terms.append(entities.strengths[0])

        if search_terms:
            fts_query_str = " ".join(search_terms)
            fts_results = search_medicines_fts(fts_query_str, limit=25)
            for r in fts_results:
                candidates_dict[r["id"]] = r

        if len(candidates_dict) < 5 and entities.normalized_query:
            fallback_results = search_medicines_fts(entities.normalized_query, limit=20)
            for r in fallback_results:
                candidates_dict[r["id"]] = r

        conn.close()
        return list(candidates_dict.values())[:limit]

    @classmethod
    def match(cls, entities: ParsedEntities, max_results: int = settings.MAX_CANDIDATE_RESULTS) -> List[MatchCandidate]:
        candidates = cls._fetch_candidates(entities)
        if not candidates:
            return []

        scored_candidates: List[Tuple[float, str, Dict[str, Any]]] = []

        query_str = entities.normalized_query
        target_strengths = [re.sub(r'\s+', '', s.lower()) for s in entities.strengths]
        target_forms = [f.lower() for f in entities.dosage_forms]

        for cand in candidates:
            med_name = cand.get("name", "")
            brand_name = cand.get("brand_name", "")
            comp = cand.get("composition", "")
            cand_strength = cand.get("strength", "").lower()
            cand_form = cand.get("dosage_form", "").lower()

            name_score = fuzz.token_sort_ratio(query_str, med_name)
            brand_score = max([fuzz.ratio(b.lower(), brand_name.lower()) for b in entities.brand_candidates] or [0])
            
            composite_score = max(name_score, brand_score * 0.95)

            if target_strengths:
                cand_clean_strength = re.sub(r'\s+', '', cand_strength)
                if any(ts in cand_clean_strength for ts in target_strengths):
                    composite_score += 15.0
                elif cand_clean_strength and not any(ts in cand_clean_strength for ts in target_strengths):
                    composite_score -= 10.0

            # Dosage Form Matching & Form Incompatibility Guard
            is_target_oral_solid = any(tf in ["tablet", "capsule", "caplet", "dt", "sr", "er"] for tf in target_forms)
            is_target_injection = any("injection" in tf for tf in target_forms)

            cand_name_lower = med_name.lower()
            is_cand_injection = "injection" in cand_form or "injection" in cand_name_lower or bool(re.search(r'\binj(\.|\b)', cand_name_lower))
            is_cand_oral_solid = any(f in cand_form for f in ["tablet", "capsule"]) or any(f in cand_name_lower for f in ["tablet", "capsule", " tab", " cap"])

            if is_target_oral_solid:
                if is_cand_injection:
                    # High-risk incompatibility: user scanned a tablet/capsule, candidate is an injection!
                    composite_score -= 60.0
                elif is_cand_oral_solid:
                    composite_score += 15.0
            elif is_target_injection:
                if is_cand_oral_solid:
                    composite_score -= 60.0
                elif is_cand_injection:
                    composite_score += 15.0
            else:
                # Target form was not explicitly visible on packaging.
                # For an oral medicine strip recognition engine, penalise injections unless explicitly indicated.
                if is_cand_injection:
                    composite_score -= 30.0
                elif is_cand_oral_solid:
                    composite_score += 10.0

            if entities.active_salts and comp:
                comp_lower = comp.lower()
                for salt in entities.active_salts:
                    if salt.lower() in comp_lower:
                        composite_score += 10.0
                        break

            final_score = min(100.0, max(0.0, composite_score))
            match_type = "exact_name" if brand_score > 95 else "fuzzy_name" if brand_score > 70 else "fts_query"
            scored_candidates.append((final_score, match_type, cand))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)

        results: List[MatchCandidate] = []
        for score, m_type, cand in scored_candidates[:max_results]:
            if score >= 85.0:
                confidence = "HIGH"
            elif score >= 65.0:
                confidence = "MEDIUM"
            else:
                confidence = "LOW"

            med_record = MedicineRecord(
                id=cand.get("med_id", cand.get("id", 0)),
                name=cand["name"],
                brand_name=cand.get("brand_name"),
                dosage_form=cand.get("dosage_form"),
                strength=cand.get("strength"),
                composition=cand.get("composition"),
                manufacturer=cand.get("manufacturer") or "Not specified",
                price=cand.get("price") or "Not specified",
                introduction=cand.get("introduction"),
                uses=cand.get("uses"),
                benefits=cand.get("benefits"),
                side_effects=cand.get("side_effects"),
                how_to_use=cand.get("how_to_use"),
                how_works=cand.get("how_works"),
                quick_tips=cand.get("quick_tips"),
                habit_forming=cand.get("habit_forming", "No"),
                therapeutic_class=cand.get("therapeutic_class"),
                safety_alcohol=cand.get("safety_alcohol"),
                safety_pregnancy=cand.get("safety_pregnancy"),
                safety_breastfeeding=cand.get("safety_breastfeeding"),
                safety_driving=cand.get("safety_driving"),
                safety_kidney=cand.get("safety_kidney"),
                safety_liver=cand.get("safety_liver"),
                drug_interactions=cand.get("drug_interactions"),
                link=cand.get("link")
            )

            explanation = explanation_service.generate_explanation(cand)

            results.append(MatchCandidate(
                medicine=med_record,
                match_score=round(score, 1),
                match_type=m_type,
                confidence=confidence,
                simple_explanation=explanation
            ))

        return results

matcher_service = MatcherService()
