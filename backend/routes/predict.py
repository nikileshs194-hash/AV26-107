import os
import math
import requests
import joblib
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["predict"])

FEATURES = [
    "rainfall_1h", "rainfall_24h", "humidity", "temperature",
    "elevation", "soil_moisture", "drainage", "slope", "pressure",
    "sat_index",   # soil_moisture x rainfall_24h
    "rain_burst",  # rainfall_1h / (rainfall_24h + 1)
    "drain_eff",   # drainage x (slope + 0.5) / 10
]

_model_path = os.path.join(os.path.dirname(__file__), "..", "model.pkl")
try:
    _model = joblib.load(_model_path)
except Exception:
    _model = None


# ── Slope from real DEM elevation gradient ────────────────────────────────────

def _fetch_slope_and_elevation(lat: float, lon: float) -> tuple[float, float]:
    """
    Fetch elevation at 5 points (centre + N/S/E/W offset ~500m apart)
    and compute max terrain slope in degrees using real DEM data.
    """
    OFFSET = 0.005   # ~500m in degrees
    points = [
        (lat,          lon),           # centre
        (lat + OFFSET, lon),           # north
        (lat - OFFSET, lon),           # south
        (lat,          lon + OFFSET),  # east
        (lat,          lon - OFFSET),  # west
    ]
    lats = ",".join(str(p[0]) for p in points)
    lons = ",".join(str(p[1]) for p in points)
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/elevation",
            params={"latitude": lats, "longitude": lons},
            timeout=10,
        )
        elevs = r.json().get("elevation", [])
        if len(elevs) < 5:
            raise ValueError("incomplete elevation response")
    except Exception:
        return 3.0, 50.0   # fallback slope, elevation

    centre, north, south, east, west = [float(e) for e in elevs[:5]]

    # Horizontal distance for OFFSET degrees (~555m per 0.005 deg lat, varies for lon)
    dist_ns = OFFSET * 111_000          # metres
    dist_ew = OFFSET * 111_000 * math.cos(math.radians(lat))

    dz_ns = abs(north - south) / (2 * dist_ns)
    dz_ew = abs(east  - west)  / (2 * dist_ew)
    gradient = math.sqrt(dz_ns**2 + dz_ew**2)
    slope_deg = math.degrees(math.atan(gradient))

    return round(slope_deg, 3), round(centre, 1)


# ── Drainage from OpenStreetMap Overpass API ──────────────────────────────────

def _fetch_drainage_score(lat: float, lon: float, radius_m: int = 1000) -> float:
    """
    Query OSM Overpass for real drainage infrastructure within `radius_m` metres.
    Score 0-10: 0 = no drains (very poor), 10 = dense network (excellent).
    """
    query = f"""
    [out:json][timeout:12];
    (
      way["waterway"~"drain|ditch|canal|stream"](around:{radius_m},{lat},{lon});
      node["man_made"="manhole"](around:{radius_m},{lat},{lon});
      way["man_made"="pipeline"](around:{radius_m},{lat},{lon});
      node["waterway"="drain"](around:{radius_m},{lat},{lon});
    );
    out count;
    """
    try:
        r = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=15,
        )
        result = r.json()
        total = int(result.get("elements", [{}])[0].get("tags", {}).get("total", 0))
    except Exception:
        return 4.0   # neutral fallback

    # Normalise: 0 features -> score 1, 100+ features -> score 9
    score = min(9.0, 1.0 + (total / 100.0) * 8.0)
    return round(score, 2)


# ── Main feature fetcher ──────────────────────────────────────────────────────

