import sys
import os
import json
import time

sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding='utf-8')

from backend.app.services.ocr_service import ocr_service
from backend.app.services.nlp_parser import nlp_parser
from backend.app.services.matcher_service import matcher_service

image_path = os.path.abspath("backend/tests/evion_test_strip.jpeg")

print("================================================================================")
print("MEDICARE AI - LIVE TEST OF ACTUAL IMAGE RECOGNITION PIPELINE")
print(f"Test Image: {image_path}")
print("================================================================================")

t0 = time.time()

# Step 1 & 2 & 3: Read image, preprocess, and run OCR
print("\n[STAGE 1 & 2: IMAGE PREPROCESSING & ORIENTATION-AWARE OCR]")
ocr_results = ocr_service.extract_text(image_path)

print("\nRAW OCR TEXT:")
print(ocr_results["raw_text"])

print("\n--- DETECTED LINES WITH CONFIDENCE ---")
for line_info in ocr_results["detailed_results"]:
    print(f"  [{line_info['confidence']:.2f}] {line_info['text']}")
print(f"Selected Orientation: {ocr_results['orientation']}")
print(f"Average Confidence: {ocr_results['average_confidence']:.2f}")

# Step 4 & 5: NLP Entity Extraction
print("\nNLP EXTRACTED ENTITIES:")
entities = nlp_parser.parse(ocr_results["raw_text"], detected_lines=ocr_results["detected_lines"])
print(f"Brand Candidates   : {entities.brand_candidates}")
print(f"Active Salts       : {entities.active_salts}")
print(f"Strengths          : {entities.strengths}")
print(f"Dosage Forms       : {entities.dosage_forms}")
print(f"Manufacturer Hints : {entities.manufacturer_hints}")

print("\nNORMALIZED TEXT:")
print(f"Query: '{entities.normalized_query}'")

# Step 6 & 7: Match against Dataset
print("\nDATASET MATCHES:")
matches = matcher_service.match(entities, max_results=3)

if not matches:
    print("No matching medicines found.")
else:
    for idx, m in enumerate(matches, 1):
        print(f"Match #{idx}:")
        print(f"  Medicine Name : {m.medicine.name}")
        print(f"  Brand Name    : {m.medicine.brand_name}")
        print(f"  Strength      : {m.medicine.strength}")
        print(f"  Dosage Form   : {m.medicine.dosage_form}")
        print(f"  Composition   : {m.medicine.composition}")
        print(f"  Match Score   : {m.match_score}%")
        print(f"  Confidence    : {m.confidence}")
        print(f"  Match Type    : {m.match_type}")

# Step 8: Final Medicine Information
print("\nFINAL RESULT:")
if matches:
    top = matches[0]
    exp = top.simple_explanation
    print(f"RECOGNIZED MEDICINE : {exp.medicine_name}")
    print(f"ACTIVE INGREDIENTS  : {exp.active_ingredients}")
    print(f"DOSAGE & FORM       : {exp.dosage_and_form}")
    print(f"MATCH CONFIDENCE    : {top.confidence} ({top.match_score}%)")
    print("\nPRIMARY USES:")
    for u in exp.primary_uses:
        print(f"  * {u}")
    print("\nHOW IT WORKS:")
    print(f"  {exp.how_it_works}")
    print("\nHOW TO TAKE:")
    print(f"  {exp.how_to_take}")
    print("\nCOMMON SIDE EFFECTS:")
    for s in exp.common_side_effects:
        print(f"  * {s}")
    print("\nCRITICAL SAFETY ALERTS:")
    for category, advisory in exp.critical_safety_alerts.items():
        print(f"  * {category}: {advisory[:120]}...")
    print(f"\nHABIT FORMING RISK  : {'YES (Alert)' if exp.habit_forming_warning else 'No (Safe)'}")
else:
    print("Recognition failed to match any medicine record.")

elapsed = time.time() - t0
print(f"\nPipeline Execution Time: {elapsed:.2f} seconds")
print("================================================================================")

