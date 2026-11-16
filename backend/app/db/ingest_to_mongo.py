import os
import re
import sys
import time
import pandas as pd
import openpyxl
from pathlib import Path
from pymongo import InsertOne, ReplaceOne

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.config import settings
from app.db.mongo_client import mongo_manager
from app.db.ingest_dataset import extract_form_and_strength, normalize_text

def run_mongo_ingestion(limit: int = None):
    print("==================================================")
    print("Starting MediCare MongoDB Dataset Ingestion...")
    print(f"Target Mongo URI: {settings.MONGO_URI}")
    print(f"Target Database : {settings.MONGO_DB_NAME}")
    print(f"Target Collection: {settings.MONGO_COLLECTION_MEDICINES}")
    print("==================================================")

    start_time = time.time()
    db = mongo_manager.get_db()
    if db is None:
        print("ERROR: Cannot connect to MongoDB. Please ensure MongoDB service is running.")
        return

    coll = db[settings.MONGO_COLLECTION_MEDICINES]

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
    print("\n[Step 2/3] Streaming and inserting MID.xlsx into MongoDB...")
    
    # Drop existing medicines collection for clean fresh ingestion
    coll.drop()
    print("  Dropped existing collection for fresh ingestion.")

    seen_names = set()
    operations = []
    batch_size = 5000
    med_id_counter = 1
    total_inserted = 0

    if settings.XLSX_PATH.exists():
        wb = openpyxl.load_workbook(settings.XLSX_PATH, read_only=True)
        sheet = wb.active

        for idx, row in enumerate(sheet.iter_rows(values_only=True)):
            if idx == 0:
                continue

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

            brand_name, dosage_form, strength = extract_form_and_strength(raw_name, contains)
            norm_composition = normalize_text(contains)

            csv_meta = csv_lookup.get(norm_name, {})
            manufacturer = csv_meta.get('manufacturer', 'Not specified')
            price = csv_meta.get('price', 'Not specified')
            drug_interactions = csv_meta.get('drug_interactions', '')

            doc = {
                "med_id": med_id_counter,
                "id": med_id_counter,
                "name": raw_name,
                "normalized_name": norm_name,
                "brand_name": brand_name,
                "dosage_form": dosage_form,
                "strength": strength,
                "composition": contains,
                "normalized_composition": norm_composition,
                "manufacturer": manufacturer,
                "price": price,
                "introduction": intro,
                "uses": uses,
                "benefits": benefits,
                "side_effects": side_effect,
                "how_to_use": how_to_use,
                "how_works": how_works,
                "quick_tips": quick_tips,
                "habit_forming": habit_forming,
                "therapeutic_class": therapeutic_class,
                "safety_alcohol": safety_alcohol,
                "safety_pregnancy": safety_preg,
                "safety_breastfeeding": safety_breast,
                "safety_driving": safety_drive,
                "safety_kidney": safety_kidney,
                "safety_liver": safety_liver,
                "drug_interactions": drug_interactions,
                "link": link
            }

            operations.append(InsertOne(doc))
            med_id_counter += 1

            if len(operations) >= batch_size:
                coll.bulk_write(operations, ordered=False)
                total_inserted += len(operations)
                operations.clear()
                print(f"  Inserted {total_inserted} documents into MongoDB...")

            if limit and med_id_counter > limit:
                break

        wb.close()

    if operations:
        coll.bulk_write(operations, ordered=False)
        total_inserted += len(operations)
        operations.clear()

    print(f"  Finished MID.xlsx. Inserted: {total_inserted}")

    # Step 3: Add CSV-only medicines
    print("\n[Step 3/3] Inserting CSV-only unique medicines...")
    csv_added = 0
    for item in csv_unique_rows:
        raw_name = item['raw_name']
        norm_name = normalize_text(raw_name)
        if norm_name not in seen_names:
            seen_names.add(norm_name)
            brand_name, dosage_form, strength = extract_form_and_strength(raw_name, item['salt_composition'])
            norm_composition = normalize_text(item['salt_composition'])

            doc = {
                "med_id": med_id_counter,
                "id": med_id_counter,
                "name": raw_name,
                "normalized_name": norm_name,
                "brand_name": brand_name,
                "dosage_form": dosage_form,
                "strength": strength,
                "composition": item['salt_composition'],
                "normalized_composition": norm_composition,
                "manufacturer": item['manufacturer'],
                "price": item['price'],
                "introduction": item['medicine_desc'],
                "uses": item['sub_category'],
                "benefits": "",
                "side_effects": item['side_effects'],
                "how_to_use": "",
                "how_works": item['medicine_desc'],
                "quick_tips": "",
                "habit_forming": "No",
                "therapeutic_class": item['sub_category'],
                "safety_alcohol": "",
                "safety_pregnancy": "",
                "safety_breastfeeding": "",
                "safety_driving": "",
                "safety_kidney": "",
                "safety_liver": "",
                "drug_interactions": item['drug_interactions'],
                "link": ""
            }
            operations.append(InsertOne(doc))
            med_id_counter += 1
            csv_added += 1

            if len(operations) >= batch_size:
                coll.bulk_write(operations, ordered=False)
                total_inserted += len(operations)
                operations.clear()

    if operations:
        coll.bulk_write(operations, ordered=False)
        total_inserted += len(operations)
        operations.clear()

    print(f"  Added {csv_added} CSV-only medicines.")

    # Step 4: Build Indexes in MongoDB
    print("\n[Building MongoDB Indexes]...")
    mongo_manager.init_indexes()

    final_count = coll.count_documents({})
    elapsed = time.time() - start_time
    print("\n==================================================")
    print(f"MongoDB Ingestion Complete in {elapsed:.2f} seconds!")
    print(f"Total Medicines in MongoDB: {final_count}")
    print(f"Database: {settings.MONGO_DB_NAME}.{settings.MONGO_COLLECTION_MEDICINES}")
    print("==================================================")

if __name__ == "__main__":
    run_mongo_ingestion()

