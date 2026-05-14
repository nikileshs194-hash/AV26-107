"""
AI service — uses Groq (llama-3.3-70b-versatile, free tier).
Get a free key at https://console.groq.com → API Keys → Create Free Key
Add to backend/.env:  GROQ_API_KEY=gsk_xxxxxxxxxxxx
"""
import requests as _req
from config import GROQ_API_KEY
from datetime import datetime, timezone, timedelta

_GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_MODEL = "llama-3.3-70b-versatile"


def _key_ok() -> bool:
    return bool(GROQ_API_KEY and len(GROQ_API_KEY) > 10)


def _wind_analysis(speed: float) -> str:
    if speed < 5:   return "Calm"
    if speed < 15:  return "Light breeze"
    if speed < 30:  return "Moderate wind"
    if speed < 50:  return "Strong wind — driving caution advised"
    return "Dangerous wind speeds — avoid outdoor activity"


def _humidity_analysis(h: float) -> str:
    if h < 30: return "Very dry — stay hydrated"
    if h < 50: return "Comfortable"
    if h < 70: return "Moderate humidity"
    if h < 85: return "High humidity — feels muggy"
    return "Very high humidity — oppressive, heat stress risk"


def _uv_analysis(uv: float) -> str:
    if uv <= 2:  return f"{uv:.0f} — Low (safe for most)"
    if uv <= 5:  return f"{uv:.0f} — Moderate (wear sunscreen after 30 min)"
    if uv <= 7:  return f"{uv:.0f} — High (limit 10am-4pm exposure, SPF 30+)"
    if uv <= 10: return f"{uv:.0f} — Very High (minimize sun exposure, SPF 50+)"
    return f"{uv:.0f} — Extreme (avoid outdoor activity, full protection)"


def _aqi_analysis(aqi: int, label: str) -> str:
    tips = {
        "Good":               "Air quality excellent — safe for all outdoor activities.",
        "Satisfactory":       "Air quality satisfactory — sensitive groups take minor precautions.",
        "Moderately Polluted":"Air quality moderate — children/elderly limit prolonged outdoor activity.",
        "Poor":               "Air quality poor — everyone should reduce outdoor exertion.",
        "Very Poor":          "Air quality very poor — avoid outdoor activity, wear N95 mask.",
        "Severe":             "Air quality severe — stay indoors, seal windows, use air purifier.",
    }
    return tips.get(label, f"AQI {aqi} — {label}")


def _rain_intensity(mm_h: float) -> str:
    if mm_h == 0:   return "No rain"
    if mm_h < 2.5:  return "Drizzle (light)"
    if mm_h < 7.5:  return "Light rain"
    if mm_h < 15:   return "Moderate rain"
    if mm_h < 30:   return "Heavy rain — expect reduced visibility"
    if mm_h < 60:   return "Very heavy rain — avoid travel"
    return "Extreme rain — severe flooding risk, evacuate low areas"


def _visibility_analysis(km: float) -> str:
    if km >= 10: return f"{km} km — clear"
    if km >= 5:  return f"{km} km — slightly reduced"
    if km >= 2:  return f"{km} km — poor (drive slowly)"
    return f"{km} km — very poor (fog/rain, use headlights)"


