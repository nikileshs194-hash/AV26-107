from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from pydantic import BaseModel
import requests as _req
from services.ai_service import get_ai_response
from services.weather_service import get_full_weather
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


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    lat: float | None = None
    lon: float | None = None


@router.post("")
def chat(req: ChatRequest):
    try:
        weather_data  = None
        flood_data    = None

        if req.lat is not None and req.lon is not None:
            # ── Fetch real-time weather ──────────────────────────────────────
            try:
                weather_data = get_full_weather(req.lat, req.lon)
            except Exception as e:
                print(f"[CHAT] Weather fetch failed: {e}")

            # ── Fetch flood prediction ───────────────────────────────────────
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

        history = [{"role": m.role, "content": m.content} for m in req.history]
        return get_ai_response(req.message, history, weather_data, flood_data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """
    Transcribe voice audio using Groq Whisper (whisper-large-v3-turbo).
    """
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
