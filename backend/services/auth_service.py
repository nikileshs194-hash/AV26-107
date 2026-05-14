import random
import string
from datetime import datetime, timedelta, timezone  # timedelta/timezone used in store_otp
from services.supabase_service import _get_service_client as _get_client


def generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def store_otp(phone: str, otp: str) -> None:
    db = _get_client()
    if not db:
        raise RuntimeError("Supabase not configured")
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    # Remove old OTPs for this phone first
    db.table("otp_sessions").delete().eq("phone", phone).execute()
    db.table("otp_sessions").insert({
        "phone": phone,
        "otp": otp,
        "expires_at": expires_at,
        "verified": False,
    }).execute()


def verify_otp(phone: str, otp: str) -> bool:
    db = _get_client()
    if not db:
        raise RuntimeError("Supabase not configured")
    result = (
        db.table("otp_sessions")
        .select("*")
        .eq("phone", phone)
        .eq("otp", otp)
        .eq("verified", False)
        .execute()
    )
    if not result.data:
        return False
    session = result.data[0]
    expires_str = session["expires_at"]
    # Normalise timezone suffix
    expires_at = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires_at:
        return False
    db.table("otp_sessions").update({"verified": True}).eq("id", session["id"]).execute()
    return True


def get_or_create_user(phone: str) -> dict:
    db = _get_client()
    if not db:
        raise RuntimeError("Supabase not configured")
    result = db.table("users").select("*").eq("phone", phone).execute()
    if result.data:
        return {"user": result.data[0], "is_new": False}
    new = db.table("users").insert({
        "phone": phone,
    }).execute()
    return {"user": new.data[0], "is_new": True}


def update_user_profile(phone: str, full_name: str, age: int, gender: str) -> dict:
    db = _get_client()
    if not db:
        raise RuntimeError("Supabase not configured")
    result = (
        db.table("users")
        .update({
            "full_name": full_name,
            "age": age,
            "gender": gender,
        })
        .eq("phone", phone)
        .execute()
    )
    return result.data[0] if result.data else {}


def get_user_by_phone(phone: str) -> dict | None:
    db = _get_client()
    if not db:
        return None
    result = db.table("users").select("*").eq("phone", phone).execute()
    return result.data[0] if result.data else None