def _build_weather_block(label: str, weather: dict, flood: dict | None = None) -> list[str]:
    lines = []
    c      = weather.get("current", {})
    daily  = weather.get("daily",   [])
    hourly = weather.get("hourly",  [])

    city    = c.get("city", "Unknown")
    country = c.get("country", "")
    state   = c.get("state", "")
    loc_str = ", ".join(filter(None, [city, state, country]))

    temp      = c.get("temp", 0)
    humidity  = c.get("humidity", 0)
    wind_spd  = c.get("wind_speed", 0)
    uv        = c.get("uv_index", 0)
    vis       = c.get("visibility", 10)
    rain_1h   = c.get("rain_1h", 0)
    pressure  = c.get("pressure", 1013)

    aq    = c.get("air_quality", {})
    aqi   = aq.get("aqi", 0)
    aq_lb = aq.get("label", "Good")

    lines += [
        f"=== {label}: {loc_str} ===",
        f"Temperature   : {temp}°C  (feels like {c.get('feels_like')}°C)",
        f"Today range   : {c.get('temp_min')}°C min — {c.get('temp_max')}°C max",
        f"Condition     : {c.get('description', c.get('condition', 'N/A'))}",
        f"Humidity      : {humidity}%  → {_humidity_analysis(humidity)}",
        f"Wind          : {wind_spd} km/h {c.get('wind_dir', '')}  → {_wind_analysis(wind_spd)}",
        f"Rain (last 1h): {rain_1h} mm  → {_rain_intensity(rain_1h)}",
        f"Pressure      : {pressure} hPa",
        f"UV Index      : {_uv_analysis(uv)}",
        f"Visibility    : {_visibility_analysis(vis)}",
        f"Air Quality   : {aq_lb}  (NAQI {aqi})  → {_aqi_analysis(aqi, aq_lb)}",
    ]

    # ── Next 6 hours ──────────────────────────────────────────────────────────
    if hourly:
        lines.append(f"\n--- Next 6 Hours ({city}) ---")
        for h in hourly[:6]:
            rain_tag = f"  ⚠ Rain {h['rain_prob']}%" if h['rain_prob'] >= 40 else f"  Rain {h['rain_prob']}%"
            lines.append(
                f"  {h['time']:>5}  {h['condition']:<22}  {h['temp']}°C{rain_tag}"
            )

    # ── 7-day forecast ────────────────────────────────────────────────────────
    if daily:
        lines.append(f"\n--- 7-Day Forecast ({city}) ---")
        for i, d in enumerate(daily[:7]):
            tag = ""
            if i == 0:   tag = " ← TODAY"
            elif i == 1: tag = " ← TOMORROW"
            risk_flag = " ⚠ HIGH RAIN" if d['rain_prob'] >= 70 else ""
            lines.append(
                f"  {d['day']}{tag:<12}  {d['condition']:<24}  "
                f"{d['temp_min']}–{d['temp_max']}°C  Rain {d['rain_prob']}%{risk_flag}"
            )

        # Weekly pattern summary
        avg_rain = sum(d['rain_prob'] for d in daily[:7]) / max(len(daily[:7]), 1)
        max_rain_day = max(daily[:7], key=lambda d: d['rain_prob'])
        lines.append(
            f"\n  Weekly pattern: avg rain probability {avg_rain:.0f}%  |  "
            f"wettest day: {max_rain_day['day']} ({max_rain_day['rain_prob']}%)"
        )

    # ── Flood prediction ──────────────────────────────────────────────────────
    if flood:
        pct = round(flood["probability"] * 100)
        soil_pct = round(flood["soil_moisture"] * 100)
        lines += [
            f"\n--- Flood Prediction ({city}) ---",
            f"Risk level        : {flood['risk_level']}",
            f"Flood probability : {pct}%",
            f"Flood imminent    : {'⚠ YES — EVACUATE LOW AREAS' if flood['flood_likely'] else 'No'}",
            f"Rainfall (1h)     : {flood['rainfall_1h']} mm/h  → {_rain_intensity(flood['rainfall_1h'])}",
            f"Rainfall (24h)    : {flood['rainfall_24h']} mm",
            f"Soil saturation   : {soil_pct}%  {'← Near saturation, runoff risk high' if soil_pct > 70 else ''}",
            f"Elevation         : {flood['elevation']} m  {'← Low-lying area, flood risk elevated' if flood['elevation'] < 50 else ''}",
            f"Drainage score    : {flood['drainage']} / 10  {'← Poor drainage' if flood['drainage'] < 4 else ''}",
        ]

    return lines


