"""
Two independent background loops:

  LOOP 1 — flood_check_loop()   → every 60 seconds
    Run the ML flood model for every user with a location.
    The MOMENT it predicts High risk → send push notification immediately.
    30-min cooldown per user so the same person is not spammed.
    Also saves a Severe flood alert card to the user's Alerts tab.

  LOOP 2 — weather_tip_loop()   → every 5 minutes
    Fetch current weather for every user.
    Generate a human-readable tip (rain / heat / nice day / etc.).
    Save it as an alert CARD to user_alerts DB table
    → it instantly appears in the Alerts tab in the app, stacked newest-first.
    Also sends a light push notification banner.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Intervals ────────────────────────────────────────────────────────────────
FLOOD_CHECK_SECS    = 60          # run every 1 minute — fire the moment flood predicted
WEATHER_TIP_SECS    = 5 * 60     # run every 5 minutes — add tip card to Alerts tab
FLOOD_COOLDOWN_SECS = 30 * 60    # 30-min gap between flood alerts per user

# Per-user flood alert cooldown: { phone: last_alert_datetime }
_flood_cooldown: dict[str, datetime] = {}

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _send_pushes(messages: list[dict]) -> None:
    """Batch push to Expo (sync — called via asyncio.to_thread)."""
    import requests as _req
    if not messages:
        return
    try:
        resp = _req.post(
            EXPO_PUSH_URL,
            json=messages,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=15,
        )
        data = resp.json().get("data", [])
        ok   = sum(1 for d in data if isinstance(d, dict) and d.get("status") == "ok") \
               if isinstance(data, list) else len(messages)
        logger.info(f"[Scheduler] Push: {ok}/{len(messages)} ok")
    except Exception as e:
        logger.warning(f"[Scheduler] Push error: {e}")


def _get_all_users_with_token() -> list[dict]:
    """Return users who have a push_token AND a saved location."""
    try:
        from services.supabase_service import _get_service_client
        db = _get_service_client()
        if not db:
            return []
        res = db.table("users").select(
            "full_name,phone,push_token,latitude,longitude"
        ).execute()
        return [
            u for u in (res.data or [])
            if u.get("push_token") and u.get("latitude") and u.get("longitude")
        ]
    except Exception as e:
        logger.warning(f"[Scheduler] get_users error: {e}")
        return []


def _save_alert_to_db(phone: str, alert: dict) -> None:
    """
    Insert one alert card into user_alerts so it appears in the Alerts tab.
    alert keys: alert_id, title, description, severity, source, location,
                icon, icon_bg, icon_color, border_color, when_text, when_color
    """
    try:
        from services.supabase_service import _get_service_client
        db = _get_service_client()
        if not db:
            return
        row = {"phone": phone, **alert}
        db.table("user_alerts").upsert(row, on_conflict="phone,alert_id").execute()
    except Exception as e:
        logger.warning(f"[Scheduler] save_alert error: {e}")


# ── Shelter lookup ────────────────────────────────────────────────────────────

def _get_nearest_shelter_osm(lat: float, lon: float) -> Optional[dict]:
    """OSM Overpass fallback — finds nearest shelter/school within 3 km."""
    import requests as _req
    from math import radians, cos, sin, asin, sqrt

    query = f"""
