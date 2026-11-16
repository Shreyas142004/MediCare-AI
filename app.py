"""
MediCare AI - Flask Web Application & Multimodal Recognition Engine
Run with:
    python app.py
"""

import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, make_response
from werkzeug.exceptions import HTTPException

# Ensure stdout handles UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure backend directory is in sys.path
ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Import MediCare backend services
from backend.app.core.config import settings
from backend.app.services.gemini_service import gemini_service
from backend.app.services.ocr_space_service import ocr_space_service
from backend.app.services.medicine_service import medicine_service
from backend.app.services.ocr_service import ocr_service
from backend.app.services.nlp_parser import nlp_parser
from backend.app.services.matcher_service import matcher_service
from backend.app.services.explanation_service import explanation_service
from backend.app.services.auth_service import (
    auth_service,
    create_access_token,
    decode_access_token
)
from backend.app.db.database import get_total_medicine_count, get_medicine_by_id
from backend.app.db.mongo_client import mongo_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("medicare.flask")

# Initialize Flask App
app = Flask(
    __name__,
    template_folder=str(FRONTEND_DIR),
    static_folder=None
)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB limit

# ---------------------------------------------------------
# CORS & OPTIONS Preflight Support
# ---------------------------------------------------------
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        resp = make_response()
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return resp, 200

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------
def get_auth_user():
    """Extracts authenticated user from Authorization header if present."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        payload = decode_access_token(token)
        if payload and "sub" in payload:
            return auth_service.find_user_by_id(payload["sub"])
    return None

def require_auth_user():
    """Extracts authenticated user or aborts with 401."""
    user = get_auth_user()
    if not user:
        resp = jsonify({"detail": "Authentication required. Please log in."})
        resp.status_code = 401
        return None, resp
    return user, None

# ---------------------------------------------------------
# API System & Health Routes
# ---------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    return send_from_directory(str(FRONTEND_DIR), "index.html")

@app.route("/api", methods=["GET"])
@app.route("/api/", methods=["GET"])
def api_status():
    med_count = get_total_medicine_count()
    return jsonify({
        "app": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "framework": "Flask 3.x",
        "status": "online",
        "gemini_model": settings.GEMINI_MODEL,
        "gemini_active": gemini_service.is_configured(),
        "ocr_space_active": ocr_space_service.is_configured(),
        "database": "mongodb" if mongo_manager.is_connected() else "sqlite",
        "total_medicines_indexed": med_count
    })

@app.route("/api/health", methods=["GET"])
def health_check():
    db_connected = mongo_manager.is_connected()
    return jsonify({
        "status": "healthy",
        "service": "MediCare AI Recognition Engine",
        "timestamp": datetime.utcnow().isoformat(),
        "database": "mongodb" if db_connected else "sqlite",
        "gemini_configured": gemini_service.is_configured()
    })

# ---------------------------------------------------------
# Medicine Scanning & Recognition Routes
# ---------------------------------------------------------
ALLOWED_MIME_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}

@app.route("/api/medicine/scan", methods=["POST"])
def scan_medicine():
    """
    Primary MediCare Multimodal Recognition Endpoint.
    Receives image of tablet strip, extracts details via Gemini/OCR,
    matches against 149,000+ medicine database, and formats patient explanation.
    """
    if "file" not in request.files:
        return jsonify({"detail": "No image file provided in request."}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"detail": "Empty file uploaded."}), 400

    contents = file.read()
    if not contents or len(contents) < 200:
        return jsonify({"detail": "Empty or corrupted image file uploaded."}), 400

    t0 = time.time()
    user = get_auth_user()
    user_id = str(user.get("id")) if user else "anonymous"

    try:
        # Step 1: Run OCR / Multimodal Analysis (OCR.space primary with fallback)
        mime_type = file.mimetype or "image/jpeg"
        if ocr_space_service.is_configured():
            extraction, model_used, is_fallback = ocr_space_service.extract_medicine_details(
                image_bytes=contents,
                mime_type=mime_type
            )
        else:
            extraction, model_used, is_fallback = gemini_service.analyze_medicine_image(
                image_bytes=contents,
                mime_type=mime_type
            )
        elapsed_ms = (time.time() - t0) * 1000

        # Step 2: Match against Medicine Dataset & Formulate Response
        response = medicine_service.process_extracted_medicine(
            extraction=extraction,
            model_name=model_used,
            processing_time_ms=elapsed_ms,
            user_id=user_id
        )

        return jsonify(response.model_dump()), 200

    except Exception as e:
        logger.error("Error in scan_medicine endpoint: %s", e, exc_info=True)
        return jsonify({"detail": f"An error occurred while scanning medicine: {str(e)}"}), 500

@app.route("/api/medicine/search", methods=["GET"])
def search_medicines():
    """Searches medicines by brand, active salt, composition, or generic query."""
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify([])

    limit = int(request.args.get("limit", 5))
    limit = max(1, min(limit, 20))

    entities = nlp_parser.parse(q)
    matches = matcher_service.match(entities, max_results=limit)
    return jsonify([m.model_dump() for m in matches]), 200

@app.route("/api/medicine/<int:med_id>", methods=["GET"])
def get_medicine_by_id_endpoint(med_id: int):
    """Retrieves full medicine record and patient-friendly explanation by medicine ID."""
    med = get_medicine_by_id(med_id)
    if not med:
        return jsonify({"detail": f"Medicine with ID {med_id} not found."}), 404

    explanation = explanation_service.generate_explanation(med)
    return jsonify({
        "medicine": med,
        "explanation": explanation.model_dump()
    }), 200

@app.route("/api/medicine/scans/history", methods=["GET"])
def get_scan_history():
    """Fetches recent medicine scans for the dashboard and history pages."""
    limit = int(request.args.get("limit", 20))
    user = get_auth_user()
    user_id = str(user.get("id")) if user else None

    db = mongo_manager.get_db()
    if db is None:
        return jsonify({"scans": [], "total": 0})

    query = {}
    if user_id:
        query = {"$or": [{"user_id": user_id}, {"user_id": "anonymous"}]}

    coll = db[settings.MONGO_COLLECTION_SCANS]
    cursor = coll.find(query).sort("timestamp", -1).limit(limit)
    scans = []
    for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        scans.append(doc)

    return jsonify({"scans": scans, "total": len(scans)})

@app.route("/api/medicine/scans/<scan_id>", methods=["DELETE"])
def delete_scan_record(scan_id: str):
    """Deletes a scan entry from history."""
    db = mongo_manager.get_db()
    if db is None:
        return jsonify({"success": True, "message": "Record removed."})

    from bson import ObjectId
    try:
        db[settings.MONGO_COLLECTION_SCANS].delete_one({"_id": ObjectId(scan_id)})
        return jsonify({"success": True, "message": "Scan deleted from history."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

# ---------------------------------------------------------
# User Authentication & Profile Routes
# ---------------------------------------------------------
@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    data = request.get_json(force=True, silent=True) or {}
    full_name = data.get("full_name", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")
    phone = data.get("phone")

    if not full_name or not email or not password:
        return jsonify({"detail": "Full name, email, and password are required."}), 400
    if len(password) < 6:
        return jsonify({"detail": "Password must be at least 6 characters long."}), 400

    try:
        user = auth_service.register_user(full_name, email, password, phone)
        token = create_access_token({"sub": str(user["id"]), "email": user["email"]})
        return jsonify({
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": str(user["id"]),
                "full_name": user["full_name"],
                "email": user["email"],
                "phone": user.get("phone"),
                "medical_notes": user.get("medical_notes"),
                "allergies": user.get("allergies"),
                "created_at": user.get("created_at")
            }
        }), 201
    except Exception as e:
        detail = getattr(e, "detail", str(e))
        return jsonify({"detail": detail}), 400

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(force=True, silent=True) or {}
    email = data.get("email", "").strip()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"detail": "Email and password are required."}), 400

    try:
        user = auth_service.authenticate_user(email, password)
        token = create_access_token({"sub": str(user["id"]), "email": user["email"]})
        return jsonify({
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": str(user["id"]),
                "full_name": user["full_name"],
                "email": user["email"],
                "phone": user.get("phone"),
                "medical_notes": user.get("medical_notes"),
                "allergies": user.get("allergies"),
                "created_at": user.get("created_at")
            }
        }), 200
    except Exception as e:
        detail = getattr(e, "detail", "Invalid email or password.")
        return jsonify({"detail": detail}), 401

@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    user, err_resp = require_auth_user()
    if err_resp:
        return err_resp

    return jsonify({
        "id": str(user["id"]),
        "full_name": user["full_name"],
        "email": user["email"],
        "phone": user.get("phone"),
        "medical_notes": user.get("medical_notes"),
        "allergies": user.get("allergies"),
        "created_at": user.get("created_at")
    })

@app.route("/api/auth/profile", methods=["PUT"])
def auth_update_profile():
    user, err_resp = require_auth_user()
    if err_resp:
        return err_resp

    data = request.get_json(force=True, silent=True) or {}
    updated = auth_service.update_profile(str(user["id"]), data)
    return jsonify({
        "id": str(updated["id"]),
        "full_name": updated["full_name"],
        "email": updated["email"],
        "phone": updated.get("phone"),
        "medical_notes": updated.get("medical_notes"),
        "allergies": updated.get("allergies"),
        "created_at": updated.get("created_at")
    })

@app.route("/api/auth/change-password", methods=["POST"])
def auth_change_password():
    user, err_resp = require_auth_user()
    if err_resp:
        return err_resp

    data = request.get_json(force=True, silent=True) or {}
    old_pw = data.get("old_password", "")
    new_pw = data.get("new_password", "")

    if len(new_pw) < 6:
        return jsonify({"detail": "New password must be at least 6 characters."}), 400

    try:
        auth_service.change_password(str(user["id"]), old_pw, new_pw)
        return jsonify({"success": True, "message": "Password updated successfully."})
    except Exception as e:
        detail = getattr(e, "detail", str(e))
        return jsonify({"detail": detail}), 400

@app.route("/api/auth/forgot-password", methods=["POST"])
def auth_forgot_password():
    data = request.get_json(force=True, silent=True) or {}
    email = data.get("email", "").strip()
    if not email:
        return jsonify({"detail": "Email is required."}), 400

    try:
        otp = auth_service.generate_otp(email)
        return jsonify({
            "success": True,
            "message": f"Verification code sent to {email}.",
            "demo_otp": otp
        })
    except Exception as e:
        detail = getattr(e, "detail", str(e))
        return jsonify({"detail": detail}), 400

@app.route("/api/auth/verify-otp", methods=["POST"])
def auth_verify_otp():
    data = request.get_json(force=True, silent=True) or {}
    email = data.get("email", "").strip()
    otp = data.get("otp", "").strip()

    try:
        auth_service.verify_otp(email, otp)
        return jsonify({"success": True, "message": "OTP verified successfully."})
    except Exception as e:
        detail = getattr(e, "detail", str(e))
        return jsonify({"detail": detail}), 400

@app.route("/api/auth/reset-password", methods=["POST"])
def auth_reset_password():
    data = request.get_json(force=True, silent=True) or {}
    email = data.get("email", "").strip()
    otp = data.get("otp", "").strip()
    new_password = data.get("new_password", "")

    if len(new_password) < 6:
        return jsonify({"detail": "New password must be at least 6 characters."}), 400

    try:
        auth_service.reset_password(email, otp, new_password)
        return jsonify({"success": True, "message": "Password has been successfully reset."})
    except Exception as e:
        detail = getattr(e, "detail", str(e))
        return jsonify({"detail": detail}), 400

# ---------------------------------------------------------
# OCR Raw Diagnostic Route
# ---------------------------------------------------------
@app.route("/api/ocr/extract", methods=["POST"])
def ocr_extract_raw():
    if "file" not in request.files:
        return jsonify({"detail": "No image provided."}), 400
    file = request.files["file"]
    contents = file.read()
    if ocr_space_service.is_configured():
        res = ocr_space_service.parse_image_text(contents, mime_type=file.mimetype or "image/jpeg")
        if res.get("success"):
            return jsonify(res)
    result = ocr_service.extract_text(contents)
    return jsonify(result)

# ---------------------------------------------------------
# Static Frontend Files Proxy (Catch-all for pages & assets)
# ---------------------------------------------------------
@app.route("/<path:path>", methods=["GET"])
def static_proxy(path):
    if path == "api" or path == "api/":
        return api_status()
    if path == "api/health":
        return health_check()
    if path.startswith("api/"):
        return jsonify({"detail": f"API endpoint /{path} not found."}), 404
    file_path = FRONTEND_DIR / path
    if file_path.exists() and file_path.is_file():
        return send_from_directory(str(FRONTEND_DIR), path)
    html_path = FRONTEND_DIR / f"{path}.html"
    if html_path.exists() and html_path.is_file():
        return send_from_directory(str(FRONTEND_DIR), f"{path}.html")
    return send_from_directory(str(FRONTEND_DIR), "index.html")

# ---------------------------------------------------------
# Main Execution Entrypoint
# ---------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    host = os.getenv("HOST", "127.0.0.1")

    # Banner
    med_count = get_total_medicine_count()
    db_mode = "MongoDB (medicare_db)" if mongo_manager.is_connected() else "SQLite Fallback (backend/medicare.db)"
    
    print("\n" + "=" * 65)
    print("             MEDICARE AI - FLASK APPLICATION")
    print("=" * 65)
    print(f" * Server URL:      http://{host}:{port}/")
    print(f" * Scanner URL:     http://{host}:{port}/scanner.html")
    print(f" * Dashboard URL:   http://{host}:{port}/dashboard.html")
    print(f" * Indexed Meds:    {med_count:,} records")
    print(f" * Database Engine: {db_mode}")
    print(f" * OCR.space Engine: {settings.OCR_SPACE_ENGINE} (Configured: {ocr_space_service.is_configured()})")
    print(f" * Gemini Vision:   {settings.GEMINI_MODEL} (Configured: {gemini_service.is_configured()})")
    print(f" * Local Fallback:  Orientation-Aware CRAFT + EasyOCR")
    print("=" * 65)
    print("Press CTRL+C to quit.\n")

    app.run(host=host, port=port, debug=False)
