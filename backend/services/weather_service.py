import requests
from datetime import datetime, timezone, timedelta
from config import OPENWEATHER_API_KEY, OWM_BASE, OPEN_METEO_BASE

# Open-Meteo air quality base (separate subdomain)
AIR_QUALITY_BASE = "https://air-quality-api.open-meteo.com/v1"


def degrees_to_compass(deg: float) -> str:
    directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                  'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    return directions[round(deg / 22.5) % 16]


# WMO weather code → (Ionicon name, condition label)
_WMO_MAP = {
    0:  ('sunny-outline',         'Clear Sky'),
    1:  ('partly-sunny-outline',  'Mainly Clear'),
    2:  ('partly-sunny-outline',  'Partly Cloudy'),
    3:  ('cloud-outline',         'Overcast'),
    45: ('cloudy-outline',        'Foggy'),
    48: ('cloudy-outline',        'Icy Fog'),
    51: ('rainy-outline',         'Light Drizzle'),
    53: ('rainy-outline',         'Drizzle'),
    55: ('rainy-outline',         'Heavy Drizzle'),
    61: ('rainy-outline',         'Light Rain'),
    63: ('rainy-outline',         'Rain'),
    65: ('rainy-outline',         'Heavy Rain'),
    71: ('snow-outline',          'Light Snow'),
    73: ('snow-outline',          'Snow'),
    75: ('snow-outline',          'Heavy Snow'),
    77: ('snow-outline',          'Snow Grains'),
    80: ('rainy-outline',         'Rain Showers'),
    81: ('rainy-outline',         'Rain Showers'),
    82: ('rainy-outline',         'Violent Showers'),
    85: ('snow-outline',          'Snow Showers'),
    86: ('snow-outline',          'Heavy Snow Showers'),
    95: ('thunderstorm-outline',  'Thunderstorm'),
    96: ('thunderstorm-outline',  'Thunderstorm w/ Hail'),
    99: ('thunderstorm-outline',  'Severe Thunderstorm'),
}
_WMO_NIGHT = {
    'sunny-outline':        'moon-outline',
    'partly-sunny-outline': 'cloudy-night-outline',
}


def wmo_icon(code: int, is_night: bool = False) -> str:
    icon, _ = _WMO_MAP.get(int(code), ('cloud-outline', 'Cloudy'))
    if is_night:
        icon = _WMO_NIGHT.get(icon, icon)
    return icon


def wmo_condition(code: int) -> str:
    _, label = _WMO_MAP.get(int(code), ('cloud-outline', 'Cloudy'))
    return label


def uv_label(uv: float) -> str:
    if uv <= 2:   return f"{uv:.0f} Low"
    if uv <= 5:   return f"{uv:.0f} Moderate"
    if uv <= 7:   return f"{uv:.0f} High"
    if uv <= 10:  return f"{uv:.0f} Very High"
    return f"{uv:.0f} Extreme"


def _fmt_hour(h: int) -> str:
    if h == 0:   return "12 AM"
    if h < 12:   return f"{h} AM"
    if h == 12:  return "12 PM"
    return f"{h - 12} PM"


def _naqi_from_pm25(pm25: float) -> tuple[int, str, str]:
    """Compute India NAQI index, label, and color from PM2.5 μg/m³."""
    breakpoints = [
        (0,   0,   30,  50,  "Good",               "#4CAF50"),
        (30,  50,  60,  100, "Satisfactory",        "#8BC34A"),
        (60,  100, 90,  200, "Moderately Polluted", "#FFC107"),
        (90,  200, 120, 300, "Poor",                "#FF9800"),
        (120, 300, 250, 400, "Very Poor",           "#F44336"),
        (250, 400, 380, 500, "Severe",              "#7B1FA2"),
    ]
    for c_lo, i_lo, c_hi, i_hi, label, color in breakpoints:
        if pm25 <= c_hi:
            naqi = round((i_hi - i_lo) / max(c_hi - c_lo, 1) * (pm25 - c_lo) + i_lo)
            return max(naqi, 0), label, color
    return 500, "Severe", "#7B1FA2"


# ─── Geocoding: city name → (lat, lon, city, country) — no API key needed ───