[out:json][timeout:15];
(
  node["amenity"~"shelter|community_centre|school|hospital"](around:3000,{lat},{lon});
  way["amenity"~"shelter|community_centre|school|hospital"](around:3000,{lat},{lon});
);
out center 5;
"""
    try:
        r        = _req.post("https://overpass-api.de/api/interpreter",
                             data={"data": query}, timeout=20)
        elements = r.json().get("elements", [])
        if not elements:
            return None
        el   = elements[0]
        slat = el.get("lat") or el.get("center", {}).get("lat", lat)
        slon = el.get("lon") or el.get("center", {}).get("lon", lon)
        name = el.get("tags", {}).get("name", "Nearest Safe Location")
        R    = 6371000
        dlat = radians(slat - lat)
        dlon = radians(slon - lon)
        a    = sin(dlat/2)**2 + cos(radians(lat)) * cos(radians(slat)) * sin(dlon/2)**2
        dist_m   = int(2 * R * asin(sqrt(a)))
        dist_str = f"{dist_m/1000:.1f} km" if dist_m >= 1000 else f"{dist_m} m"
        return {
            "name": name, "distance_m": dist_m, "distance_str": dist_str,
            "lat": slat, "lon": slon,
            "maps_url": f"https://www.google.com/maps/dir/?api=1&destination={slat},{slon}",
        }
    except Exception as e:
        logger.warning(f"[Scheduler] OSM shelter error: {e}")
        return None


def _get_shelter_for_user(lat: float, lon: float) -> dict:
    """Supabase shelters → OSM fallback → generic Google Maps link."""
    from services.supabase_service import get_nearby_shelters
    shelters = get_nearby_shelters(lat, lon, radius_km=10)
    if shelters:
        s        = shelters[0]
        dist_km  = s.get("distance_km", 0)
        dist_m   = int(dist_km * 1000)
        dist_str = f"{dist_km} km" if dist_km >= 1 else f"{dist_m} m"
        slat, slon = s.get("latitude", lat), s.get("longitude", lon)
        return {
            "name": s.get("name", "Safe Shelter"), "distance_m": dist_m,
            "distance_str": dist_str, "lat": slat, "lon": slon,
            "maps_url": f"https://www.google.com/maps/dir/?api=1&destination={slat},{slon}",
        }
    osm = _get_nearest_shelter_osm(lat, lon)
    if osm:
        return osm
    return {
        "name": "Nearest Government Shelter", "distance_m": 500,
        "distance_str": "~500 m", "lat": lat, "lon": lon,
        "maps_url": f"https://www.google.com/maps/search/emergency+shelter/@{lat},{lon},15z",
    }


# ── LOOP 1 — Flood check (every 60 seconds) ───────────────────────────────────

def _run_flood_check_sync(users: list[dict]) -> list[dict]:
    """
    Synchronous flood prediction for all users (called via to_thread so it
    does not block the event loop while the ML model and HTTP calls run).
    Returns list of push payloads to send.
    """
    try:
        from routes.predict import _model, _fetch_features, _risk_label
        import pandas as pd
    except Exception:
        return []

    if _model is None:
        return []

    now      = datetime.now(timezone.utc)
    messages = []

    for u in users:
        lat, lon = float(u["latitude"]), float(u["longitude"])
        phone    = u.get("phone", "")

        # Cooldown guard
        last = _flood_cooldown.get(phone)
        if last and (now - last).total_seconds() < FLOOD_COOLDOWN_SECS:
            continue

        try:
            features = _fetch_features(lat, lon)
            df       = pd.DataFrame([features])
            prob     = float(_model.predict_proba(df)[0][1])
            risk     = _risk_label(prob)
        except Exception as e:
            logger.warning(f"[FloodCheck] predict error ({phone}): {e}")
            continue

        if risk != "High":
            continue

        # Flood confirmed — update cooldown
        _flood_cooldown[phone] = now

        # Get nearest shelter
        shelter  = _get_shelter_for_user(lat, lon)
        pct      = round(prob * 100)
        now_str  = now.strftime("%H:%M")

        # ── Save alert card to DB (shows in Alerts tab) ──────────────────
        _save_alert_to_db(phone, {
            "alert_id":    f"flood_{phone}_{int(now.timestamp())}",
            "title":       "🚨 Urban Flood Alert — Evacuate Now",
            "description": (
                f"High flood probability ({pct}%) detected at your location. "
                f"Nearest shelter: {shelter['name']} ({shelter['distance_str']}). "
                f"Please move to higher ground immediately."
            ),
            "severity":    "Extreme",
            "source":      "Flood AI Model",
            "location":    f"{round(lat,4)}, {round(lon,4)}",
            "icon":        "warning",
            "icon_bg":     "#FEE2E2",
            "icon_color":  "#E53935",
            "border_color":"#E53935",
            "when_text":   f"Just now · {now_str}",
            "when_color":  "#E53935",
        })

        # ── Push notification ─────────────────────────────────────────────
        messages.append({
            "to":        u["push_token"],
            "title":     "🚨 URBAN FLOOD ALERT",
            "body":      (
                f"High flood risk ({pct}%) at your location. "
                f"Nearest shelter: {shelter['name']} — {shelter['distance_str']}."
            ),
            "sound":     "default",
            "priority":  "high",
            "badge":     1,
            "channelId": "sos",
            "data": {
                "type":             "flood_alert",
                "probability":      round(prob, 3),
                "risk_level":       risk,
                "shelter_name":     shelter["name"],
                "shelter_distance": shelter["distance_str"],
                "shelter_maps_url": shelter["maps_url"],
                "shelter_lat":      shelter["lat"],
                "shelter_lon":      shelter["lon"],
                "user_lat":         lat,
                "user_lon":         lon,
            },
        })
        logger.info(f"[FloodCheck] 🚨 High risk ({pct}%) for {phone} — alert queued")

    return messages


async def flood_check_loop() -> None:
    """Runs every 60 seconds. Fires flood alert the moment risk = High."""
    logger.info("[FloodCheck] Loop started — checking every 60 s")
    while True:
        try:
            users = await asyncio.to_thread(_get_all_users_with_token)
            if users:
                messages = await asyncio.to_thread(_run_flood_check_sync, users)
                if messages:
                    await asyncio.to_thread(_send_pushes, messages)
        except Exception as e:
            logger.error(f"[FloodCheck] Loop error: {e}")

        await asyncio.sleep(FLOOD_CHECK_SECS)


# ── LOOP 2 — Weather tips → Alerts tab (every 5 minutes) ─────────────────────

def _build_weather_tip(lat: float, lon: float, user_name: str) -> Optional[dict]:
    """
    Fetch live weather and return a fully-formed alert row dict ready for DB.
    Returns None on error.
    """
    import requests as _req
    from config import OPENWEATHER_API_KEY
    try:
        r = _req.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY, "units": "metric"},
            timeout=10,
        )
        d         = r.json()
        temp      = d.get("main", {}).get("temp", 25)
        humidity  = d.get("main", {}).get("humidity", 60)
        rain_1h   = d.get("rain", {}).get("1h", 0)
        condition = (d.get("weather") or [{}])[0].get("main", "Clear")
        desc      = (d.get("weather") or [{}])[0].get("description", "clear sky").capitalize()
        city      = d.get("name", "your area")
        now       = datetime.now(timezone.utc)
        now_str   = now.strftime("%H:%M")

        # Pick condition bucket → title / body / icon / colors / severity
        if rain_1h > 15:
            title      = "🌧️ Heavy Rain — Stay Indoors"
            body       = f"{rain_1h:.1f} mm/h in {city}. Avoid low-lying roads and underpasses."
            icon       = "rainy"
            icon_bg    = "#E3F2FD"
            icon_color = "#1565C0"
            border     = "#1565C0"
            when_color = "#1565C0"
            severity   = "Severe"
            when_label = "Severe"
        elif rain_1h > 3:
            title      = "🌦️ Light Rain Advisory"
            body       = f"Light rain ({rain_1h:.1f} mm/h) in {city}. Carry an umbrella."
            icon       = "rainy-outline"
            icon_bg    = "#E3F2FD"
            icon_color = "#1976D2"
            border     = "#1976D2"
            when_color = "#1976D2"
            severity   = "Moderate"
            when_label = "Moderate"
        elif condition == "Thunderstorm":
            title      = "⛈️ Thunderstorm Warning"
            body       = f"Thunderstorm in {city}. Stay indoors and away from open areas."
            icon       = "thunderstorm"
            icon_bg    = "#F3E5F5"
            icon_color = "#7B1FA2"
            border     = "#7B1FA2"
            when_color = "#7B1FA2"
            severity   = "Severe"
            when_label = "Severe"
        elif humidity > 88:
            title      = "💧 High Humidity Advisory"
            body       = f"Humidity is {humidity}% in {city}. Stay hydrated and limit outdoor activity."
            icon       = "water"
            icon_bg    = "#E3F2FD"
            icon_color = "#0288D1"
            border     = "#0288D1"
            when_color = "#0288D1"
            severity   = "Moderate"
            when_label = "Moderate"
        elif temp > 40:
            title      = "🌡️ Extreme Heat Warning"
            body       = f"Temperature reaching {temp:.0f}°C in {city}. Drink water and avoid direct sun."
            icon       = "thermometer"
            icon_bg    = "#FFF3E0"
            icon_color = "#E64A19"
            border     = "#E64A19"
            when_color = "#E64A19"
            severity   = "Severe"
            when_label = "Severe"
        elif temp > 34:
            title      = "☀️ Heat Advisory"
            body       = f"It's {temp:.0f}°C in {city}. Seek shade, stay cool and hydrated."
            icon       = "sunny"
            icon_bg    = "#FFF8E1"
            icon_color = "#F9A825"
            border     = "#F9A825"
            when_color = "#F9A825"
            severity   = "Moderate"
            when_label = "Moderate"
        elif condition in ("Fog", "Mist"):
            title      = "🌫️ Low Visibility Advisory"
            body       = f"Fog/mist in {city}. Drive with headlights on and reduce speed."
            icon       = "cloudy"
            icon_bg    = "#ECEFF1"
            icon_color = "#607D8B"
            border     = "#607D8B"
            when_color = "#607D8B"
            severity   = "Minor"
            when_label = "Advisory"
        else:
            # Nice / normal weather
            title      = f"🌤️ Weather Update — {city}"
            body       = f"{desc}, {temp:.0f}°C, Humidity {humidity}%. A good time to stay flood-aware."
            icon       = "partly-sunny"
            icon_bg    = "#E8F5E9"
            icon_color = "#43A047"
            border     = "#43A047"
            when_color = "#43A047"
            severity   = "Minor"
            when_label = "Info"

        return {
            "alert_id":    f"tip_{uuid.uuid4().hex[:12]}",   # unique every 5 min
            "title":       title,
            "description": body,
            "severity":    severity,
            "source":      "Weather Monitor",
            "location":    city,
            "icon":        icon,
            "icon_bg":     icon_bg,
            "icon_color":  icon_color,
            "border_color": border,
            "when_text":   f"{when_label} · {now_str}",
            "when_color":  when_color,
            # push payload for the banner
            "_push_title": title,
            "_push_body":  body,
        }
    except Exception as e:
        logger.warning(f"[WeatherTip] build error: {e}")
        return None


async def weather_tip_loop() -> None:
    """
    Runs every 5 minutes.
    For each user: build weather tip → save to DB (Alerts tab card) + push banner.
    """
    logger.info("[WeatherTip] Loop started — saving tip cards every 5 min")
    while True:
        try:
            users = await asyncio.to_thread(_get_all_users_with_token)
            if users:
                logger.info(f"[WeatherTip] Processing {len(users)} user(s)")
                push_msgs = []

                for u in users:
                    lat   = float(u["latitude"])
                    lon   = float(u["longitude"])
                    phone = u.get("phone", "")
                    name  = u.get("full_name", "User")

                    tip = await asyncio.to_thread(_build_weather_tip, lat, lon, name)
                    if not tip:
                        continue

                    # Extract push-only keys before saving to DB
                    push_title = tip.pop("_push_title")
                    push_body  = tip.pop("_push_body")

                    # Save card to DB → appears in Alerts tab immediately
                    await asyncio.to_thread(_save_alert_to_db, phone, tip)

                    # Queue push banner
                    push_msgs.append({
                        "to":        u["push_token"],
                        "title":     push_title,
                        "body":      push_body,
                        "sound":     "default",
                        "priority":  "normal",
                        "channelId": "weather",
                        "data":      {"type": "weather_tip"},
                    })

                if push_msgs:
                    await asyncio.to_thread(_send_pushes, push_msgs)
                    logger.info(f"[WeatherTip] Saved cards + sent {len(push_msgs)} banners")

        except Exception as e:
            logger.error(f"[WeatherTip] Loop error: {e}")

        await asyncio.sleep(WEATHER_TIP_SECS)


# ── LOOP 3 — Daily chat cleanup at midnight IST ───────────────────────────────

from datetime import timezone, timedelta as _td
_IST = timezone(_td(hours=5, minutes=30))

async def chat_cleanup_loop() -> None:
    """
    Runs every hour. At the first tick past midnight IST, wipes all chat
    messages from previous IST days so every user starts fresh each day.
    """
    logger.info("[ChatCleanup] Loop started — checking every hour")
    _last_cleanup_date: list[str] = [""]   # mutable container for closure

    while True:
        try:
            now_ist = datetime.now(_IST)
            today_str = now_ist.strftime("%Y-%m-%d")

            if today_str != _last_cleanup_date[0]:
                # New IST day — clear old messages
                from routes.chat import _clear_old_messages
                count = await asyncio.to_thread(_clear_old_messages)
                _last_cleanup_date[0] = today_str
                logger.info(f"[ChatCleanup] ✅ Cleared {count} old messages for {today_str}")
        except Exception as e:
            logger.error(f"[ChatCleanup] Error: {e}")

        await asyncio.sleep(3600)   # check every hour


# ── Entry point ───────────────────────────────────────────────────────────────

async def run_scheduler() -> None:
    """
    Start all three loops concurrently.
    Called from main.py lifespan — runs for the entire server lifetime.
    """
    logging.basicConfig(level=logging.INFO)
    logger.info("[Scheduler] Starting all loops...")
    await asyncio.gather(
        flood_check_loop(),
        weather_tip_loop(),
        chat_cleanup_loop(),
    )
