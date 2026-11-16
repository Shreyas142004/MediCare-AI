import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator

EMAIL_REGEX = re.compile(r"^[\w\.\+\-]+@[\w\-]+\.[a-zA-Z]{2,}$")

def validate_email_str(value: str) -> str:
    cleaned = value.strip().lower()
    if not EMAIL_REGEX.match(cleaned):
        raise ValueError("Invalid email address format.")
    return cleaned

class UserRegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    email: str
    password: str = Field(..., min_length=6, max_length=128)
    phone: Optional[str] = None

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_str(v)

class UserLoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_str(v)

class ForgotPasswordRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_str(v)

class VerifyOTPRequest(BaseModel):
    email: str
    otp: str = Field(..., min_length=4, max_length=8)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_str(v)

class ResetPasswordRequest(BaseModel):
    email: str
    otp: str
    new_password: str = Field(..., min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email_str(v)

class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = None
    medical_notes: Optional[str] = None
    allergies: Optional[str] = None

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6, max_length=128)

class UserResponse(BaseModel):
    id: str
    full_name: str
    email: str
    phone: Optional[str] = None
    medical_notes: Optional[str] = None
    allergies: Optional[str] = None
    created_at: str

class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
