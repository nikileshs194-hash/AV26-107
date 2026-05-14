"""
Real-time weather alert engine — works globally (India, USA, everywhere).
Sources:
  1. OWM current weather  → immediate conditions
  2. OWM 5-day forecast   → upcoming severe weather
  3. OWM air pollution    → air quality index
  4. NOAA (US only)       → official NWS alerts when available
"""
import requests
from datetime import datetime, timezone
from config import OPENWEATHER_API_KEY, OWM_BASE, NOAA_BASE


# ── Helpers ───────────────────────────────────────────────────────────────────

def _time_ago(iso_str: str) -> str:
    if not iso_str: return "Just now"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        secs = int((datetime.now(timezone.utc) - dt).total_seconds())
        if secs < 60:    return "Just now"
        if secs < 3600:  return f"{secs // 60} min ago"
        if secs < 86400: return f"{secs // 3600} hr ago"
        return f"{secs // 86400}d ago"
    except Exception:
        return "Just now"


def _fmt_dt(ts: int) -> str:
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b %d, %I:%M %p")
    except Exception:
        return "Upcoming"


def _alert(id, title, icon, icon_bg, icon_color, border, time_str, when, when_color, desc, location, severity, source):
    return {
        "id": id, "title": title, "icon": icon,
        "iconBg": icon_bg, "iconColor": icon_color, "borderColor": border,
        "time": time_str, "when": when, "whenColor": when_color,
        "desc": desc, "location": location, "severity": severity, "source": source,
    }


# ── NOAA (US only) ────────────────────────────────────────────────────────────

def _get_noaa_alerts(lat: float, lon: float) -> list:
    try:
        headers = {"User-Agent": "FloodAI/1.0 (nikileshs194@gmail.com)"}
        r = requests.get(
            f"{NOAA_BASE}/alerts/active?point={lat},{lon}&status=actual",
            headers=headers, timeout=8,
        )
        if r.status_code != 200:
            return []
        alerts = []
        icon_map = {
            "flood": "water-outline", "thunder": "thunderstorm-outline",
            "rain": "rainy-outline", "wind": "flag-outline",
            "heat": "sunny-outline", "fog": "cloudy-outline",
            "snow": "snow-outline", "fire": "flame-outline",
            "air": "leaf-outline", "tornado": "warning-outline",
            "hurricane": "warning-outline", "cyclone": "warning-outline",
        }
        sev_color = {"Extreme": "#E53935", "Severe": "#E53935", "Moderate": "#FB8C00", "Minor": "#43A047"}
        sev_bg    = {"Extreme": "#FEE2E2", "Severe": "#FEE2E2", "Moderate": "#FFF3E0", "Minor": "#E8F5E9"}
        for f in r.json().get("features", []):
            p = f.get("properties", {})
            sev   = p.get("severity", "Minor")
            event = p.get("event", "Weather Alert")
            desc  = p.get("description", "")[:200].replace("\n", " ")
            icon  = next((v for k, v in icon_map.items() if k in event.lower()), "warning-outline")
            col   = sev_color.get(sev, "#43A047")
            alerts.append(_alert(
                id=p.get("id", f"noaa_{len(alerts)}"),
                title=event, icon=icon,
                icon_bg=sev_bg.get(sev, "#E3F2FD"), icon_color=col, border=col,
                time_str=_time_ago(p.get("sent", "")),
                when=p.get("onset", "Active now")[:16],
                when_color=col, desc=desc,
                location=p.get("areaDesc", f"{lat:.2f}, {lon:.2f}"),
                severity=sev, source="NWS",
            ))
        return alerts
    except Exception:
        return []


# ── OWM Current weather alerts ────────────────────────────────────────────────

