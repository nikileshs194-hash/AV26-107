from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
import requests as _req
import re
from datetime import datetime, timezone, timedelta

from services.ai_service import get_ai_response
from services.weather_service import get_full_weather, geocode_city
from config import GROQ_API_KEY

router = APIRouter(prefix="/api/chat", tags=["ai"])

_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

# Supported audio extensions → MIME types for Groq Whisper
_AUDIO_MIME: dict[str, str] = {
    "m4a":  "audio/m4a",
    "mp4":  "audio/mp4",
    "mp3":  "audio/mpeg",
    "wav":  "audio/wav",
    "webm": "audio/webm",
    "ogg":  "audio/ogg",
    "flac": "audio/flac",
    "opus": "audio/opus",
}

# Words that look like city names but aren't
_NON_CITY_WORDS = {
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "today", "tomorrow", "yesterday", "morning", "evening", "night", "afternoon",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "rain", "flood", "weather", "safe", "risk", "high", "low", "moderate",
    "india", "help", "what", "how", "will", "can", "should", "is", "are",
    "please", "thank", "okay", "yes", "no", "the", "and", "for", "not",
    "groq", "ai", "app", "data", "forecast", "chance", "probability",
}

IST = timezone(timedelta(hours=5, minutes=30))


# ── DB helpers ────────────────────────────────────────────────────────────────

def _db():
    from services.supabase_service import _get_service_client
    return _get_service_client()


def _save_messages(phone: str, user_text: str, ai_text: str) -> None:
    """Persist one user + one assistant message to chat_messages table."""
    if not phone:
        return
    try:
        db = _db()
        if not db:
            return
        now = datetime.now(timezone.utc).isoformat()
        db.table("chat_messages").insert([
            {"phone": phone, "role": "user",      "content": user_text, "created_at": now},
            {"phone": phone, "role": "assistant",  "content": ai_text,  "created_at": now},
        ]).execute()
    except Exception as e:
        print(f"[CHAT] DB save error: {e}")


def _load_today_history(phone: str) -> list[dict]:
    """Return today's messages (IST midnight → now) for a user, oldest first."""
    if not phone:
        return []
    try:
        db = _db()
        if not db:
            return []
        # Today's start in IST → convert to UTC for the query
        now_ist = datetime.now(IST)
        today_start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_utc = today_start_ist.astimezone(timezone.utc).isoformat()

        res = (
            db.table("chat_messages")
            .select("role, content, created_at")
            .eq("phone", phone)
            .gte("created_at", today_start_utc)
            .order("created_at", desc=False)
            .limit(200)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f"[CHAT] DB load error: {e}")
        return []


def _clear_all_messages(phone: str) -> int:
    """Delete ALL chat_messages rows for a phone. Returns deleted count."""
    try:
        db = _db()
        if not db:
            return 0
        res = db.table("chat_messages").delete().eq("phone", phone).execute()
        return len(res.data or [])
    except Exception as e:
        print(f"[CHAT] DB clear error: {e}")
        return 0


def _clear_old_messages() -> int:
    """
    Delete messages from previous IST days.
    Called by the daily midnight scheduler loop.
    """
    try:
        db = _db()
        if not db:
            return 0
        now_ist = datetime.now(IST)
        today_start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_utc = today_start_ist.astimezone(timezone.utc).isoformat()

        res = (
            db.table("chat_messages")
            .delete()
            .lt("created_at", today_start_utc)
            .execute()
        )
        count = len(res.data or [])
        print(f"[ChatCleanup] Deleted {count} old messages (before {today_start_utc})")
        return count
    except Exception as e:
        print(f"[ChatCleanup] Error: {e}")
        return 0


# ── City detection ─────────────────────────────────────────────────────────────

def _extract_city_candidates(message: str) -> list[str]:
    candidates = []

    # Pattern 1: after prepositions — "weather in Mysore", "travel to Bangalore"
    prep_matches = re.findall(
        r'\b(?:in|for|at|to|about|near|around|of)\s+([A-Za-z][a-zA-Z\s]{1,25}?)(?:\s*[?,.]|$)',
        message
    )
    for m in prep_matches:
        c = m.strip().title()
        if c.lower() not in _NON_CITY_WORDS and len(c) > 2:
            candidates.append(c)

    # Pattern 2: entire message is a city name
    stripped = message.strip().rstrip("?.,!")
    if 2 < len(stripped) < 30 and re.match(r'^[A-Za-z][a-zA-Z\s]+$', stripped):
        c = stripped.title()
        if c.lower() not in _NON_CITY_WORDS:
            candidates.insert(0, c)

    # Pattern 3: capitalized proper nouns
    cap_matches = re.findall(r'\b([A-Z][a-z]{2,15}(?:\s+[A-Z][a-z]{2,15})?)\b', message)
    for m in cap_matches:
        c = m.strip()
        if c.lower() not in _NON_CITY_WORDS and c not in candidates:
            candidates.append(c)

    return candidates


