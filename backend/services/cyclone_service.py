"""
Cyclone prediction service — real-world data, ML model + physics fallback.

Data sources:
  Open-Meteo Forecast API  — wind, gusts, pressure, CAPE (live + 6-h history)
  GDACS RSS Feed           — active tropical cyclones (TC) worldwide
  Indian coastline points  — to compute coastal proximity multiplier

Primary model: VotingClassifier ML model trained on 35+ documented Indian
  Ocean cyclone landfalls (2007-2024) using ERA5 historical features.
Fallback: IMD (India Meteorological Department) threshold-based physics model.
  component      weight   signal
  wind gusts     0.40     IMD cyclone scale (31 → 222+ km/h)
  pressure       0.30     low pressure eye (<980 hPa = severe)
  pressure drop  0.20     rate of deepening (hPa / 6 h)
  CAPE           0.10     convective instability (J / kg)
  × season × coast multipliers applied after weighted sum
  GDACS floor:  if active TC within 1500 km → prob ≥ 0.60
"""

import math
import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# ── ML model feature list (must match train_cyclone.py CYCLONE_FEATURES) ──────
CYCLONE_FEATURES = [
    "wind_gusts_kmh",
    "surface_pressure_hpa",
    "pressure_drop_6h",
    "cape_jkg",
    "precipitation_mm",
    "humidity",
    "coastal_proximity_km",
    "season_factor",
    "lat_abs",
]

# ── Load ML model at import time ──────────────────────────────────────────────
_CYCLONE_MODEL = None
try:
    import joblib
    _MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "cyclone_model.pkl")
    if os.path.exists(_MODEL_PATH):
        _CYCLONE_MODEL = joblib.load(_MODEL_PATH)
        print(f"[CycloneService] ML model loaded from {_MODEL_PATH}")
    else:
        print("[CycloneService] cyclone_model.pkl not found — using physics model only")
except Exception as _e:
    print(f"[CycloneService] ML model load failed: {_e} — using physics fallback")

_OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
_GDACS_RSS  = "https://www.gdacs.org/xml/rss.xml"
_GDACS_NS   = "http://www.gdacs.org/xml/1.0"

# ── Indian coastline reference points (lat, lon) ──────────────────────────────
# ~25 points covering the full perimeter: Gujarat → Karnataka → Kerala →
# Tamil Nadu → AP → Odisha → West Bengal
_COAST_PTS = [
    (23.2, 68.9), (21.6, 69.6), (20.9, 70.4), (19.2, 72.8),
    (15.5, 73.8), (14.8, 74.1), (12.9, 74.8), (11.2, 75.8),
    (10.0, 76.2), (8.5,  77.0), (8.1,  77.5),
    (9.3,  79.3), (10.8, 79.8), (11.9, 79.8), (13.1, 80.3),
    (14.8, 80.1), (15.9, 80.6), (16.9, 82.2), (17.7, 83.3),
    (19.8, 85.8), (20.5, 86.7), (21.4, 87.2), (21.9, 88.2),
    (21.6, 88.9),
]


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _coast_distance_km(lat: float, lon: float) -> float:
    """Straight-line distance to the nearest point on the Indian coastline."""
    return min(_haversine_km(lat, lon, cp[0], cp[1]) for cp in _COAST_PTS)


def _coast_factor(dist_km: float) -> float:
    """
    Multiplier that boosts risk for coastal locations and dampens it inland.
    Cyclones rapidly weaken once they cross the coast.
    """
    if dist_km < 200:   return 1.40
    if dist_km < 500:   return 1.20
    if dist_km < 1000:  return 1.00
    return 0.30    # deep inland — cyclone will have already dissipated


def _season_factor(month: int) -> float:
    """
    IMD seasonal multiplier.
    Bay of Bengal: peak Apr-Jun & Oct-Dec.  Arabian Sea: peak May-Jun & Oct-Nov.
    """
    factors = {
        1: 0.55, 2: 0.55, 3: 0.65,
        4: 0.90, 5: 1.30, 6: 0.95,
        7: 0.45, 8: 0.45, 9: 0.60,
        10: 1.20, 11: 1.30, 12: 0.90,
    }
    return factors.get(month, 0.80)


# ── IMD scale helpers ─────────────────────────────────────────────────────────

def _imd_category(wind_kmh: float) -> str:
    if wind_kmh >= 222: return "Super Cyclone"
    if wind_kmh >= 168: return "Extremely Severe Cyclonic Storm"
    if wind_kmh >= 118: return "Very Severe Cyclonic Storm"
    if wind_kmh >= 89:  return "Severe Cyclonic Storm"
    if wind_kmh >= 63:  return "Cyclonic Storm"
    if wind_kmh >= 52:  return "Deep Depression"
    if wind_kmh >= 31:  return "Depression"
    return "No Cyclonic Activity"


def _risk_label(prob: float) -> str:
    if prob >= 0.80: return "Extreme"
    if prob >= 0.60: return "High"
    if prob >= 0.40: return "Moderate"
    if prob >= 0.20: return "Low"
    return "Very Low"