def _get_current_alerts(lat: float, lon: float, location_name: str) -> list:
    try:
        r = requests.get(
            f"{OWM_BASE}/weather",
            params={"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY, "units": "metric"},
            timeout=8,
        )
        r.raise_for_status()
        d = r.json()
        alerts = []
        seen   = set()

        weather_id   = d.get("weather", [{}])[0].get("id", 800)
        weather_main = d.get("weather", [{}])[0].get("main", "")
        temp         = d.get("main", {}).get("temp", 25)
        feels_like   = d.get("main", {}).get("feels_like", 25)
        humidity     = d.get("main", {}).get("humidity", 50)
        wind_mps     = d.get("wind", {}).get("speed", 0)
        wind_kmh     = wind_mps * 3.6
        visibility   = d.get("visibility", 10000)
        rain_1h      = d.get("rain", {}).get("1h", 0)
        now_str      = datetime.now(timezone.utc).strftime("%I:%M %p")

        # ── Thunderstorm (codes 200–232) ──
        if 200 <= weather_id <= 232 and "thunder" not in seen:
            seen.add("thunder")
            alerts.append(_alert(
                id="curr_thunder", title="⚡ Thunderstorm Alert",
                icon="thunderstorm-outline", icon_bg="#FFF3E0", icon_color="#FF6F00", border="#FF6F00",
                time_str="Now", when=f"Active since {now_str}", when_color="#FF6F00",
                desc=f"Thunderstorm currently active in {location_name}. Lightning, gusty winds ({wind_kmh:.0f} km/h) and heavy downpours expected. Stay indoors, avoid trees and metal objects.",
                location=location_name, severity="Severe", source="Live Weather",
            ))

        # ── Heavy / Extreme Rain ──
        if rain_1h >= 15 and "extreme_rain" not in seen:
            seen.add("extreme_rain")
            alerts.append(_alert(
                id="curr_xrain", title="🌊 Extreme Rainfall Warning",
                icon="water-outline", icon_bg="#FEE2E2", icon_color="#E53935", border="#E53935",
                time_str="Now", when=f"Since {now_str}", when_color="#E53935",
                desc=f"Extremely heavy rain ({rain_1h:.1f} mm/hr) currently falling in {location_name}. High risk of flash flooding. Move to higher ground immediately. Avoid roads and underpasses.",
                location=location_name, severity="Extreme", source="Live Weather",
            ))
        elif rain_1h >= 7.5 and "heavy_rain" not in seen:
            seen.add("heavy_rain")
            alerts.append(_alert(
                id="curr_hrain", title="🌧 Heavy Rain Warning",
                icon="rainy-outline", icon_bg="#FEE2E2", icon_color="#E53935", border="#E53935",
                time_str="Now", when=f"Since {now_str}", when_color="#E53935",
                desc=f"Heavy rainfall ({rain_1h:.1f} mm/hr) in {location_name}. Flooding of low-lying areas possible. Avoid waterlogged roads. Keep drainage clear.",
                location=location_name, severity="Severe", source="Live Weather",
            ))
        elif rain_1h >= 2.5 and "moderate_rain" not in seen:
            seen.add("moderate_rain")
            alerts.append(_alert(
                id="curr_mrain", title="🌦 Moderate Rain Advisory",
                icon="rainy-outline", icon_bg="#FFF3E0", icon_color="#FB8C00", border="#FB8C00",
                time_str="Now", when=f"Since {now_str}", when_color="#FB8C00",
                desc=f"Moderate rain ({rain_1h:.1f} mm/hr) ongoing in {location_name}. Roads may be slippery. Carry an umbrella and drive carefully.",
                location=location_name, severity="Moderate", source="Live Weather",
            ))

        # ── Extreme Heat ──
        if temp >= 42 and "extreme_heat" not in seen:
            seen.add("extreme_heat")
            alerts.append(_alert(
                id="curr_xheat", title="🔥 Extreme Heat Warning",
                icon="sunny-outline", icon_bg="#FEE2E2", icon_color="#E53935", border="#E53935",
                time_str="Now", when="Today", when_color="#E53935",
                desc=f"Dangerous heat: {temp:.0f}°C (feels like {feels_like:.0f}°C) in {location_name}. Risk of heat stroke. Stay indoors between 11 AM–4 PM, drink plenty of water, avoid direct sunlight.",
                location=location_name, severity="Extreme", source="Live Weather",
            ))
        elif temp >= 38 and "heat" not in seen:
            seen.add("heat")
            alerts.append(_alert(
                id="curr_heat", title="☀️ Heat Wave Advisory",
                icon="sunny-outline", icon_bg="#FFF3E0", icon_color="#FB8C00", border="#FB8C00",
                time_str="Now", when="Today", when_color="#FB8C00",
                desc=f"Very high temperature: {temp:.0f}°C (feels {feels_like:.0f}°C) in {location_name}. Stay hydrated, wear light clothing and limit outdoor activity during peak hours.",
                location=location_name, severity="Moderate", source="Live Weather",
            ))

        # ── Strong Winds ──
        if wind_kmh >= 90 and "cyclone" not in seen:
            seen.add("cyclone")
            alerts.append(_alert(
                id="curr_cyclone", title="🌀 Cyclonic Wind Warning",
                icon="warning-outline", icon_bg="#FEE2E2", icon_color="#E53935", border="#E53935",
                time_str="Now", when=f"Since {now_str}", when_color="#E53935",
                desc=f"Extremely dangerous winds ({wind_kmh:.0f} km/h) in {location_name}. Cyclonic conditions. Do not go outdoors. Secure loose objects. Follow local authority instructions.",
                location=location_name, severity="Extreme", source="Live Weather",
            ))
        elif wind_kmh >= 60 and "storm_wind" not in seen:
            seen.add("storm_wind")
            alerts.append(_alert(
                id="curr_wind", title="💨 Strong Wind Warning",
                icon="flag-outline", icon_bg="#FFF3E0", icon_color="#FB8C00", border="#FB8C00",
                time_str="Now", when=f"Since {now_str}", when_color="#FB8C00",
                desc=f"Strong winds ({wind_kmh:.0f} km/h) currently in {location_name}. Avoid driving high-sided vehicles. Secure outdoor furniture and loose objects.",
                location=location_name, severity="Moderate", source="Live Weather",
            ))

        # ── Dense Fog ──
        if (weather_id in (741, 701, 721, 731, 751, 761, 762) or visibility < 500) and "fog" not in seen:
            seen.add("fog")
            vis_str = f"{visibility}m" if visibility < 1000 else f"{visibility/1000:.1f}km"
            alerts.append(_alert(
                id="curr_fog", title="🌫 Dense Fog Advisory",
                icon="cloudy-outline", icon_bg="#F3F4F6", icon_color="#6B7280", border="#6B7280",
                time_str="Now", when="Active now", when_color="#6B7280",
                desc=f"Visibility reduced to {vis_str} in {location_name}. Drive slowly with fog lights on. Allow extra stopping distance. Avoid highways if possible.",
                location=location_name, severity="Moderate", source="Live Weather",
            ))

        return alerts
    except Exception as e:
        print(f"[Alerts/Current] {e}")
        return []


# ── OWM Forecast alerts (upcoming severe weather) ─────────────────────────────

def _get_forecast_alerts(lat: float, lon: float, location_name: str) -> list:
    try:
        r = requests.get(
            f"{OWM_BASE}/forecast",
            params={"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY, "units": "metric", "cnt": 24},
            timeout=8,
        )
        r.raise_for_status()
        alerts, seen = [], set()

        for item in r.json().get("list", []):
            weather_id   = item.get("weather", [{}])[0].get("id", 800)
            weather_main = item.get("weather", [{}])[0].get("main", "")
            pop          = item.get("pop", 0)         # probability of precipitation 0-1
            rain_3h      = item.get("rain", {}).get("3h", 0)
            wind_kmh     = item.get("wind", {}).get("speed", 0) * 3.6
            temp_max     = item.get("main", {}).get("temp_max", 25)
            dt_str       = _fmt_dt(item["dt"])

            # Upcoming thunderstorm
            if 200 <= weather_id <= 232 and "fc_thunder" not in seen:
                seen.add("fc_thunder")
                alerts.append(_alert(
                    id=f"fc_thunder_{item['dt']}", title="⚡ Thunderstorm Forecast",
                    icon="thunderstorm-outline", icon_bg="#FFF3E0", icon_color="#FF6F00", border="#FF6F00",
                    time_str="Upcoming", when=dt_str, when_color="#FF6F00",
                    desc=f"Thunderstorm expected in {location_name} around {dt_str}. Prepare for lightning, gusty winds and heavy rain. Secure outdoor items in advance.",
                    location=location_name, severity="Severe", source="Forecast",
                ))

            # Upcoming heavy rain
            if rain_3h >= 15 and pop >= 0.5 and "fc_xrain" not in seen:
                seen.add("fc_xrain")
                alerts.append(_alert(
                    id=f"fc_xrain_{item['dt']}", title="🌊 Heavy Rain Forecast",
                    icon="rainy-outline", icon_bg="#FEE2E2", icon_color="#E53935", border="#E53935",
                    time_str="Upcoming", when=dt_str, when_color="#E53935",
                    desc=f"Heavy rain ({rain_3h:.0f} mm) expected in {location_name} around {dt_str} (probability: {pop*100:.0f}%). Risk of waterlogging and flooding in low-lying areas.",
                    location=location_name, severity="Severe", source="Forecast",
                ))
            elif rain_3h >= 7 and pop >= 0.6 and "fc_hrain" not in seen:
                seen.add("fc_hrain")
                alerts.append(_alert(
                    id=f"fc_hrain_{item['dt']}", title="🌧 Rain Advisory",
                    icon="rainy-outline", icon_bg="#FFF3E0", icon_color="#FB8C00", border="#FB8C00",
                    time_str="Upcoming", when=dt_str, when_color="#FB8C00",
                    desc=f"Moderate to heavy rain ({rain_3h:.0f} mm) forecast for {location_name} around {dt_str}. Carry rain gear, expect traffic delays and slippery roads.",
                    location=location_name, severity="Moderate", source="Forecast",
                ))

            # Upcoming heat
            if temp_max >= 40 and "fc_heat" not in seen:
                seen.add("fc_heat")
                alerts.append(_alert(
                    id=f"fc_heat_{item['dt']}", title="🔥 Heat Wave Forecast",
                    icon="sunny-outline", icon_bg="#FFF3E0", icon_color="#FB8C00", border="#FB8C00",
                    time_str="Upcoming", when=dt_str, when_color="#FB8C00",
                    desc=f"Temperature expected to reach {temp_max:.0f}°C in {location_name} on {dt_str}. Stay hydrated, avoid outdoor activity during peak heat hours (11 AM–4 PM).",
                    location=location_name, severity="Moderate", source="Forecast",
                ))

            # Upcoming strong winds
            if wind_kmh >= 60 and "fc_wind" not in seen:
                seen.add("fc_wind")
                alerts.append(_alert(
                    id=f"fc_wind_{item['dt']}", title="💨 Strong Wind Forecast",
                    icon="flag-outline", icon_bg="#FFF3E0", icon_color="#FB8C00", border="#FB8C00",
                    time_str="Upcoming", when=dt_str, when_color="#FB8C00",
                    desc=f"Winds up to {wind_kmh:.0f} km/h expected in {location_name} around {dt_str}. Secure loose outdoor objects and be cautious while driving.",
                    location=location_name, severity="Moderate", source="Forecast",
                ))

        return alerts
    except Exception as e:
        print(f"[Alerts/Forecast] {e}")
        return []


# ── Air Quality alerts ────────────────────────────────────────────────────────

def _get_aqi_alerts(lat: float, lon: float, location_name: str) -> list:
    try:
        r = requests.get(
            f"{OWM_BASE}/air_pollution",
            params={"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY},
            timeout=6,
        )
        r.raise_for_status()
        aqi = r.json()["list"][0]["main"]["aqi"]
        if aqi < 3:
            return []
        colors = {3: "#FFC107", 4: "#FF9800", 5: "#F44336"}
        labels = {3: "Moderate 😷", 4: "Poor 🚫", 5: "Hazardous ☠️"}
        tips   = {
            3: "Sensitive groups (children, elderly, respiratory patients) should reduce outdoor activity.",
            4: "Everyone should reduce prolonged outdoor activity. Wear a mask outdoors.",
            5: "Hazardous air quality. Avoid all outdoor activity. Keep windows closed. Use air purifiers indoors.",
        }
        col = colors.get(aqi, "#FB8C00")
        return [_alert(
            id="aqi_now", title=f"😷 Air Quality: {labels.get(aqi, 'Poor')}",
            icon="leaf-outline", icon_bg="#E8F5E9", icon_color=col, border=col,
            time_str="Now", when="Today", when_color=col,
            desc=f"Air Quality Index is {labels.get(aqi, 'Poor')} in {location_name}. {tips.get(aqi, '')}",
            location=location_name, severity="Moderate" if aqi == 3 else "Severe", source="AQI",
        )]
    except Exception:
        return []


# ── Get city name from OWM ────────────────────────────────────────────────────

def _get_city(lat: float, lon: float) -> str:
    try:
        r = requests.get(
            f"{OWM_BASE}/weather",
            params={"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY},
            timeout=6,
        )
        d = r.json()
        city  = d.get("name", "")
        state = d.get("sys", {}).get("country", "")
        return f"{city}, {state}" if city else f"{lat:.2f}°N, {lon:.2f}°E"
    except Exception:
        return f"{lat:.2f}°N, {lon:.2f}°E"


# ── Groq personalisation ──────────────────────────────────────────────────────

def _personalise_alerts(alerts: list, city: str) -> list:
    """Use Groq to rewrite each alert description in a friendly, local style."""
    try:
        from config import GROQ_API_KEY
        if not GROQ_API_KEY or len(GROQ_API_KEY) < 10:
            return alerts

        import requests as _r
        personalised = []
        for a in alerts:
            prompt = (
                f"Rewrite this weather alert for {city} in 2-3 short, friendly sentences. "
                f"Be specific to the location, mention practical safety tips. "
                f"Keep it under 80 words. Alert: {a['title']} — {a['desc']}"
            )
            try:
                resp = _r.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 120, "temperature": 0.6,
                    },
                    timeout=8,
                )
                if resp.ok:
                    text = resp.json()["choices"][0]["message"]["content"].strip()
                    a = {**a, "desc": text}
            except Exception:
                pass
            personalised.append(a)
        return personalised
    except Exception:
        return alerts


# ── Main entry point ──────────────────────────────────────────────────────────

def get_alerts(lat: float, lon: float) -> dict:
    location_name = _get_city(lat, lon)

    # Try NOAA first (US only — returns empty outside US)
    noaa = _get_noaa_alerts(lat, lon)
    if noaa:
        return {"alerts": noaa, "source": "NOAA/NWS", "count": len(noaa)}

    # Global: combine current + forecast + AQI
    current  = _get_current_alerts(lat, lon, location_name)
    forecast = _get_forecast_alerts(lat, lon, location_name)
    aqi      = _get_aqi_alerts(lat, lon, location_name)

    # Deduplicate: prefer current over forecast for same type
    seen_types = set()
    final = []
    for a in current + aqi + forecast:
        key = a["id"].split("_")[0] + "_" + a["id"].split("_")[1] if "_" in a["id"] else a["id"]
        if key not in seen_types:
            seen_types.add(key)
            final.append(a)

    # Sort: Extreme → Severe → Moderate → Minor
    sev_order = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3}
    final.sort(key=lambda x: sev_order.get(x.get("severity", "Minor"), 3))

    # Personalise descriptions with Groq
    final = _personalise_alerts(final, location_name)

    print(f"[Alerts] {location_name}: {len(current)} current, {len(forecast)} forecast, {len(aqi)} AQI → {len(final)} total")
    return {"alerts": final, "source": "OpenWeatherMap", "count": len(final)}
