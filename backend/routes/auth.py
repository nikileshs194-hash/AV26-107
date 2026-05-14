import traceback
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.auth_service import (
    generate_otp, store_otp, verify_otp,
    get_or_create_user, update_user_profile, get_user_by_phone,
)
from services.sms_service import send_otp_sms

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SendOTPRequest(BaseModel):
    phone: str      # e.g. "+919876543210"
    country_code: str = "+91"


class VerifyOTPRequest(BaseModel):
    phone: str
    otp: str


class UpdateProfileRequest(BaseModel):
    phone: str
    full_name: str
    age: int
    gender: str


class UpdateLocationRequest(BaseModel):
    phone: str
    latitude: float
    longitude: float


@router.post("/send-otp")
def send_otp(req: SendOTPRequest):
    phone = req.phone.strip()
    if not phone or len(phone) < 10:
        raise HTTPException(status_code=400, detail="Invalid phone number")
    try:
        otp = generate_otp()
        store_otp(phone, otp)
        send_otp_sms(phone, otp)
        return {"success": True, "message": "OTP sent successfully"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify-otp")
def verify_otp_route(req: VerifyOTPRequest):
    try:
        if not verify_otp(req.phone, req.otp):
            raise HTTPException(status_code=400, detail="Invalid or expired OTP")
        result = get_or_create_user(req.phone)
        return result
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-profile")
def update_profile(req: UpdateProfileRequest):
    try:
        user = update_user_profile(req.phone, req.full_name, req.age, req.gender)
        return {"success": True, "user": user}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-location")
def update_location(req: UpdateLocationRequest):
    try:
        from services.supabase_service import _get_service_client
        from datetime import datetime, timezone
        db = _get_service_client()
        if not db:
            raise HTTPException(status_code=500, detail="Database not configured")
        db.table("users").update({
            "latitude":            req.latitude,
            "longitude":           req.longitude,
            "location_updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("phone", req.phone).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profile/{phone:path}")
def get_profile(phone: str):
    user = get_user_by_phone(phone)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": user, "is_new": False}