# ── GDACS active cyclone check ────────────────────────────────────────────────

def _check_gdacs(lat: float, lon: float) -> dict:
    """
    Fetch GDACS RSS and look for active Tropical Cyclone (TC) events
    within 1 500 km of the user.  Returns a dict with keys:
      active (bool), name (str), distance_km (float), alert_level (str)
    """
    result = {"active": False, "name": "", "distance_km": 9999.0, "alert_level": ""}
    try:
        r = requests.get(_GDACS_RSS, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.text)

        for item in root.findall(".//item"):
            etype = item.find(f"{{{_GDACS_NS}}}eventtype")
            if etype is None or (etype.text or "").strip().upper() != "TC":
                continue

            lat_el  = item.find(f"{{{_GDACS_NS}}}lat")
            lon_el  = item.find(f"{{{_GDACS_NS}}}long")
            if lat_el is None or lon_el is None:
                continue

            try:
                tc_lat = float(lat_el.text)
                tc_lon = float(lon_el.text)
            except (TypeError, ValueError):
                continue

            dist = _haversine_km(lat, lon, tc_lat, tc_lon)
            if dist < result["distance_km"]:
                title      = item.find("title")
                alert_el   = item.find(f"{{{_GDACS_NS}}}alertlevel")
                result.update({
                    "distance_km": round(dist, 1),
                    "name":        title.text if title is not None else "Tropical Cyclone",
                    "alert_level": alert_el.text if alert_el is not None else "Unknown",
                })

        if result["distance_km"] <= 1500:
            result["active"] = True

    except Exception as e:
        print(f"[Cyclone] GDACS fetch error: {e}")

    return result


# ── Feature extraction from Open-Meteo ───────────────────────────────────────

def fetch_cyclone_features(lat: float, lon: float) -> dict:
    """
    Fetch all cyclone-relevant atmospheric features for the given location.
    Uses Open-Meteo (current + 6-h past hourly) and GDACS.
    """
    resp = requests.get(
        _OPEN_METEO,
        params={
            "latitude":       lat,
            "longitude":      lon,
            "current": [
                "wind_speed_10m",
                "wind_gusts_10m",
                "surface_pressure",
                "cape",
                "precipitation",
                "relative_humidity_2m",
                "weather_code",
            ],
            "hourly": [
                "surface_pressure",
                "wind_speed_10m",
                "wind_gusts_10m",
            ],
            "past_hours":     6,
            "forecast_hours": 1,
            "timezone":       "auto",
            "wind_speed_unit": "kmh",
        },
        timeout=15,
    )
    resp.raise_for_status()
    d = resp.json()

    cur    = d.get("current", {})
    hourly = d.get("hourly", {})

    wind_speed  = float(cur.get("wind_speed_10m",      0)    or 0)
    wind_gusts  = float(cur.get("wind_gusts_10m",      0)    or 0)
    pressure    = float(cur.get("surface_pressure",    1013) or 1013)
    cape        = float(cur.get("cape",                0)    or 0)
    precip      = float(cur.get("precipitation",       0)    or 0)
    humidity    = float(cur.get("relative_humidity_2m", 70)  or 70)

    # Pressure trend: compare current pressure vs 6 hours ago
    h_pressure  = hourly.get("surface_pressure", [])
    pressure_6h_ago = float(h_pressure[0]) if h_pressure and h_pressure[0] is not None else pressure
    # positive value means pressure has been dropping (cyclone deepening)
    pressure_drop_6h = round(pressure_6h_ago - pressure, 2)

    coast_km = round(_coast_distance_km(lat, lon), 1)
    month    = datetime.now(timezone.utc).month
    s_factor = _season_factor(month)

    gdacs    = _check_gdacs(lat, lon)

    return {
        "wind_speed_kmh":        round(wind_speed,  1),
        "wind_gusts_kmh":        round(wind_gusts,  1),
        "surface_pressure_hpa":  round(pressure,    1),
        "pressure_6h_ago_hpa":   round(pressure_6h_ago, 1),
        "pressure_drop_6h":      pressure_drop_6h,
        "cape_jkg":              round(cape,         1),
        "precipitation_mm":      round(precip,       2),
        "humidity":              round(humidity,     1),
        "coastal_proximity_km":  coast_km,
        "season_factor":         s_factor,
        "lat_abs":               round(abs(lat),     2),
        "gdacs_active":          gdacs["active"],
        "gdacs_name":            gdacs["name"],
        "gdacs_distance_km":     gdacs["distance_km"],
        "gdacs_alert_level":     gdacs["alert_level"],
    }


# ── Probability computation ───────────────────────────────────────────────────

