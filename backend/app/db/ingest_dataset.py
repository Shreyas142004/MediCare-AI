import os
import re
import sys
import time
import sqlite3
import pandas as pd
import openpyxl
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.config import settings
from app.db.database import init_db, get_db_connection

DOSAGE_FORMS = [
    "tablet", "capsule", "injection", "syrup", "suspension", "drops", 
    "ointment", "cream", "gel", "lotion", "solution", "inhaler", 
    "spray", "powder", "granules", "emulsion", "elixir", "respules"
]

STRENGTH_REGEX = re.compile(
    r'(\d+(?:\.\d+)?\s*(?:mg|mcg|gm|g|iu|ml|%|w/v|w/w|iu/ml|mg/ml|mg/5ml))', 
    re.IGNORECASE
)

def normalize_text(text: str) -> str:
    if not text:
        return ""
    # Lowercase, remove special characters except spaces and alphanumeric
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', ' ', str(text)).lower()
    return " ".join(cleaned.split())

def extract_form_and_strength(name: str, composition: str = ""):
    text_to_search = f"{name} {composition}"
    
    # Extract strength
    strengths = STRENGTH_REGEX.findall(text_to_search)
    strength = ", ".join(strengths[:3]) if strengths else ""
    
    # Extract dosage form
    lower_name = name.lower()
    dosage_form = ""
    for form in DOSAGE_FORMS:
        if form in lower_name:
            dosage_form = form.capitalize()
            break
            
    # Extract brand name (usually the first word or words before the strength/form)
    brand_tokens = []
    for token in name.split():
        token_lower = token.lower()
        if STRENGTH_REGEX.search(token_lower) or any(f in token_lower for f in DOSAGE_FORMS):
            break
        brand_tokens.append(token)
    brand_name = " ".join(brand_tokens) if brand_tokens else name.split()[0] if name else ""
    
    return brand_name, dosage_form, strength