def geocode_city(city_name: str) -> dict | None:
    """
    Convert a city/place name to coordinates using Open-Meteo Geocoding API.
    Completely free — no API key required.
    Returns {"lat", "lon", "city", "country"} or None if not found.
    """
    try:
        url = (
            f"https://geocoding-api.open-meteo.com/v1/search"
            f"?name={requests.utils.quote(city_name)}&count=1&language=en&format=json"
        )
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        results = r.json().get("results", [])
        if results:
            res = results[0]
            return {
                "lat":     res["latitude"],
                "lon":     res["longitude"],
                "city":    res.get("name", city_name),
                "country": res.get("country", ""),
                "state":   res.get("admin1", ""),
            }
    except Exception:
        pass
    return None


# ─── City name from OWM (only field we need from it) ────────────────────────

def _get_city_info(lat: float, lon: float) -> dict:
    try:
        url = f"{OWM_BASE}/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric"
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        d = r.json()
        return {
            "city": d.get("name", ""),
            "country": d.get("sys", {}).get("country", ""),
            "tz_offset": d.get("timezone", 0),
            "rain_1h": d.get("rain", {}).get("1h", 0),
        }
    except Exception:
        return {"city": "", "country": "", "tz_offset": 0, "rain_1h": 0}


# ─── Current conditions: Open-Meteo (accurate, uncapped values) ─────────────

def get_open_meteo_current(lat: float, lon: float) -> dict:
    url = (
        f"{OPEN_METEO_BASE}/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
        f"weather_code,surface_pressure,wind_speed_10m,wind_direction_10m,"
        f"visibility,precipitation,uv_index"
        f"&daily=temperature_2m_max,temperature_2m_min"
        f"&wind_speed_unit=kmh"
        f"&timezone=auto"
        f"&forecast_days=1"
    )
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()
    cur = data.get("current", {})
    daily = data.get("daily", {})

    wmo = int(cur.get("weather_code", 3))
    local_hour = 0
    try:
        local_hour = datetime.fromisoformat(cur.get("time", "2000-01-01T00:00")).hour
    except Exception:
        pass
    is_night = local_hour < 6 or local_hour >= 20

    vis_m = cur.get("visibility", 10000)
    vis_km = round(vis_m / 1000, 1) if vis_m else 10.0

    temp_min = round(daily.get("temperature_2m_min", [None])[0] or cur.get("temperature_2m", 0))
    temp_max = round(daily.get("temperature_2m_max", [None])[0] or cur.get("temperature_2m", 0))

    return {
        "temp": round(cur.get("temperature_2m", 0)),
        "feels_like": round(cur.get("apparent_temperature", 0)),
        "temp_min": temp_min,
        "temp_max": temp_max,
        "humidity": int(cur.get("relative_humidity_2m", 0)),
        # surface_pressure is actual station pressure (elevation-corrected) — NOT sea-level
        "pressure": round(cur.get("surface_pressure", 1013)),
        "visibility": vis_km,
        "wind_speed": round(cur.get("wind_speed_10m", 0), 1),
        "wind_dir": degrees_to_compass(cur.get("wind_direction_10m", 0)),
        "uv_index": round(cur.get("uv_index", 0), 1),
        "uv_label": uv_label(cur.get("uv_index", 0)),
        "condition": wmo_condition(wmo),
        "description": wmo_condition(wmo),
        "icon": wmo_icon(wmo, is_night),
        "precipitation": round(cur.get("precipitation", 0), 1),
    }


# ─── Air quality: Open-Meteo (India NAQI from PM2.5) ────────────────────────

def get_air_quality(lat: float, lon: float) -> dict:
    try:
        url = (
            f"{AIR_QUALITY_BASE}/air-quality"
            f"?latitude={lat}&longitude={lon}"
            f"&current=pm2_5,pm10,us_aqi,european_aqi"
            f"&timezone=auto"
        )
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        cur = r.json().get("current", {})
        pm25 = cur.get("pm2_5", 0) or 0
        pm10 = cur.get("pm10", 0) or 0
        naqi, label, color = _naqi_from_pm25(pm25)
        return {
            "aqi": naqi,
            "label": label,
            "color": color,
            "pm2_5": round(pm25, 1),
            "pm10": round(pm10, 1),
            "us_aqi": cur.get("us_aqi", 0),
        }
    except Exception:
        # Fallback to OWM AQI if Open-Meteo air quality fails
        try:
            url = f"{OWM_BASE}/air_pollution?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}"
            r = requests.get(url, timeout=6)
            r.raise_for_status()
            aqi = r.json()["list"][0]["main"]["aqi"]
            labels = {1: "Good", 2: "Fair", 3: "Moderate", 4: "Poor", 5: "Very Poor"}
            colors = {1: "#4CAF50", 2: "#8BC34A", 3: "#FFC107", 4: "#FF9800", 5: "#F44336"}
            return {"aqi": aqi * 50, "label": labels.get(aqi, "Unknown"),
                    "color": colors.get(aqi, "#FFC107"), "pm2_5": 0, "pm10": 0}
        except Exception:
            return {"aqi": 50, "label": "Good", "color": "#4CAF50", "pm2_5": 0, "pm10": 0}


