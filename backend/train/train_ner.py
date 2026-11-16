import os
import sys
import re
import pickle
import random
from pathlib import Path
from typing import List, Tuple, Dict, Any
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.core.config import settings
from backend.app.db.database import get_db_connection

MODELS_DIR = settings.BACKEND_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

PACKAGING_TEMPLATES = [
    "{brand} {strength} {form} IP",
    "Each {form} contains: {salt} {strength}. Dosage: As directed by the physician.",
    "{brand} {form} - Composition: {salt} ({strength}). Mfg Lic: 24/UA/2019",
    "{brand} {strength} ({salt}) {form}. Store below 25 C. Protect from light.",
    "Mfg by: Sun Pharma Lab. {brand} {strength} Tablets IP. Active: {salt}",
    "{brand} {strength} - {salt} {form} IP. Keep out of reach of children."
]

def generate_synthetic_training_data(sample_size: int = 1500) -> List[Tuple[List[str], List[str]]]:
    """Generates synthetic labeled OCR token sequences from database records."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT brand_name, strength, dosage_form, composition
        FROM medicines
        WHERE brand_name IS NOT NULL AND strength IS NOT NULL AND composition IS NOT NULL
        LIMIT ?
    """, (sample_size,))
    rows = cur.fetchall()
    conn.close()

    dataset = []
    for row in rows:
        brand = row["brand_name"].strip()
        strength = row["strength"].split(",")[0].strip()
        form = row["dosage_form"].strip() if row["dosage_form"] else "Tablet"
        salt = row["composition"].split("+")[0].split("(")[0].strip()

        if not (brand and strength and salt):
            continue

        template = random.choice(PACKAGING_TEMPLATES)
        text = template.format(brand=brand, strength=strength, form=form, salt=salt)

        # Simple tokenization
        tokens = re.findall(r'\b[\w\.\%\-\/]+\b', text)
        labels = []
        for t in tokens:
            tl = t.lower()
            if tl == brand.lower():
                labels.append("B-BRAND")
            elif tl in strength.lower():
                labels.append("B-STRENGTH")
            elif tl in form.lower():
                labels.append("B-FORM")
            elif tl in salt.lower():
                labels.append("B-SALT")
            else:
                labels.append("O")
        dataset.append((tokens, labels))

    return dataset

def token_features(tokens: List[str], i: int) -> Dict[str, Any]:
    """Extracts lexical and orthographic features for token classification."""
    word = tokens[i]
    features = {
        "bias": 1.0,
        "word.lower": word.lower(),
        "word[-3:]": word[-3:],
        "word[-2:]": word[-2:],
        "word.isupper": word.isupper(),
        "word.istitle": word.istitle(),
        "word.isdigit": word.isdigit(),
        "has_digit": any(c.isdigit() for c in word),
        "has_strength_unit": any(u in word.lower() for u in ["mg", "mcg", "iu", "ml", "%"]),
    }
    if i > 0:
        prev_word = tokens[i - 1]
        features.update({
            "-1:word.lower": prev_word.lower(),
            "-1:word.istitle": prev_word.istitle(),
        })
    else:
        features["BOS"] = True

    if i < len(tokens) - 1:
        next_word = tokens[i + 1]
        features.update({
            "+1:word.lower": next_word.lower(),
            "+1:word.istitle": next_word.istitle(),
        })
    else:
        features["EOS"] = True

    return features

def train_ner_model():
    print("==================================================")
    print("Training MediCare Pharmaceutical NER Model...")
    print("==================================================")

    data = generate_synthetic_training_data(sample_size=3000)
    print(f"Generated {len(data)} labeled packaging training sequences.")

    X = []
    y = []
    for tokens, labels in data:
        for i in range(len(tokens)):
            X.append(token_features(tokens, i))
            y.append(labels[i])

    print(f"Training Logistic Regression token classifier on {len(X)} tokens...")
    pipeline = Pipeline([
        ("vectorizer", DictVectorizer(sparse=True)),
        ("classifier", LogisticRegression(max_iter=300, solver="lbfgs"))
    ])

    pipeline.fit(X, y)

    model_path = MODELS_DIR / "ner_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(pipeline, f)

    print(f"Model saved successfully to: {model_path}")
    print("Labels learned:", pipeline.classes_)
    print("==================================================")

if __name__ == "__main__":
    train_ner_model()