def _build_weather_context(
    weather: dict | None,
    flood: dict | None,
    requested_weather: dict | None = None,
    cyclone: dict | None = None,
) -> str:
    lines = []

    if requested_weather:
        lines += _build_weather_block(
            "LIVE WEATHER — REQUESTED CITY", requested_weather
        )
        lines.append("")

    if weather:
        lines += _build_weather_block(
            "LIVE WEATHER — USER'S CURRENT LOCATION", weather, flood
        )
    elif not requested_weather:
        lines.append("=== WEATHER === No live weather data available for this session.")

    if cyclone:
        lines += _build_cyclone_block(cyclone)

    return "\n".join(lines)


def _build_cyclone_block(cyclone: dict) -> list[str]:
    """Build cyclone context for the AI system prompt."""
    if not cyclone:
        return []
    f    = cyclone.get("features", {})
    prob = round(cyclone.get("probability", 0) * 100)
    lines = [
        "\n=== CYCLONE RISK (CURRENT LOCATION) ===",
        f"Risk level        : {cyclone.get('cyclone_risk', 'Unknown')}",
        f"Probability       : {prob}%",
        f"IMD Category      : {cyclone.get('category', 'N/A')}",
        f"Cyclone likely    : {'⚠ YES' if cyclone.get('cyclone_likely') else 'No'}",
        f"Wind speed        : {f.get('wind_speed_kmh', 0)} km/h",
        f"Wind gusts        : {f.get('wind_gusts_kmh', 0)} km/h",
        f"Surface pressure  : {f.get('surface_pressure_hpa', 0)} hPa  "
        f"{'← VERY LOW — cyclone eye nearby' if f.get('surface_pressure_hpa', 1013) < 980 else ''}",
        f"Pressure drop 6h  : {f.get('pressure_drop_6h', 0)} hPa  "
        f"{'← RAPID DEEPENING' if f.get('pressure_drop_6h', 0) >= 4 else ''}",
        f"CAPE              : {f.get('cape_jkg', 0)} J/kg",
        f"Coastal distance  : {f.get('coastal_proximity_km', 0)} km",
        f"Season factor     : {'Peak season' if f.get('season_factor', 1) >= 1.2 else 'Off-season'}",
    ]
    if f.get("gdacs_active"):
        lines.append(
            f"⚠ ACTIVE CYCLONE : '{f.get('gdacs_name', 'TC')}' is "
            f"{f.get('gdacs_distance_km', 0):.0f} km away "
            f"(GDACS alert: {f.get('gdacs_alert_level', 'Unknown')})"
        )
    return lines