# ─── Hourly + Daily forecast: Open-Meteo ────────────────────────────────────

def get_open_meteo_forecast(lat: float, lon: float, tz_offset: int = 0) -> dict:
    local_tz = timezone(timedelta(seconds=tz_offset))
    now_local = datetime.now(tz=local_tz)

    url = (
        f"{OPEN_METEO_BASE}/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,apparent_temperature,precipitation_probability,"
        f"weather_code,wind_speed_10m"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,"
        f"precipitation_probability_mean,precipitation_probability_max"
        f"&wind_speed_unit=kmh"
        f"&timezone=auto"
        f"&forecast_days=7"
    )
    r = requests.get(url, timeout=12)
    r.raise_for_status()
    data = r.json()

    # ── Hourly ──────────────────────────────────────────────────────────────
    hrly = data.get("hourly", {})
    times = hrly.get("time", [])
    temps = hrly.get("temperature_2m", [])
    feels = hrly.get("apparent_temperature", [])
    probs = hrly.get("precipitation_probability", [])
    codes = hrly.get("weather_code", [])

    now_ts = now_local.timestamp()
    hourly_out = []
    for i, t_str in enumerate(times):
        try:
            dt = datetime.fromisoformat(t_str).replace(tzinfo=local_tz)
        except Exception:
            continue
        if dt.timestamp() < now_ts - 1800:
            continue
        wmo = int(codes[i]) if i < len(codes) else 0
        rain_prob = int(probs[i]) if i < len(probs) else 0
        is_night = dt.hour < 6 or dt.hour >= 20
        hourly_out.append({
            "time": _fmt_hour(dt.hour),
            "timestamp": int(dt.timestamp()),
            "temp": round(temps[i]) if i < len(temps) else 0,
            "feels_like": round(feels[i]) if i < len(feels) else 0,
            "icon": wmo_icon(wmo, is_night),
            "condition": wmo_condition(wmo),
            "rain_prob": rain_prob,
            "rain_mm": 0,
            "humidity": 0,
        })
        if len(hourly_out) >= 8:
            break

    # ── Daily ────────────────────────────────────────────────────────────────
    drly = data.get("daily", {})
    d_dates  = drly.get("time", [])
    d_codes  = drly.get("weather_code", [])
    d_maxT   = drly.get("temperature_2m_max", [])
    d_minT   = drly.get("temperature_2m_min", [])
    d_mean_p = drly.get("precipitation_probability_mean", [])

    today_str = now_local.strftime("%Y-%m-%d")
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    daily_out = []
    for i, d_str in enumerate(d_dates[:7]):
        try:
            dt = datetime.strptime(d_str, "%Y-%m-%d")
        except Exception:
            continue
        label = "Today" if d_str == today_str else day_names[dt.weekday()]
        wmo = int(d_codes[i]) if i < len(d_codes) else 0
        mean_prob = int(d_mean_p[i]) if i < len(d_mean_p) else 0
        daily_out.append({
            "date": d_str, "day": label,
            "temp_min": round(d_minT[i]) if i < len(d_minT) else 0,
            "temp_max": round(d_maxT[i]) if i < len(d_maxT) else 0,
            "icon": wmo_icon(wmo, is_night=False),
            "condition": wmo_condition(wmo),
            "rain_prob": mean_prob,
            "rain_mm": 0,
        })
    return {"hourly": hourly_out, "daily": daily_out}


# ─── Full weather response ───────────────────────────────────────────────────

def get_full_weather(lat: float, lon: float) -> dict:
    city_info = _get_city_info(lat, lon)
    tz_offset = city_info.get("tz_offset", 0)

    current = get_open_meteo_current(lat, lon)
    air = get_air_quality(lat, lon)
    forecast = get_open_meteo_forecast(lat, lon, tz_offset=tz_offset)

    current.update({
        "city": city_info["city"],
        "country": city_info["country"],
        "lat": lat, "lon": lon,
        "rain_1h": city_info["rain_1h"],
        "air_quality": air,
        "tz_offset": tz_offset,
    })

    return {
        "current": current,
        "hourly": forecast["hourly"],
        "daily": forecast["daily"],
    }
