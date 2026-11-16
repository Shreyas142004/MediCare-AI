import logging
import pymongo
from typing import Optional, List, Dict, Any
from ..core.config import settings

logger = logging.getLogger(__name__)

class MongoDBManager:
    _client: Optional[pymongo.MongoClient] = None
    _db: Optional[pymongo.database.Database] = None

    @classmethod
    def get_client(cls) -> Optional[pymongo.MongoClient]:
        if cls._client is None:
            try:
                cls._client = pymongo.MongoClient(
                    settings.MONGO_URI,
                    serverSelectionTimeoutMS=2000
                )
                # Verify connection
                cls._client.server_info()
                logger.info("Successfully connected to MongoDB at %s", settings.MONGO_URI)
            except Exception as e:
                logger.warning("MongoDB connection failed (%s). Fallback to SQLite enabled.", e)
                cls._client = None
        return cls._client

    @classmethod
    def get_db(cls) -> Optional[pymongo.database.Database]:
        client = cls.get_client()
        if client is not None:
            return client[settings.MONGO_DB_NAME]
        return None

    @classmethod
    def is_connected(cls) -> bool:
        try:
            client = cls.get_client()
            if client is None:
                return False
            client.server_info()
            return True
        except Exception:
            return False

    @classmethod
    def init_indexes(cls):
        db = cls.get_db()
        if db is None:
            return
        
        coll = db[settings.MONGO_COLLECTION_MEDICINES]
        logger.info("Ensuring MongoDB indexes on %s collection...", settings.MONGO_COLLECTION_MEDICINES)
        
        # Text Index for full-text clinical search
        try:
            coll.create_index([
                ("name", pymongo.TEXT),
                ("brand_name", pymongo.TEXT),
                ("composition", pymongo.TEXT),
                ("uses", pymongo.TEXT),
                ("manufacturer", pymongo.TEXT)
            ], name="medicine_fulltext_idx")
        except Exception as e:
            logger.info("Text index check: %s", e)

        # Compound & single field indexes
        coll.create_index("normalized_name")
        coll.create_index("brand_name")
        coll.create_index("strength")
        coll.create_index("dosage_form")
        coll.create_index("med_id", unique=True, sparse=True)
        
        logger.info("MongoDB indexes verified successfully.")

    @classmethod
    def count_medicines(cls) -> int:
        db = cls.get_db()
        if db is not None:
            return db[settings.MONGO_COLLECTION_MEDICINES].count_documents({})
        return 0

    @classmethod
    def get_medicine_by_id(cls, med_id: int) -> Optional[Dict[str, Any]]:
        db = cls.get_db()
        if db is not None:
            doc = db[settings.MONGO_COLLECTION_MEDICINES].find_one({"$or": [{"med_id": med_id}, {"id": med_id}]})
            if doc:
                doc["id"] = doc.get("med_id", doc.get("id", 0))
                doc.pop("_id", None)
                return doc
        return None

    @classmethod
    def search_medicines(cls, query: str, limit: int = 25) -> List[Dict[str, Any]]:
        db = cls.get_db()
        if db is None or not query.strip():
            return []

        coll = db[settings.MONGO_COLLECTION_MEDICINES]
        tokens = query.strip().split()
        
        # 1. Try MongoDB Text Search with score projection
        try:
            cursor = coll.find(
                {"$text": {"$search": query}},
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})]).limit(limit)
            
            results = []
            for doc in cursor:
                doc["id"] = doc.get("med_id", doc.get("id", 0))
                doc.pop("_id", None)
                results.append(doc)
            if results:
                return results
        except Exception as e:
            logger.debug("MongoDB text search exception: %s", e)

        # 2. Fallback to Regex search on normalized_name and normalized_composition
        clean_first_token = tokens[0].lower() if tokens else ""
        if len(clean_first_token) >= 3:
            pattern = {"$regex": clean_first_token, "$options": "i"}
            cursor = coll.find({
                "$or": [
                    {"normalized_name": pattern},
                    {"normalized_composition": pattern},
                    {"brand_name": pattern}
                ]
            }).limit(limit)
            
            fallback_results = []
            for doc in cursor:
                doc["id"] = doc.get("med_id", doc.get("id", 0))
                doc.pop("_id", None)
                fallback_results.append(doc)
            return fallback_results

        return []

    @classmethod
    def log_scan_history(cls, scan_data: Dict[str, Any]):
        """Logs OCR scan activity into the scanhistories collection."""
        db = cls.get_db()
        if db is not None:
            try:
                db[settings.MONGO_COLLECTION_SCANS].insert_one(scan_data)
            except Exception as e:
                logger.warning("Failed to log scan history to MongoDB: %s", e)

mongo_manager = MongoDBManager()

