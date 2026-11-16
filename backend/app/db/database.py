import sqlite3
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
from ..core.config import settings
from .mongo_client import mongo_manager

logger = logging.getLogger(__name__)

def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    target_path = db_path or settings.DB_PATH
    conn = sqlite3.connect(str(target_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn

def init_db(db_path: Optional[Path] = None):
    # Initialize SQLite schema
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS medicines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        normalized_name TEXT NOT NULL,
        brand_name TEXT,
        dosage_form TEXT,
        strength TEXT,
        composition TEXT,
        normalized_composition TEXT,
        manufacturer TEXT DEFAULT 'Not specified',
        price TEXT DEFAULT 'Not specified',
        introduction TEXT,
        uses TEXT,
        benefits TEXT,
        side_effects TEXT,
        how_to_use TEXT,
        how_works TEXT,
        quick_tips TEXT,
        habit_forming TEXT DEFAULT 'No',
        therapeutic_class TEXT,
        safety_alcohol TEXT,
        safety_pregnancy TEXT,
        safety_breastfeeding TEXT,
        safety_driving TEXT,
        safety_kidney TEXT,
        safety_liver TEXT,
        drug_interactions TEXT,
        link TEXT
    );
    """)
    
    cur.execute("CREATE INDEX IF NOT EXISTS idx_med_norm_name ON medicines (normalized_name);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_med_brand ON medicines (brand_name);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_med_strength ON medicines (strength);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_med_form ON medicines (dosage_form);")
    
    cur.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS medicines_fts USING fts5(
        name,
        brand_name,
        composition,
        uses,
        therapeutic_class,
        manufacturer,
        content=medicines,
        content_rowid=id
    );
    """)
    
    conn.commit()
    conn.close()

    # Also initialize MongoDB indexes if connected
    if mongo_manager.is_connected():
        mongo_manager.init_indexes()

def get_total_medicine_count(db_path: Optional[Path] = None) -> int:
    if settings.DATABASE_TYPE == "mongodb" and mongo_manager.is_connected():
        mongo_count = mongo_manager.count_medicines()
        if mongo_count > 0:
            return mongo_count
            
    # Fallback to SQLite
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM medicines;")
    count = cur.fetchone()[0]
    conn.close()
    return count

def get_medicine_by_id(med_id: int, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    if settings.DATABASE_TYPE == "mongodb" and mongo_manager.is_connected():
        doc = mongo_manager.get_medicine_by_id(med_id)
        if doc:
            return doc
            
    # Fallback to SQLite
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM medicines WHERE id = ?", (med_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def search_medicines_fts(query: str, limit: int = 25, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    if settings.DATABASE_TYPE == "mongodb" and mongo_manager.is_connected():
        mongo_results = mongo_manager.search_medicines(query, limit=limit)
        if mongo_results:
            return mongo_results

    # Fallback to SQLite FTS5
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    
    tokens = [t.strip() for t in query.split() if t.strip()]
    if not tokens:
        conn.close()
        return []
    
    fts_query = " ".join([f'"{t}"*' for t in tokens if len(t) > 1] or [f'"{tokens[0]}"*'])
    
    sql = """
    SELECT m.*, rank
    FROM medicines_fts fts
    JOIN medicines m ON fts.rowid = m.id
    WHERE medicines_fts MATCH ?
    ORDER BY rank
    LIMIT ?;
    """
    try:
        cur.execute(sql, (fts_query, limit))
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    except Exception:
        fallback_sql = """
        SELECT * FROM medicines
        WHERE normalized_name LIKE ? OR normalized_composition LIKE ?
        LIMIT ?;
        """
        pattern = f"%{tokens[0].lower()}%"
        cur.execute(fallback_sql, (pattern, pattern, limit))
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
