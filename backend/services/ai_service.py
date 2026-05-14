"""
AI service — uses Groq (llama-3.3-70b-versatile, free tier).
Get a free key at https://console.groq.com → API Keys → Create Free Key
Add to backend/.env:  GROQ_API_KEY=gsk_xxxxxxxxxxxx
"""
import requests as _req
from config import GROQ_API_KEY
from datetime import datetime, timezone, timedelta

_GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_MODEL = "llama-3.3-70b-versatile"   # free, fast (~300 tok/s)


def _key_ok() -> bool:
    return bool(GROQ_API_KEY and len(GROQ_API_KEY) > 10)


def _build_weather_context(weather: dict | None, flood: dict | None) -> str:
    lines = []

    # ── Current weather ──────────────────────────────────────────────────────
    if weather:
        c = weather.get("current", {})
        daily  = weather.get("daily",  [])
        hourly = weather.get("hourly", [])

        lines += [
            "=== CURRENT WEATHER (LIVE, RIGHT NOW) ===",
            f"Location     : {c.get('city', 'Unknown')}, {c.get('country', '')}",
            f"Temperature  : {c.get('temp')}°C  (feels like {c.get('feels_like')}°C)",
            f"Today range  : {c.get('temp_min')}°C min — {c.get('temp_max')}°C max",
            f"Sky          : {c.get('description', c.get('condition', 'N/A'))}",
            f"Humidity     : {c.get('humidity')}%",
            f"Wind         : {c.get('wind_speed')} km/h {c.get('wind_dir', '')}",
            f"Pressure     : {c.get('pressure')} hPa",
            f"UV Index     : {c.get('uv_label', c.get('uv_index', 'N/A'))}",
            f"Visibility   : {c.get('visibility')} km",
            f"Rainfall 1h  : {c.get('rain_1h', 0)} mm",
        ]
        aq = c.get("air_quality", {})
        if aq:
            lines.append(f"Air Quality  : {aq.get('label', 'N/A')}  (AQI {aq.get('aqi', 'N/A')})")

        # Next 6 hours
        if hourly:
            lines.append("\n=== NEXT 6 HOURS ===")
            for h in hourly[:6]:
                lines.append(
                    f"  {h['time']:>5}  {h['condition']:<22}  {h['temp']}°C  "
                    f"Rain {h['rain_prob']}%"
                )

        # 7-day forecast — label today and tomorrow explicitly
        if daily:
            today_label    = datetime.now().strftime("%a")   # e.g. "Wed"
            tomorrow_label = (datetime.now() + timedelta(days=1)).strftime("%a")
            lines.append("\n=== 7-DAY FORECAST ===")
            for i, d in enumerate(daily[:7]):
                tag = ""
                if i == 0: tag = " ← TODAY"
                elif i == 1: tag = " ← TOMORROW"
                lines.append(
                    f"  {d['day']}{tag:<12}  {d['condition']:<22}  "
                    f"{d['temp_min']}–{d['temp_max']}°C  Rain {d['rain_prob']}%"
                )
    else:
        lines.append("=== WEATHER === No live weather data available for this session.")

    # ── Flood prediction ─────────────────────────────────────────────────────
    if flood:
        pct = round(flood["probability"] * 100)
        lines += [
            "\n=== AI FLOOD PREDICTION (CURRENT CONDITIONS) ===",
            f"Flood risk level  : {flood['risk_level']}",
            f"Flood probability : {pct}%",
            f"Flood likely      : {'YES' if flood['flood_likely'] else 'NO'}",
            f"Rainfall 1h       : {flood['rainfall_1h']} mm/h",
            f"Rainfall 24h      : {flood['rainfall_24h']} mm",
            f"Soil moisture     : {round(flood['soil_moisture'] * 100)}% saturated",
            f"Humidity          : {flood['humidity']}%",
            f"Elevation         : {flood['elevation']} m above sea level",
            f"Drainage score    : {flood['drainage']} / 10",
        ]
    else:
        lines.append("\n=== FLOOD PREDICTION === Not available for this session.")

    return "\n".join(lines)


