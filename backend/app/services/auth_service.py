import os
import hashlib
import hmac
import random
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from fastapi import Header, HTTPException, status
from ..core.config import settings
from ..db.mongo_client import mongo_manager

logger = logging.getLogger(__name__)

# Fallback in-memory store for users if MongoDB is temporarily unavailable
_FALLBACK_USERS_STORE: Dict[str, Dict[str, Any]] = {}
_FALLBACK_OTPS_STORE: Dict[str, Dict[str, Any]] = {}

def hash_password(password: str) -> str:
    """Hashes a password securely using PBKDF2-HMAC-SHA256 with a 16-byte random salt."""
    salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"{salt.hex()}${hashed.hex()}"

def verify_password(password: str, hashed_value: str) -> bool:
    """Verifies a plain password against the stored salt$hash string."""
    try:
        salt_hex, hash_hex = hashed_value.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)
        actual_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return hmac.compare_digest(actual_hash, expected_hash)
    except Exception as e:
        logger.error("Error verifying password hash: %s", e)
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Encodes a JWT access token with expiration."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=settings.JWT_EXPIRATION_HOURS))
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token

def decode_access_token(token: str) -> Optional[dict]:
    """Decodes and validates a JWT token; returns payload or None."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None

class AuthService:
    @staticmethod
    def get_users_collection():
        db = mongo_manager.get_db()
        if db is not None:
            return db[settings.MONGO_COLLECTION_USERS]
        return None

    @staticmethod
    def get_otps_collection():
        db = mongo_manager.get_db()
        if db is not None:
            return db[settings.MONGO_COLLECTION_OTPS]
        return None

    @classmethod
    def find_user_by_email(cls, email: str) -> Optional[Dict[str, Any]]:
        clean_email = email.strip().lower()
        coll = cls.get_users_collection()
        if coll is not None:
            user = coll.find_one({"email": clean_email})
            if user:
                user["id"] = str(user.pop("_id"))
                return user
        return _FALLBACK_USERS_STORE.get(clean_email)

    @classmethod
    def find_user_by_id(cls, user_id: str) -> Optional[Dict[str, Any]]:
        coll = cls.get_users_collection()
        if coll is not None:
            from bson import ObjectId
            try:
                user = coll.find_one({"_id": ObjectId(user_id)})
                if user:
                    user["id"] = str(user.pop("_id"))
                    return user
            except Exception:
                pass
        # Search fallback
        for u in _FALLBACK_USERS_STORE.values():
            if u.get("id") == user_id:
                return u
        return None

    @classmethod
    def register_user(cls, full_name: str, email: str, password: str, phone: Optional[str] = None) -> Dict[str, Any]:
        clean_email = email.strip().lower()
        existing = cls.find_user_by_email(clean_email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email address already exists. Please log in."
            )

        hashed_pw = hash_password(password)
        now_iso = datetime.utcnow().isoformat()
        user_doc = {
            "full_name": full_name.strip(),
            "email": clean_email,
            "password_hash": hashed_pw,
            "phone": phone.strip() if phone else None,
            "medical_notes": "",
            "allergies": "",
            "created_at": now_iso,
            "updated_at": now_iso
        }

        coll = cls.get_users_collection()
        if coll is not None:
            res = coll.insert_one(user_doc)
            user_doc["id"] = str(res.inserted_id)
            user_doc.pop("_id", None)
        else:
            user_doc["id"] = f"usr_{random.randint(100000, 999999)}"
            _FALLBACK_USERS_STORE[clean_email] = user_doc

        return user_doc

    @classmethod
    def authenticate_user(cls, email: str, password: str) -> Dict[str, Any]:
        clean_email = email.strip().lower()
        user = cls.find_user_by_email(clean_email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password. Please try again."
            )

        if not verify_password(password, user.get("password_hash", "")):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password. Please try again."
            )

        return user

    @classmethod
    def update_profile(cls, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        coll = cls.get_users_collection()
        clean_updates = {k: v for k, v in updates.items() if v is not None}
        clean_updates["updated_at"] = datetime.utcnow().isoformat()

        if coll is not None:
            from bson import ObjectId
            try:
                coll.update_one({"_id": ObjectId(user_id)}, {"$set": clean_updates})
                return cls.find_user_by_id(user_id)
            except Exception as e:
                logger.error("Error updating profile in MongoDB: %s", e)

        # Fallback store update
        for email, u in _FALLBACK_USERS_STORE.items():
            if u.get("id") == user_id:
                u.update(clean_updates)
                return u

        raise HTTPException(status_code=404, detail="User not found")

    @classmethod
    def change_password(cls, user_id: str, old_pw: str, new_pw: str) -> bool:
        user = cls.find_user_by_id(user_id)
        if not user or not verify_password(old_pw, user.get("password_hash", "")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect."
            )
        new_hash = hash_password(new_pw)
        coll = cls.get_users_collection()
        if coll is not None:
            from bson import ObjectId
            coll.update_one({"_id": ObjectId(user_id)}, {"$set": {"password_hash": new_hash, "updated_at": datetime.utcnow().isoformat()}})
            return True

        user["password_hash"] = new_hash
        return True

    @classmethod
    def generate_otp(cls, email: str) -> str:
        clean_email = email.strip().lower()
        user = cls.find_user_by_email(clean_email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No account found with this email address."
            )

        # Generate 6 digit numeric code
        otp_code = str(random.randint(100000, 999999))
        expires_at = datetime.utcnow() + timedelta(minutes=15)

        otp_doc = {
            "email": clean_email,
            "otp": otp_code,
            "expires_at": expires_at.isoformat(),
            "used": False
        }

        coll = cls.get_otps_collection()
        if coll is not None:
            coll.delete_many({"email": clean_email})
            coll.insert_one(otp_doc)
        else:
            _FALLBACK_OTPS_STORE[clean_email] = otp_doc

        logger.info("Generated OTP for %s: %s (valid for 15 mins)", clean_email, otp_code)
        return otp_code

    @classmethod
    def verify_otp(cls, email: str, otp: str) -> bool:
        clean_email = email.strip().lower()
        coll = cls.get_otps_collection()
        record = None

        if coll is not None:
            record = coll.find_one({"email": clean_email, "used": False})
        else:
            record = _FALLBACK_OTPS_STORE.get(clean_email)

        if not record:
            raise HTTPException(status_code=400, detail="No active OTP found. Please request a new one.")

        # Check expiration
        exp_time = datetime.fromisoformat(record["expires_at"])
        if datetime.utcnow() > exp_time:
            raise HTTPException(status_code=400, detail="OTP has expired. Please request a new one.")

        if str(record["otp"]).strip() != str(otp).strip():
            raise HTTPException(status_code=400, detail="Invalid OTP code. Please check and try again.")

        return True

    @classmethod
    def reset_password(cls, email: str, otp: str, new_password: str) -> bool:
        cls.verify_otp(email, otp)
        clean_email = email.strip().lower()
        new_hash = hash_password(new_password)

        coll = cls.get_users_collection()
        if coll is not None:
            coll.update_one({"email": clean_email}, {"$set": {"password_hash": new_hash, "updated_at": datetime.utcnow().isoformat()}})
            # Mark OTP as used
            otps_coll = cls.get_otps_collection()
            if otps_coll is not None:
                otps_coll.delete_many({"email": clean_email})
        else:
            if clean_email in _FALLBACK_USERS_STORE:
                _FALLBACK_USERS_STORE[clean_email]["password_hash"] = new_hash
            _FALLBACK_OTPS_STORE.pop(clean_email, None)

        return True

auth_service = AuthService()

def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Dependency that extracts and validates the currently logged-in user from the Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required. Please log in."
        )
    token = authorization[7:].strip()
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please log in again."
        )
    user_id = payload.get("sub")
    user = auth_service.find_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists."
        )
    return user

