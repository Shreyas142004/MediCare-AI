# MediCare AI: Intelligent Medicine Recognition & Patient Guidance System

[![Python](https://img.shields.io/badge/Python-3.14%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![MongoDB](https://img.shields.io/badge/MongoDB-medicare__db-47A248.svg)](https://www.mongodb.com/)
[![EasyOCR](https://img.shields.io/badge/OCR-EasyOCR%20(PyTorch)-red.svg)](https://github.com/JaidedAI/EasyOCR)
[![Status](https://img.shields.io/badge/Tests-9%2F9%20Passing-brightgreen.svg)]()

MediCare is an AI-powered pharmaceutical recognition platform designed to eliminate medication confusion. It accepts an image of a tablet blister strip or medicine box, uses computer vision to extract printed details from noisy foil packaging, extracts clinical entities (brand name, salt composition, strength, and dosage form), matches them against a verified encyclopedic dataset of **149,267 Indian medicines**, and returns clear, patient-friendly guidance in plain language.

---

## Table of Contents

- [Key Capabilities](#key-capabilities)
- [System Architecture](#system-architecture)
- [Tech Stack](#tech-stack)
- [Project Directory Structure](#project-directory-structure)
- [Getting Started & Installation](#getting-started--installation)
  - [1. Prerequisites](#1-prerequisites)
  - [2. Clone & Environment Setup](#2-clone--environment-setup)
  - [3. Start MongoDB](#3-start-mongodb)
- [Dataset Ingestion](#dataset-ingestion)
- [How to Train & Fine-Tune the Models](#how-to-train--fine-tune-the-models)
  - [1. Train Pharmaceutical NER Model](#1-train-pharmaceutical-ner-model)
  - [2. Train Semantic Vector Search Index](#2-train-semantic-vector-search-index)
- [Starting the Project](#starting-the-project)
- [API Reference](#api-reference)
  - [POST /api/ocr/scan](#1-post-apiocrscan)
  - [GET /api/medicine/search](#2-get-apimedicinesearch)
  - [GET /api/medicine/{id}](#3-get-apimedicineid)
  - [GET /api/health](#4-get-apihealth)
- [Running Automated Tests](#running-automated-tests)

---

## Key Capabilities

1. **Foil Reflection Suppression**: Specialized OpenCV image enhancement (CLAHE, bilateral denoising, Otsu thresholding) engineered specifically for reflective metallic blister packs.
2. **Robust Multi-Angle OCR**: EasyOCR deep learning text detection and recognition resilient to rotated and curved packaging text.
3. **Domain-Specific Pharmaceutical NLP**: Regex, heuristic, and token classifiers extracting active salts, dosage strengths (`mg`, `mcg`, `IU`, `ml`), dosage forms (`Tablet`, `Capsule`, `Syrup`), and manufacturer entities.
4. **Hybrid Dual-Engine Matching**:
   - **MongoDB** full-text search with score projection and regex fallback.
   - **SQLite FTS5** fallback for zero-configuration, local offline execution.
   - **RapidFuzz** fuzzy token-sort and partial ratio matching handling OCR typographical errors (`O` vs `0`, `l` vs `1`).
5. **Patient-Friendly Translation**: Synthesizes verified clinical records into simple, understandable sections:
   - Primary uses (what condition it treats).
   - Mechanism of action in lay terms.
   - Directions for use (food requirements, whole tablet warnings).
   - Common side effects.
   - Organ-specific safety alerts (Alcohol, Pregnancy, Breastfeeding, Driving, Kidney, Liver).
   - Habit-forming and addiction alerts.

---

## System Architecture

```
[ Medicine Blister Strip / Box Image ]
                   │
                   ▼
       [ OpenCV Preprocessing ]
       - Grayscale & Bilateral Noise Filtering
       - CLAHE (Contrast-Limited Adaptive Histogram Equalization)
       - Otsu Adaptive Binarization
                   │
                   ▼
          [ EasyOCR Engine ]
       - Deep learning text detection (CRAFT)
       - Text recognition (CRNN / CTC)
                   │
                   ▼
        [ NLP Entity Extractor ]
       - Brand candidates
       - Active salts & pharmaceutical suffixes
       - Strength parser (mg, mcg, IU, %, ml)
       - Dosage forms (Tablet, Capsule, Syrup)
                   │
                   ▼
      [ Hybrid Database Matcher ]
    ┌──────────────┴──────────────┐
    ▼                             ▼
[ MongoDB Full-Text ]     [ SQLite FTS5 Index ]
(Primary Database)        (Local Fallback)
    └──────────────┬──────────────┘
                   │
                   ▼
         [ RapidFuzz Scorer ]
       - Token sort similarity
       - Strength verification bonus (+15 / -10)
       - Confidence rating (HIGH / MEDIUM / LOW)
                   │
                   ▼
    [ Simple Language Generator ]
       - Uses, Directions, How it works
       - Side effects & Organ safety advisories
                   │
                   ▼
[ Structured JSON API Response ]
```

---

## Tech Stack

- **Backend Framework**: FastAPI (Asynchronous Python 3.14+)
- **Primary Database**: MongoDB (`medicare_db.medicines`, with text indexing)
- **Fallback Database**: SQLite 3 with FTS5 virtual table
- **Computer Vision**: OpenCV (`cv2`), Pillow
- **OCR Engine**: EasyOCR (PyTorch-backed CRAFT + CRNN)
- **NLP & Matching**: RapidFuzz, Regular Expressions, Scikit-learn
- **Testing**: PyTest, HTTPX TestClient

---

## Project Directory Structure

```
MediCare-AI/
├── README.md                           # Project documentation & instructions
├── dataset/                            # Original encyclopedic datasets
│   ├── medicine_data.csv               # 195,607 rows with pricing & manufacturers
│   └── MID.xlsx                        # 192,807 rows with clinical explanations
└── backend/
    ├── medicare.db                     # Unified SQLite database (FTS5 indexed)
    ├── requirements.txt                # Python backend dependencies
    ├── app/
    │   ├── main.py                     # FastAPI application entrypoint
    │   ├── api/
    │   │   ├── health_routes.py        # /api/health endpoint
    │   │   ├── medicine_routes.py      # /api/medicine/search & /{id}
    │   │   └── ocr_routes.py           # /api/ocr/scan endpoint
    │   ├── core/
    │   │   └── config.py               # Settings (MongoDB URI, paths, thresholds)
    │   ├── db/
    │   │   ├── database.py             # Unified query interface (Mongo + SQLite fallback)
    │   │   ├── mongo_client.py         # MongoDB connection & text index manager
    │   │   ├── models.py               # Pydantic schemas
    │   │   ├── ingest_to_mongo.py      # MongoDB bulk ETL ingestion script
    │   │   └── ingest_dataset.py       # SQLite ETL ingestion script
    │   ├── services/
    │   │   ├── ocr_service.py          # EasyOCR image reading & line aggregation
    │   │   ├── nlp_parser.py           # Entity, salt, strength & brand extractor
    │   │   ├── matcher_service.py      # Hybrid fuzzy & FTS matcher
    │   │   └── explanation_service.py  # Plain-language summary generator
    │   └── utils/
    │       ├── image_utils.py          # CLAHE contrast, bilateral filter, Otsu
    │       └── text_utils.py           # String cleaning and normalization
    ├── models/
    │   ├── ner_model.pkl               # Trained token classification model
    │   └── semantic_index.pkl          # Trained semantic vector search index
    ├── train/
    │   ├── train_ner.py                # Pharmaceutical NER model training script
    │   └── train_embeddings.py         # Semantic vector index training script
    ├── reports/
    │   └── dataset_report.txt          # Reconnaissance and dataset inspection report
    └── tests/
        └── test_backend.py             # Automated unit & integration tests
```

---

## Getting Started & Installation

### 1. Prerequisites

- **Python 3.10+** (Python 3.14 verified)
- **MongoDB** (Local instance running on `localhost:27017` or MongoDB Atlas URI)

### 2. Clone & Environment Setup

Open PowerShell or terminal in the project directory:

```powershell
cd D:\MediCare-AI

# Install required dependencies
python -m pip install -r backend/requirements.txt
```

### 3. Start MongoDB

If using local MongoDB on Windows:
```powershell
net start MongoDB
```
Or start via mongod command:
```powershell
mongod --dbpath="C:\data\db"
```

---

## Dataset Ingestion

The dataset includes `MID.xlsx` and `medicine_data.csv` inside `dataset/`. To deduplicate and load all 149,267 medicines into **MongoDB**:

```powershell
python backend/app/db/ingest_to_mongo.py
```

*To also populate the offline SQLite database fallback:*
```powershell
python backend/app/db/ingest_dataset.py
```

---

## How to Train & Fine-Tune the Models

MediCare provides two modular training pipelines tailored to medicine recognition:

### 1. Train Pharmaceutical NER Model

This script generates synthetic packaging token sequences with realistic OCR noise (casing shifts, dosage lines, composition clauses) and trains a logistic regression token classifier to extract `B-BRAND`, `B-SALT`, `B-STRENGTH`, and `B-FORM`:

```powershell
python backend/train/train_ner.py
```

**Output**: Model artifact saved to `backend/models/ner_model.pkl`.

### 2. Train Semantic Vector Search Index

This script constructs TF-IDF and 128-dimensional TruncatedSVD dense embeddings across clinical indications, therapeutic classes, and active salts, then trains a cosine NearestNeighbors index for semantic discovery:

```powershell
python backend/train/train_embeddings.py
```

**Output**: Vector index artifact saved to `backend/models/semantic_index.pkl`.

---

## Starting the Project

### Option 1: Standard Flask App (Recommended)

To run the complete web application (Frontend UI + REST API + Multimodal Vision Engine):

```powershell
python app.py
```

Once running:
- **Web App (Landing Page)**: [http://127.0.0.1:5000/](http://127.0.0.1:5000/)
- **Medicine Strip Scanner**: [http://127.0.0.1:5000/scanner.html](http://127.0.0.1:5000/scanner.html)
- **User Dashboard**: [http://127.0.0.1:5000/dashboard.html](http://127.0.0.1:5000/dashboard.html)
- **Scan History**: [http://127.0.0.1:5000/history.html](http://127.0.0.1:5000/history.html)
- **API Status**: [http://127.0.0.1:5000/api](http://127.0.0.1:5000/api)
- **API Health Check**: [http://127.0.0.1:5000/api/health](http://127.0.0.1:5000/api/health)

### Option 2: FastAPI Async Server

Alternatively, you can run the FastAPI async engine:

```powershell
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Once running:
- **Interactive Swagger Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative ReDoc UI**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/api/health](http://localhost:8000/api/health)

---

## API Reference

### 1. POST `/api/ocr/scan`
Accepts an image of a medicine blister strip, packaging, or label (`multipart/form-data`).

**Request (cURL)**:
```bash
curl -X POST "http://localhost:8000/api/ocr/scan" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@tablet_strip.jpg"
```

**Response (JSON)**:
```json
{
  "success": true,
  "ocr_raw_text": "Andol 0.5mg Tablets IP Each uncoated tablet contains: Haloperidol IP 0.5 mg",
  "detected_lines": [
    "Andol 0.5mg Tablets IP",
    "Each uncoated tablet contains: Haloperidol IP 0.5 mg"
  ],
  "extracted_entities": {
    "brand_candidates": ["Andol"],
    "active_salts": ["Haloperidol"],
    "strengths": ["0.5mg"],
    "dosage_forms": ["Tablet"],
    "manufacturer_hints": ["Sun Pharma"],
    "normalized_query": "Andol 0.5mg"
  },
  "top_match": {
    "medicine": {
      "id": 1,
      "name": "Andol 0.5mg Tablet",
      "brand_name": "Andol",
      "dosage_form": "Tablet",
      "strength": "0.5mg",
      "composition": "Haloperidol (0.5mg)",
      "manufacturer": "Not specified",
      "price": "Not specified"
    },
    "match_score": 100.0,
    "match_type": "exact_name",
    "confidence": "HIGH",
    "simple_explanation": {
      "medicine_name": "Andol 0.5mg Tablet",
      "active_ingredients": "Haloperidol (0.5mg)",
      "dosage_and_form": "Tablet (0.5mg)",
      "primary_uses": [
        "Schizophrenia",
        "Severe behavior problems in adults and children"
      ],
      "how_it_works": "Andol 0.5mg Tablet is a typical antipsychotic. It works by blocking the action of dopamine, a chemical messenger in the brain that affects thoughts and mood.",
      "how_to_take": "Take this medicine in the dose and duration as advised by your doctor. Swallow it as a whole. Do not chew, crush or break it.",
      "common_side_effects": [
        "Agitation",
        "Extrapyramidal symptoms",
        "Insomnia",
        "Muscle spasm",
        "Headache"
      ],
      "critical_safety_alerts": {
        "Alcohol": "Andol 0.5mg Tablet may cause excessive drowsiness with alcohol., label: SAFE",
        "Pregnancy": "May be unsafe during pregnancy. Please consult your doctor.",
        "Driving & Machinery": "May decrease alertness, affect vision or cause dizziness. Do not drive if symptoms occur."
      },
      "habit_forming_warning": false
    }
  },
  "processing_time_ms": 342.15,
  "message": "Medicine recognized successfully."
}
```

### 2. GET `/api/medicine/search?q={query}`
Searches medicines by brand name, salt composition, or generic query.

**Example**:
```bash
curl "http://localhost:8000/api/medicine/search?q=Paracetamol%20500"
```

### 3. GET `/api/medicine/{id}`
Retrieves full details and simple explanation for a medicine ID.

**Example**:
```bash
curl "http://localhost:8000/api/medicine/1"
```

### 4. GET `/api/health`
Returns connection status of MongoDB, SQLite fallback, and indexed medicine counts.

---

## Running Automated Tests

To execute the test suites:

```powershell
# 1. OCR.space Integration & Fallback Tests
python -m pytest backend/tests/test_ocr_space.py -v

# 2. General Backend & Clinical Matcher Tests
python -m pytest backend/tests/test_backend.py -v
```

The test suites validate:
1. `test_ocr_space_service_configured`: Verifies OCR.space key loading and key masking (security).
2. `test_ocr_space_live_parse_evion_strip`: Live text extraction via OCR.space API (`https://api.ocr.space/parse/image`).
3. `test_ocr_space_medicine_details_extraction`: NLP entity extraction of brand, strength, and dates without guessing.
4. `test_fastapi_scan_endpoint_with_ocr_space`: End-to-end `/api/medicine/scan` integration with clinical database matching.
5. `test_unreadable_blank_image_no_guessing`: Verifies unreadable images produce NO_MATCH without hallucinating medicine names.
6. `test_invalid_empty_image_raises_400`: Verifies corrupted or tiny files under 200 bytes trigger HTTP 400.
7. Plus the 9 core database, FTS5, OpenCV CLAHE, and API health tests.