def run_ingestion(db_path: Path = settings.DB_PATH, limit: int = None):
    print("==================================================")
    print("Starting MediCare Database Ingestion & ETL...")
    print(f"Target Database: {db_path}")
    print("==================================================")
    
    start_time = time.time()
    init_db(db_path)
    
    # Step 1: Load and deduplicate CSV metadata into an in-memory dictionary
    print("\n[Step 1/3] Loading and indexing medicine_data.csv...")
    csv_lookup = {}
    csv_unique_rows = []
    
    if settings.CSV_PATH.exists():
        csv_df = pd.read_csv(settings.CSV_PATH, low_memory=False)
        print(f"  Total raw CSV rows: {len(csv_df)}")
        dedup_csv = csv_df.drop_duplicates(subset=['product_name']).fillna("")
        print(f"  Deduplicated CSV products: {len(dedup_csv)}")
        
        for _, row in dedup_csv.iterrows():
            prod_name = str(row['product_name']).strip()
            norm = normalize_text(prod_name)
            data = {
                'manufacturer': str(row.get('product_manufactured', 'Not specified')).strip() or 'Not specified',
                'price': str(row.get('product_price', 'Not specified')).strip() or 'Not specified',
                'drug_interactions': str(row.get('drug_interactions', '')).strip(),
                'sub_category': str(row.get('sub_category', '')).strip(),
                'side_effects': str(row.get('side_effects', '')).strip(),
                'medicine_desc': str(row.get('medicine_desc', '')).strip(),
                'salt_composition': str(row.get('salt_composition', '')).strip(),
                'raw_name': prod_name
            }
            csv_lookup[norm] = data
            csv_unique_rows.append(data)
    else:
        print("  WARNING: medicine_data.csv not found at", settings.CSV_PATH)

    # Step 2: Stream and ingest MID.xlsx
    print("\n[Step 2/3] Streaming and ingesting MID.xlsx...")
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    
    # Clear existing data for fresh ingestion
    cur.execute("DELETE FROM medicines;")
    cur.execute("DELETE FROM medicines_fts;")
    conn.commit()
    
    seen_names = set()
    records_batch = []
    fts_batch = []
    
    insert_med_sql = """
    INSERT INTO medicines (
        name, normalized_name, brand_name, dosage_form, strength,
        composition, normalized_composition, manufacturer, price,
        introduction, uses, benefits, side_effects, how_to_use,
        how_works, quick_tips, habit_forming, therapeutic_class,
        safety_alcohol, safety_pregnancy, safety_breastfeeding,
        safety_driving, safety_kidney, safety_liver, drug_interactions, link
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """
    
    batch_size = 5000
    ingested_count = 0
    
    if settings.XLSX_PATH.exists():
        wb = openpyxl.load_workbook(settings.XLSX_PATH, read_only=True)
        sheet = wb.active
        
        for idx, row in enumerate(sheet.iter_rows(values_only=True)):
            if idx == 0:
                continue  # Skip header
            
            raw_name = str(row[0] or "").strip()
            if not raw_name:
                continue
                
            norm_name = normalize_text(raw_name)
            if norm_name in seen_names:
                continue
            seen_names.add(norm_name)
            
            link = str(row[1] or "").strip()
            contains = str(row[2] or "").strip()
            intro = str(row[3] or "").strip()
            uses = str(row[4] or "").strip()
            benefits = str(row[5] or "").strip()
            side_effect = str(row[6] or "").strip()
            how_to_use = str(row[7] or "").strip()
            how_works = str(row[8] or "").strip()
            quick_tips = str(row[9] or "").strip()
            habit_forming = str(row[11] or "No").strip()
            therapeutic_class = str(row[12] or "").strip()
            safety_alcohol = str(row[14] or "").strip()
            safety_preg = str(row[15] or "").strip()
            safety_breast = str(row[16] or "").strip()
            safety_drive = str(row[17] or "").strip()
            safety_kidney = str(row[18] or "").strip()
            safety_liver = str(row[19] or "").strip()
            
            # Extract brand, form, and strength
            brand_name, dosage_form, strength = extract_form_and_strength(raw_name, contains)
            norm_composition = normalize_text(contains)
            
            # Enrich from CSV lookup
            csv_meta = csv_lookup.get(norm_name, {})
            manufacturer = csv_meta.get('manufacturer', 'Not specified')
            price = csv_meta.get('price', 'Not specified')
            drug_interactions = csv_meta.get('drug_interactions', '')
            
            records_batch.append((
                raw_name, norm_name, brand_name, dosage_form, strength,
                contains, norm_composition, manufacturer, price,
                intro, uses, benefits, side_effect, how_to_use,
                how_works, quick_tips, habit_forming, therapeutic_class,
                safety_alcohol, safety_preg, safety_breast,
                safety_drive, safety_kidney, safety_liver, drug_interactions, link
            ))
            
            ingested_count += 1
            
            if len(records_batch) >= batch_size:
                cur.executemany(insert_med_sql, records_batch)
                conn.commit()
                records_batch.clear()
                print(f"  Ingested {ingested_count} medicines...")
                
            if limit and ingested_count >= limit:
                break
                
        wb.close()
    
    # Flush remaining batch
    if records_batch:
        cur.executemany(insert_med_sql, records_batch)
        conn.commit()
        records_batch.clear()
        
    print(f"  Finished MID.xlsx ingestion. Total unique medicines from MID: {ingested_count}")

    # Step 3: Insert unique medicines from CSV that were not in MID.xlsx
    print("\n[Step 3/3] Checking and adding CSV-only medicines...")
    csv_only_count = 0
    for item in csv_unique_rows:
        raw_name = item['raw_name']
        norm_name = normalize_text(raw_name)
        if norm_name not in seen_names:
            seen_names.add(norm_name)
            brand_name, dosage_form, strength = extract_form_and_strength(raw_name, item['salt_composition'])
            norm_composition = normalize_text(item['salt_composition'])
            
            records_batch.append((
                raw_name, norm_name, brand_name, dosage_form, strength,
                item['salt_composition'], norm_composition, item['manufacturer'], item['price'],
                item['medicine_desc'], item['sub_category'], "", item['side_effects'], "",
                item['medicine_desc'], "", "No", item['sub_category'],
                "", "", "", "", "", "", item['drug_interactions'], ""
            ))
            csv_only_count += 1
            if len(records_batch) >= batch_size:
                cur.executemany(insert_med_sql, records_batch)
                conn.commit()
                records_batch.clear()
                
    if records_batch:
        cur.executemany(insert_med_sql, records_batch)
        conn.commit()
        records_batch.clear()
        
    print(f"  Added {csv_only_count} additional unique medicines from CSV.")
    
    # Build FTS5 virtual table
    print("\n[Building Full-Text Search Index (FTS5)]...")
    cur.execute("""
    INSERT INTO medicines_fts (rowid, name, brand_name, composition, uses, therapeutic_class, manufacturer)
    SELECT id, name, brand_name, composition, uses, therapeutic_class, manufacturer
    FROM medicines;
    """)
    conn.commit()
    
    # Verify counts
    cur.execute("SELECT COUNT(*) FROM medicines;")
    total_meds = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM medicines_fts;")
    total_fts = cur.fetchone()[0]
    
    conn.close()
    
    elapsed = time.time() - start_time
    print("\n==================================================")
    print(f"Ingestion Complete in {elapsed:.2f} seconds!")
    print(f"Total Unified Medicines in SQLite Database: {total_meds}")
    print(f"Total Records in FTS5 Search Index: {total_fts}")
    print(f"Database File: {db_path} ({os.path.getsize(db_path) / (1024*1024):.2f} MB)")
    print("==================================================")

if __name__ == "__main__":
    run_ingestion()