_SYSTEM = """You are **JeevanSetu AI** — a highly accurate, real-time weather and flood-safety assistant built into a disaster-preparedness app used in India.

You have been given LIVE weather data and AI flood prediction for the user's EXACT location right now. Always use this data to answer — never say you don't have weather information.

{weather_context}

---

STRICT RULES:
1. **Always use the live data above** to answer. Never say "I don't have weather data" — you do.
2. For "Can I go out tomorrow?" or "Is it safe?" questions → check tomorrow's forecast rain probability, flood risk, and give a YES/NO recommendation with the specific numbers.
3. For "Will it rain?" → give the EXACT rain probability % from the forecast for that day/time.
4. For flood risk questions → use the flood prediction data (probability %, risk level, soil moisture).
5. Keep answers short and direct: 2–4 sentences. Use bullet points only for complex queries.
6. **Bold** key values: temperatures, percentages, risk levels, day names.
7. End with a short *italic safety tip* when relevant.
8. Respond in the same language the user writes in (English, Kannada, or Hindi).
9. If the question is completely unrelated to weather/safety/floods, politely decline.

ANSWER STYLE EXAMPLES:
- "Is it safe to go out tomorrow?" → "**Tomorrow** looks [condition]. Rain probability is **X%**, temperature **Y–Z°C**. Flood risk is **[level]**. [Yes/No, it is/isn't a good idea to go out]. *[Safety tip].*"
- "Will it rain this weekend?" → "**Saturday**: [condition], **X%** rain chance. **Sunday**: [condition], **Y%** rain chance. [Brief advice]. *[Tip].*"
- "What is the flood risk?" → "Current flood risk is **[level]** with a **X%** probability. Soil is **Y%** saturated. [Brief advice]. *[Tip].*"
"""


def get_ai_response(message: str, history: list, weather_data: dict | None, flood_data: dict | None = None) -> dict:
    if not _key_ok():
        return {
            "response": (
                "⚙️ **Groq API key not set.**\n\n"
                "1. Go to **console.groq.com** → create a free account → API Keys → Create Key\n"
                "2. Add it to `backend/.env`:\n"
                "   `GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxx`\n"
                "3. Restart the backend.\n\n"
                "*It's completely free — no credit card required.*"
            ),
            "suggestions": ["Will it rain today?", "Is it safe to drive?", "Flood risk in my area?"],
        }

    weather_context = _build_weather_context(weather_data, flood_data)
    system_prompt   = _SYSTEM.format(weather_context=weather_context)

    msgs = [{"role": "system", "content": system_prompt}]
    for turn in history[-10:]:
        role    = "assistant" if turn.get("role") in ("assistant", "model") else "user"
        content = turn.get("content") or turn.get("text", "")
        if content:
            msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": message})

    try:
        resp = _req.post(
            _GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model":       _GROQ_MODEL,
                "messages":    msgs,
                "max_tokens":  500,
                "temperature": 0.4,   # lower = more factual, less hallucination
            },
            timeout=30,
        )

        if not resp.ok:
            err = ""
            try: err = resp.json().get("error", {}).get("message", resp.text[:200])
            except: err = resp.text[:200]
            if resp.status_code == 429:
                return {"response": "⏳ AI is busy right now. Please wait a moment and try again.", "suggestions": _suggestions(message)}
            return {"response": f"AI error: {err}", "suggestions": _suggestions(message)}

        text = resp.json()["choices"][0]["message"]["content"]
        return {"response": text, "suggestions": _suggestions(message, text)}

    except Exception as e:
        return {"response": f"Could not reach AI service: {str(e)[:150]}", "suggestions": _suggestions(message)}


def _suggestions(user_msg: str, resp: str = "") -> list[str]:
    m = (user_msg + resp).lower()
    if any(w in m for w in ["tomorrow", "go out", "travel", "safe to"]):
        return ["What about the weekend?", "Flood risk in my area?", "Best time to go out today?"]
    if any(w in m for w in ["rain", "drizzle", "shower"]):
        return ["How long will the rain last?", "Is it safe to drive?", "Best time to go outside?"]
    if any(w in m for w in ["flood", "water", "inundation", "risk"]):
        return ["Nearest emergency shelter?", "What to pack for evacuation?", "Will it rain today?"]
    if any(w in m for w in ["heat", "hot", "sunny"]):
        return ["How to stay safe in heat?", "UV index forecast?", "Best outdoor time today?"]
    if any(w in m for w in ["wind", "storm", "cyclone", "thunder"]):
        return ["Is it safe to go out?", "Storm duration forecast?", "Emergency contacts?"]
    return ["Will it rain tomorrow?", "Flood risk in my area?", "Is it safe to travel today?"]