def compute_probability(f: dict) -> float:
    """
    Hybrid probability: ML model (if available) blended with IMD physics score.
    ML gets 70% weight when available; physics-only otherwise.
    GDACS floor applied: if active TC within 1500 km → prob ≥ 0.60.
    """
    # ── ML model probability ──────────────────────────────────────────────────
    ml_prob = None
    if _CYCLONE_MODEL is not None:
        try:
            import pandas as pd
            row = {
                "wind_gusts_kmh":        f["wind_gusts_kmh"],
                "surface_pressure_hpa":  f["surface_pressure_hpa"],
                "pressure_drop_6h":      f["pressure_drop_6h"],
                "cape_jkg":              f["cape_jkg"],
                "precipitation_mm":      f.get("precipitation_mm", f.get("precipitation_mm", 0.0)),
                "humidity":              f.get("humidity", 70.0),
                "coastal_proximity_km":  f["coastal_proximity_km"],
                "season_factor":         f["season_factor"],
                "lat_abs":               abs(f.get("lat_abs", 0.0)),
            }
            df = pd.DataFrame([row])
            ml_prob = float(_CYCLONE_MODEL.predict_proba(df)[0][1])
        except Exception as _e:
            print(f"[CycloneService] ML inference failed: {_e}")

    # ── Physics-based scoring (IMD thresholds) ────────────────────────────────
    wind_score     = min(f["wind_gusts_kmh"] / 222.0, 1.0)
    pressure_score = max(0.0, min((1013.0 - f["surface_pressure_hpa"]) / 73.0, 1.0))
    drop           = max(f["pressure_drop_6h"], 0.0)
    drop_score     = min(drop / 10.0, 1.0)
    cape_score     = min(f["cape_jkg"] / 3000.0, 1.0)

    physics_prob = (
        wind_score     * 0.40 +
        pressure_score * 0.30 +
        drop_score     * 0.20 +
        cape_score     * 0.10
    )
    physics_prob *= f["season_factor"]
    physics_prob *= _coast_factor(f["coastal_proximity_km"])

    # ── Blend ─────────────────────────────────────────────────────────────────
    if ml_prob is not None:
        base = ml_prob * 0.70 + physics_prob * 0.30
    else:
        base = physics_prob

    # GDACS floor: confirmed active cyclone nearby → at least High
    if f["gdacs_active"]:
        base = max(base, 0.60)

    return round(min(base, 1.0), 3)


# ── Advice ────────────────────────────────────────────────────────────────────

def cyclone_advice(prob: float, f: dict) -> list[str]:
    tips = []
    if f["gdacs_active"]:
        tips.append(
            f"⚠ Active cyclone '{f['gdacs_name']}' is {f['gdacs_distance_km']:.0f} km away "
            f"(GDACS alert: {f['gdacs_alert_level']}). Follow official IMD bulletins."
        )
    if f["wind_gusts_kmh"] >= 89:
        tips.append("Severe wind gusts detected. Secure loose objects, avoid travel.")
    elif f["wind_gusts_kmh"] >= 63:
        tips.append("Cyclonic storm-level gusts. Stay indoors and monitor updates.")
    if f["surface_pressure_hpa"] < 980:
        tips.append("Very low atmospheric pressure — eye of a developing cyclone nearby.")
    elif f["surface_pressure_hpa"] < 995:
        tips.append("Below-normal pressure detected — monitor for rapid deterioration.")
    if f["pressure_drop_6h"] >= 4:
        tips.append(f"Pressure dropped {f['pressure_drop_6h']} hPa in 6 hours — rapid cyclone deepening.")
    if f["coastal_proximity_km"] < 300:
        tips.append("You are in a coastal zone — highest vulnerability to storm surge and cyclonic landfall.")
    if prob >= 0.80:
        tips.append("Extreme cyclone risk. Follow evacuation orders immediately.")
    elif prob >= 0.60:
        tips.append("High cyclone risk. Stay prepared: emergency kit, shelter plan, charged phone.")
    elif prob >= 0.40:
        tips.append("Moderate cyclone conditions. Stay alert and keep essentials ready.")
    if not tips:
        tips.append("No immediate cyclone threat. Continue monitoring weather updates.")
    return tips


# ── Main prediction function ──────────────────────────────────────────────────

def predict_cyclone(lat: float, lon: float) -> dict:
    """
    Full cyclone prediction pipeline.
    Returns a dict ready to serve from the API endpoint or the scheduler.
    """
    features = fetch_cyclone_features(lat, lon)
    prob     = compute_probability(features)
    risk     = _risk_label(prob)
    category = _imd_category(features["wind_gusts_kmh"])

    sources = ["Open-Meteo", "GDACS"]
    if _CYCLONE_MODEL is not None:
        sources.insert(0, "ML Model (ERA5-trained)")

    return {
        "cyclone_risk":       risk,
        "probability":        prob,
        "category":           category,
        "cyclone_likely":     prob >= 0.60,
        "features":           features,
        "advice":             cyclone_advice(prob, features),
        "data_sources":       sources,
        "forecast_window":    "Current conditions + 6-hour trend",
        "ml_model_active":    _CYCLONE_MODEL is not None,
    }
