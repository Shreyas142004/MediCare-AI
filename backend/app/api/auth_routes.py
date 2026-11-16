import logging
from fastapi import APIRouter, Depends, HTTPException, status
from ..schemas.auth_schema import (
    UserRegisterRequest,
    UserLoginRequest,
    ForgotPasswordRequest,
    VerifyOTPRequest,
    ResetPasswordRequest,
    ProfileUpdateRequest,
    ChangePasswordRequest,
    UserResponse,
    AuthTokenResponse
)
from ..services.auth_service import (
    auth_service,
    create_access_token,
    get_current_user
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["User Authentication & Accounts"])

def _format_user_response(user: dict) -> UserResponse:
    return UserResponse(
        id=str(user.get("id", user.get("_id", ""))),
        full_name=user.get("full_name", ""),
        email=user.get("email", ""),
        phone=user.get("phone"),
        medical_notes=user.get("medical_notes"),
        allergies=user.get("allergies"),
        created_at=user.get("created_at", "")
    )

@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegisterRequest):
    """Registers a new MediCare user account."""
    user = auth_service.register_user(
        full_name=payload.full_name,
        email=payload.email,
        password=payload.password,
        phone=payload.phone
    )
    user_id = str(user.get("id"))
    token = create_access_token({"sub": user_id, "email": user.get("email")})
    return AuthTokenResponse(
        access_token=token,
        user=_format_user_response(user)
    )

@router.post("/login", response_model=AuthTokenResponse)
def login(payload: UserLoginRequest):
    """Authenticates a user and returns an access token."""
    user = auth_service.authenticate_user(
        email=payload.email,
        password=payload.password
    )
    user_id = str(user.get("id"))
    token = create_access_token({"sub": user_id, "email": user.get("email")})
    return AuthTokenResponse(
        access_token=token,
        user=_format_user_response(user)
    )

@router.get("/me", response_model=UserResponse)
def get_profile(current_user: dict = Depends(get_current_user)):
    """Returns the profile of the currently authenticated user."""
    return _format_user_response(current_user)

@router.put("/profile", response_model=UserResponse)
def update_profile(payload: ProfileUpdateRequest, current_user: dict = Depends(get_current_user)):
    """Updates user profile information (name, phone, medical notes, allergies)."""
    updated_user = auth_service.update_profile(
        user_id=str(current_user.get("id")),
        updates=payload.model_dump(exclude_unset=True)
    )
    return _format_user_response(updated_user)

@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
    """Changes password for the authenticated user."""
    auth_service.change_password(
        user_id=str(current_user.get("id")),
        old_pw=payload.old_password,
        new_pw=payload.new_password
    )
    return {"success": True, "message": "Password changed successfully."}

@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest):
    """Generates an OTP for password recovery."""
    otp = auth_service.generate_otp(payload.email)
    # In development/local environment, return the OTP in response to allow seamless testing
    return {
        "success": True,
        "message": f"Verification code sent to {payload.email}.",
        "demo_otp": otp
    }

@router.post("/verify-otp")
def verify_otp(payload: VerifyOTPRequest):
    """Verifies that the provided OTP code is valid and active."""
    auth_service.verify_otp(payload.email, payload.otp)
    return {"success": True, "message": "OTP verified successfully. You may now set a new password."}

@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest):
    """Resets the user's password using the verified OTP."""
    auth_service.reset_password(payload.email, payload.otp, payload.new_password)
    return {"success": True, "message": "Password has been successfully reset. Please log in with your new password."}