def _fetch_features(lat: float, lon: float) -> dict:
    """
    12-hour ahead flood prediction.
    - Uses current soil moisture (ground saturation state right now)
    - Uses forecasted rainfall, humidity, temp, pressure at +12h
    - rainfall_24h = past 12h observed + next 12h forecast (full 24h window)
    """
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude":  lat,
            "longitude": lon,
            "current": [
                "soil_moisture_0_to_1cm",   # ground saturation now
            ],
            "hourly": [
                "precipitation",
                "relative_humidity_2m",
                "temperature_2m",
                "surface_pressure",
                "soil_moisture_0_to_1cm",
            ],
            "past_hours":     12,   # last 12h observed
            "forecast_hours": 13,   # next 12h forecast (+1 for index safety)
            "timezone":       "auto",
        },
        timeout=15,
    )
    resp.raise_for_status()
    d = resp.json()

    cur    = d.get("current", {})
    hourly = d.get("hourly", {})

    times  = hourly.get("time", [])
    precip = hourly.get("precipitation", [])
    humid  = hourly.get("relative_humidity_2m", [])
    temp   = hourly.get("temperature_2m", [])
    pres   = hourly.get("surface_pressure", [])
    soil   = hourly.get("soil_moisture_0_to_1cm", [])

    # Split past (first 12 entries) and forecast (remaining entries)
    past_rain     = [float(v or 0) for v in precip[:12]]
    forecast_rain = [float(v or 0) for v in precip[12:]]

    # Peak hourly rain in the 12h forecast window
    rainfall_1h  = max(forecast_rain) if forecast_rain else 0.0

    # Total rain: last 12h observed + next 12h forecast
    rainfall_24h = sum(past_rain) + sum(forecast_rain)

    # Conditions at 12h ahead (last forecast entry)
    idx_12h = min(len(times) - 1, 12)
    humidity    = float(humid[idx_12h] if idx_12h < len(humid) and humid[idx_12h] is not None else 75)
    temperature = float(temp[idx_12h]  if idx_12h < len(temp)  and temp[idx_12h]  is not None else 28)
    pressure    = float(pres[idx_12h]  if idx_12h < len(pres)  and pres[idx_12h]  is not None else 1005)

    # Current soil moisture — best proxy for ground saturation state
    soil_moist  = float(cur.get("soil_moisture_0_to_1cm") or
                        (soil[0] if soil and soil[0] is not None else 0.4))

    # Real slope + elevation from DEM gradient
    slope, elevation = _fetch_slope_and_elevation(lat, lon)

    # Real drainage density from OpenStreetMap
    drainage = _fetch_drainage_score(lat, lon)

    soil_moist_clipped = round(min(soil_moist, 1.0), 4)
    drainage_r         = round(drainage, 2)
    slope_r            = round(slope, 3)
    rainfall_1h_r      = round(rainfall_1h, 2)
    rainfall_24h_r     = round(rainfall_24h, 2)

    return {
        "rainfall_1h":   rainfall_1h_r,
        "rainfall_24h":  rainfall_24h_r,
        "humidity":      round(humidity,     1),
        "temperature":   round(temperature,  1),
        "elevation":     round(elevation,    1),
        "soil_moisture": soil_moist_clipped,
        "drainage":      drainage_r,
        "slope":         slope_r,
        "pressure":      round(pressure,     1),
        # engineered features — must match collect_and_train.py
        "sat_index":     round(soil_moist_clipped * rainfall_24h_r, 3),
        "rain_burst":    round(rainfall_1h_r / max(rainfall_24h_r, 1.0), 4),
        "drain_eff":     round(drainage_r * (slope_r + 0.5) / 10.0, 3),
    }


# ── Risk helpers ──────────────────────────────────────────────────────────────

def _risk_label(prob: float) -> str:
    if prob >= 0.75: return "High"
    if prob >= 0.45: return "Moderate"
    if prob >= 0.20: return "Low"
    return "Very Low"


def _advice(prob: float, f: dict) -> list[str]:
    tips = []
    if f["rainfall_1h"]  > 20:  tips.append("Heavy rainfall detected — avoid low-lying roads and underpasses.")
    if f["rainfall_24h"] > 80:  tips.append("High 24-hour accumulation — ground is saturated, water may not drain quickly.")
    if f["soil_moisture"] > 0.75: tips.append("Soil is near saturated — even light rain could cause surface runoff.")
    if f["elevation"]    < 30:  tips.append("You are in a low-elevation zone — particularly vulnerable to flooding.")
    if f["drainage"]     < 3:   tips.append("Sparse drainage infrastructure detected — water accumulation likely.")
    if f["slope"]        < 1:   tips.append("Very flat terrain — water drains slowly in this area.")
    if prob >= 0.75:  tips.append("Move valuables to higher floors. Keep emergency contacts ready.")
    elif prob >= 0.45: tips.append("Stay alert. Monitor local news and avoid flood-prone areas.")
    if not tips:      tips.append("No immediate flood threat. Continue to monitor weather updates.")
    return tips


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/predict")
def predict_flood(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
):
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded. Run collect_and_train.py first.")
    try:
        features = _fetch_features(lat, lon)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch weather data: {e}")

    df = pd.DataFrame([features])
    prob  = float(_model.predict_proba(df)[0][1])
    flood = bool(_model.predict(df)[0])

    return {
        "flood_predicted":   flood,
        "probability":       round(prob, 3),
        "risk_level":        _risk_label(prob),
        "forecast_window":   "12 hours",
        "features":          features,
        "advice":            _advice(prob, features),
    }