def _get_city_weather(message: str) -> dict | None:
    candidates = _extract_city_candidates(message)
    for city in candidates:
        print(f"[CHAT] Trying to geocode: '{city}'")
        geo = geocode_city(city)
        if geo:
            print(f"[CHAT] Geocoded '{city}' → {geo['city']}, {geo['country']}")
            try:
                weather = get_full_weather(geo["lat"], geo["lon"])
                weather["current"]["city"]    = geo["city"]
                weather["current"]["country"] = geo["country"]
                weather["current"]["state"]   = geo.get("state", "")
                return weather
            except Exception as e:
                print(f"[CHAT] Weather fetch failed for '{city}': {e}")
    return None


# ── Request/Response models ────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    lat: float | None = None
    lon: float | None = None
    phone: str | None = None   # user's phone — used to persist + retrieve history


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("")
def chat(req: ChatRequest):
    try:
        weather_data      = None
        flood_data        = None
        requested_weather = None

        # ── City mentioned in message → fetch its weather ────────────────────
        try:
            requested_weather = _get_city_weather(req.message)
        except Exception as e:
            print(f"[CHAT] City weather extraction failed: {e}")

        # ── GPS location weather + flood prediction ──────────────────────────
        if req.lat is not None and req.lon is not None:
            try:
                weather_data = get_full_weather(req.lat, req.lon)
            except Exception as e:
                print(f"[CHAT] GPS weather fetch failed: {e}")

            try:
                from routes.predict import _fetch_features, _model
                import pandas as pd

                features = _fetch_features(req.lat, req.lon)
                prob     = 0.0
                if _model and features:
                    df   = pd.DataFrame([features])
                    prob = float(_model.predict_proba(df)[0][1])

                risk_level = (
                    "High"     if prob >= 0.65 else
                    "Moderate" if prob >= 0.40 else
                    "Low"      if prob >= 0.20 else
                    "Very Low"
                )
                flood_data = {
                    "probability":   round(prob, 3),
                    "risk_level":    risk_level,
                    "flood_likely":  prob >= 0.65,
                    "rainfall_1h":   features.get("rainfall_1h",   0),
                    "rainfall_24h":  features.get("rainfall_24h",  0),
                    "soil_moisture": features.get("soil_moisture",  0),
                    "humidity":      features.get("humidity",       0),
                    "elevation":     features.get("elevation",      0),
                    "drainage":      features.get("drainage",       0),
                }
            except Exception as e:
                print(f"[CHAT] Flood prediction fetch failed: {e}")

        # ── Load DB history for today if phone provided ──────────────────────
        if req.phone and not req.history:
            db_rows = _load_today_history(req.phone)
            history = [{"role": r["role"], "content": r["content"]} for r in db_rows]
        else:
            history = [{"role": m.role, "content": m.content} for m in req.history]

        # ── Get AI response ──────────────────────────────────────────────────
        result = get_ai_response(
            req.message, history, weather_data, flood_data,
            requested_weather=requested_weather
        )

        # ── Persist to DB ────────────────────────────────────────────────────
        if req.phone:
            _save_messages(req.phone, req.message, result.get("response", ""))

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
def get_history(phone: str = Query(..., description="User phone number")):
    """Return today's chat messages for a user (oldest first)."""
    rows = _load_today_history(phone)
    return {
        "phone":    phone,
        "date":     datetime.now(IST).strftime("%Y-%m-%d"),
        "messages": [{"role": r["role"], "content": r["content"], "time": r["created_at"]} for r in rows],
        "count":    len(rows),
    }


@router.delete("/history")
def clear_history(phone: str = Query(..., description="User phone number")):
    """Manually clear all chat messages for a user."""
    count = _clear_all_messages(phone)
    return {"success": True, "deleted": count, "message": "Chat history cleared"}


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """Transcribe voice audio using Groq Whisper (whisper-large-v3-turbo)."""
    if not GROQ_API_KEY:
        raise HTTPException(status_code=503, detail="Groq API key not configured")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file received")

    filename = file.filename or "recording.m4a"
    ext      = filename.rsplit(".", 1)[-1].lower() if "." in filename else "m4a"
    mime     = file.content_type or _AUDIO_MIME.get(ext, "audio/m4a")

    if ext in _AUDIO_MIME and (not mime or mime == "application/octet-stream"):
        mime = _AUDIO_MIME[ext]

    try:
        resp = _req.post(
            _WHISPER_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": (filename, audio_bytes, mime)},
            data={"model": "whisper-large-v3-turbo", "response_format": "json"},
            timeout=30,
        )
        if not resp.ok:
            err = ""
            try:
                err = resp.json().get("error", {}).get("message", resp.text[:300])
            except Exception:
                err = resp.text[:300]
            raise HTTPException(status_code=502, detail=f"Whisper error: {err}")

        text = resp.json().get("text", "").strip()
        return {"text": text}

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