_SYSTEM = """You are **JeevanSetu AI** — India's most accurate real-time weather, climate, and flood-safety assistant. You are embedded in a disaster-preparedness app.

You have LIVE data fetched RIGHT NOW from global meteorological APIs (Open-Meteo, OpenWeather). Use it precisely.

{weather_context}

---

## CORE DIRECTIVES

1. **ALWAYS use the live data above.** Never say "I don't have weather data" — you always do.
2. **Requested city takes priority.** If data shows "LIVE WEATHER — REQUESTED CITY", answer using THAT data, not the user's GPS location.
3. **Be a climate analyst, not just a data reader.** Interpret the numbers: explain what they MEAN for safety, travel, outdoor activity.
4. **Precise numbers.** Always quote actual figures from the data — temperature, rain %, humidity, AQI.
5. **Short and direct.** 2–4 sentences max for simple questions. Use bullet points only for multi-day or complex queries.
6. **Bold** key values: temperatures, percentages, risk levels, day names.
7. End with a *italic safety tip* when relevant.
8. Match the user's language (English, Kannada, Hindi).
9. For cyclone risk → use the CYCLONE RISK section (probability, IMD category, gusts, pressure, GDACS). "Cyclonic Storm", "Severe Cyclonic Storm" etc. are IMD categories.
10. Decline questions unrelated to weather / safety / climate / floods / cyclones.
11. NEVER invent data. If a value is missing, skip it.

---

## ANSWER TEMPLATES

**City weather query** ("Mysore", "weather in Bangalore"):
→ "In **[City]**, it's currently **[condition]**, **X°C** (feels like Y°C). Humidity **H%**, wind **W km/h**. This week: [brief pattern]. *[Safety/outdoor tip].*"

**Travel safety** ("safe to go to Mysore", "can I travel to Chennai?"):
→ "**[City]** weather today: **[condition]**, **X°C**, rain chance **Z%**. [Safe/caution/avoid] because [specific reason with numbers]. *[Tip].*"

**Rain query** ("will it rain?", "rain this weekend?"):
→ "**[Day]** in **[City]**: **[condition]**, **X%** rain probability, **Y–Z°C**. [Risk level advice]. *[Tip].*"

**Climate/analysis query** ("how is the climate in Mysore?", "analyze weather"):
→ Give a structured 4–5 point analysis: current conditions, weekly forecast pattern, humidity/heat stress, air quality, flood risk if applicable.

**Flood risk** ("flood risk?", "is flooding likely?"):
→ "Flood risk is **[level]** (**X%** probability). Soil **Y%** saturated, rainfall **Z mm/h**. [Safe/evacuate/caution]. *[Tip].*"

**Cyclone risk** ("cyclone risk?", "is there a cyclone?", "cyclone warning?"):
→ "Cyclone risk is **[level]** (**X%** probability) — **[IMD Category]**. Wind gusts **W km/h**, pressure **P hPa**. [GDACS warning if active]. *[Evacuation/shelter tip].*"

**Comparison** ("is Mysore better than Bangalore for travel?"):
→ Compare both cities side by side with actual data. Give a clear recommendation.

---

## CLIMATE ANALYSIS FORMAT (for "analyze", "climate", "tell me about" queries)

Use this structure:
🌡️ **Temperature**: [current + today range]
💧 **Humidity**: [value + comfort level]
🌧️ **Rainfall outlook**: [weekly pattern + wettest day]
💨 **Wind & Visibility**: [conditions]
🌿 **Air Quality**: [AQI + label + advice]
🏞️ **Flood Risk**: [level + probability]
🌀 **Cyclone Risk**: [level + IMD category + wind gusts]
✅ **Verdict**: [1 sentence overall assessment]
"""


def get_ai_response(
    message: str,
    history: list,
    weather_data: dict | None,
    flood_data: dict | None = None,
    requested_weather: dict | None = None,
    cyclone_data: dict | None = None,
) -> dict:
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

    weather_context = _build_weather_context(weather_data, flood_data, requested_weather, cyclone_data)
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
                "max_tokens":  600,
                "temperature": 0.3,
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
    if any(w in m for w in ["tomorrow", "go out", "travel", "safe to", "can i"]):
        return ["What about the weekend?", "Flood risk in my area?", "Best time to go out today?"]
    if any(w in m for w in ["rain", "drizzle", "shower"]):
        return ["How long will the rain last?", "Is it safe to drive?", "Best time to go outside?"]
    if any(w in m for w in ["flood", "water", "inundation", "risk"]):
        return ["Nearest emergency shelter?", "What to pack for evacuation?", "Will it rain today?"]
    if any(w in m for w in ["heat", "hot", "sunny", "uv"]):
        return ["How to stay safe in heat?", "UV index forecast?", "Best outdoor time today?"]
    if any(w in m for w in ["wind", "storm", "cyclone", "thunder"]):
        return ["Is it safe to go out?", "Storm duration forecast?", "Emergency contacts?"]
    if any(w in m for w in ["air", "aqi", "quality", "pollution", "smog"]):
        return ["Is it safe to exercise outside?", "Best time for outdoor activity?", "Flood risk in my area?"]
    if any(w in m for w in ["cyclone", "hurricane", "tropical", "storm surge", "landfall", "imd", "depression", "severe cyclonic"]):
        return ["Is it safe to stay here?", "What to pack for cyclone evacuation?", "Flood risk in my area?"]
    if any(w in m for w in ["climate", "analyze", "analysis", "mysore", "bangalore", "chennai", "mumbai", "delhi", "hyderabad", "kolkata", "pune"]):
        return ["Will it rain there tomorrow?", "Is it safe to travel there?", "Compare with my location"]
    return ["Will it rain tomorrow?", "Cyclone risk in my area?", "Is it safe to travel today?"]
