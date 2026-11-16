import os
import sys
import pickle
import time
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.neighbors import NearestNeighbors

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.core.config import settings
from backend.app.db.database import get_db_connection

MODELS_DIR = settings.BACKEND_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

def train_semantic_index(sample_limit: int = 25000):
    print("==================================================")
    print("Building MediCare Semantic Vector Search Index...")
    print("==================================================")
    t0 = time.time()

    conn = get_db_connection()
    cur = conn.cursor()
    print(f"Fetching top {sample_limit} medicines for semantic indexing...")
    cur.execute("""
        SELECT id, name, brand_name, composition, uses, therapeutic_class
        FROM medicines
        LIMIT ?
    """, (sample_limit,))
    rows = cur.fetchall()
    conn.close()

    documents = []
    metadata = []
    for r in rows:
        text = f"{r['name']} {r['composition']} {r['uses']} {r['therapeutic_class']}"
        documents.append(text)
        metadata.append({
            "id": r["id"],
            "name": r["name"],
            "brand": r["brand_name"],
            "composition": r["composition"]
        })

    print(f"Vectorizing {len(documents)} clinical documents with TF-IDF...")
    tfidf = TfidfVectorizer(max_features=5000, stop_words="english", ngram_range=(1, 2))
    X_tfidf = tfidf.fit_transform(documents)

    print("Reducing dimensionality with TruncatedSVD (128 dimensions)...")
    svd = TruncatedSVD(n_components=128, random_state=42)
    X_reduced = svd.fit_transform(X_tfidf)

    print("Fitting Nearest Neighbors index (cosine metric)...")
    nn = NearestNeighbors(n_neighbors=5, metric="cosine", algorithm="brute")
    nn.fit(X_reduced)

    index_payload = {
        "tfidf": tfidf,
        "svd": svd,
        "nn": nn,
        "metadata": metadata
    }

    out_path = MODELS_DIR / "semantic_index.pkl"
    with open(out_path, "wb") as f:
        pickle.dump(index_payload, f)

    elapsed = time.time() - t0
    print(f"Semantic index trained and saved in {elapsed:.2f}s to: {out_path}")
    print("==================================================")

if __name__ == "__main__":
    train_semantic_index()

