"""
Earthquake prediction service — live USGS data + ML model (v2, 12 features).

Data source:
  USGS Earthquake Catalog API  (free, no API key)
  https://earthquake.usgs.gov/fdsnws/event/1/

ML model:
  VotingClassifier (XGBoost + GBM + RandomForest)
  Trained on 14,775 samples, 20-year USGS catalog (2005-2024)
  Features: b-value (Aki 1965), inter-event CV, quake acceleration,
            shallow depth fraction + 8 classical seismological features
  CV ROC-AUC: 90.7% | Temporal AUC (2023-24): 88.0%

Predicts: probability of M>=4.5 within 100 km in the next 7 days.
"""

import math
import os
import time
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone

# ── Feature list (must match train_earthquake.py EARTHQUAKE_FEATURES) ──────────
EARTHQUAKE_FEATURES = [
    "recent_quakes_7d",
    "recent_quakes_30d",
    "max_mag_7d",
    "max_mag_30d",
    "energy_index_30d",
    "b_value",
    "cv_interevent",
    "quake_acceleration",
    "depth_avg_30d",
    "depth_shallow_frac",
    "dist_to_fault_km",
    "seismic_zone",
]

MC = 2.0  # completeness magnitude for b-value

# ── Load ML model at import time ────────────────────────────────────────────────
_EQ_MODEL = None
try:
    import joblib
    _MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "earthquake_model.pkl")
    if os.path.exists(_MODEL_PATH):
        _EQ_MODEL = joblib.load(_MODEL_PATH)
        print(f"[EarthquakeService] ML model loaded from {_MODEL_PATH}")
    else:
        print("[EarthquakeService] earthquake_model.pkl not found")
except Exception as _e:
    print(f"[EarthquakeService] ML model load failed: {_e}")

# ── Fault reference points ──────────────────────────────────────────────────────
_FAULT_POINTS = [
    (27.5,72.5),(28.0,74.0),(28.5,76.0),(29.0,78.0),(29.5,80.0),
    (29.0,82.0),(28.5,84.0),(27.5,86.0),(27.0,88.0),(26.5,89.5),
    (26.0,91.0),(25.5,92.5),(25.0,94.0),(26.0,95.5),(27.0,97.0),
    (13.5,93.8),(12.0,93.2),(10.0,92.5),(8.0,92.0),
    (6.5,93.5),(5.0,94.5),(4.5,95.5),
    (24.5,93.5),(22.5,93.5),(20.5,93.0),(18.5,94.0),(17.0,95.0),
    (23.0,96.5),(21.0,96.0),(19.0,96.5),(17.5,96.5),
    (23.8,68.5),(23.5,70.0),(23.5,71.5),(22.8,72.5),
    (22.0,73.5),(22.5,75.5),(23.0,77.5),(23.5,79.5),(23.8,81.5),(24.0,83.5),
    (17.4,73.8),(17.0,74.0),(16.8,74.2),
    (28.7,77.2),(28.5,78.5),(29.0,79.5),
    (20.5,83.5),(21.0,85.5),(21.5,87.0),
]
_FAULT_LATS = np.array([p[0] for p in _FAULT_POINTS])
_FAULT_LONS = np.array([p[1] for p in _FAULT_POINTS])

_ZONE_B_DEFAULT = {5: 0.90, 4: 0.87, 3: 0.82, 2: 0.78}


# ── Geometry helpers ────────────────────────────────────────────────────────────

def _haversine_vec(lat, lon, lats, lons):
    R = 6371.0
    dlat = np.radians(lats - lat)
    dlon = np.radians(lons - lon)
    a = (np.sin(dlat / 2) ** 2
         + np.cos(np.radians(lat)) * np.cos(np.radians(lats))
         * np.sin(dlon / 2) ** 2)
    return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _dist_to_fault(lat: float, lon: float) -> float:
    return round(float(_haversine_vec(lat, lon, _FAULT_LATS, _FAULT_LONS).min()), 1)


def _seismic_zone(lat: float, lon: float) -> int:
    ZONE_V = [
        (22.0,29.5,89.5,97.5),(6.0,14.5,92.0,94.5),(33.5,36.5,73.5,77.5),
        (22.5,24.5,68.0,71.5),(32.0,33.5,75.5,78.5),
    ]
    ZONE_IV = [
        (26.5,28.5,87.5,90.5),(29.5,31.5,78.0,81.0),(32.0,35.5,74.0,77.5),
        (28.0,29.5,76.5,78.5),(27.5,30.0,80.0,84.0),(26.5,27.5,83.0,88.0),
        (22.0,24.0,71.5,74.0),(17.0,18.5,73.5,75.0),(30.5,32.5,75.0,78.0),
    ]
    for a, b, c, d in ZONE_V:
        if a <= lat <= b and c <= lon <= d: return 5
    for a, b, c, d in ZONE_IV:
        if a <= lat <= b and c <= lon <= d: return 4
    if 8.0 <= lat <= 28.0 and 70.0 <= lon <= 90.0: return 3
    return 2


def _zone_label(z: int) -> str:
    return {5: "V - Very High", 4: "IV - High", 3: "III - Moderate", 2: "II - Low"}.get(z, "Unknown")


def _risk_label(prob: float) -> str:
    if prob >= 0.70: return "High"
    if prob >= 0.45: return "Moderate"
    if prob >= 0.20: return "Low"
    return "Very Low"


# ── Scientific feature computation ─────────────────────────────────────────────

def _compute_b_value(mags: np.ndarray, mc: float = MC) -> float:
    """Aki (1965) MLE b-value. Low b = high tectonic stress."""
    mags = mags[mags >= mc]
    if len(mags) < 20:
        return 1.0
    mean_m = float(mags.mean())
    if mean_m <= mc:
        return 1.0
    b = math.log10(math.e) / (mean_m - mc)
    return round(float(np.clip(b, 0.5, 2.0)), 3)


def _compute_cv_interevent(times_series: pd.Series) -> float:
    """CV of inter-event times. >1=clustered, ~1=Poisson, <1=quiescent."""
    if len(times_series) < 3:
        return 1.0
    times_sorted = times_series.sort_values()
    diffs = times_sorted.diff().dropna().dt.total_seconds() / 3600.0
    diffs = diffs[diffs > 0]
    if len(diffs) < 2:
        return 1.0
    cv = float(diffs.std() / (diffs.mean() + 1e-9))
    return round(float(np.clip(cv, 0.0, 10.0)), 3)


# ── Live USGS feature fetch ─────────────────────────────────────────────────────

def fetch_earthquake_features(lat: float, lon: float) -> dict:
    """
    Fetch last 90 days of USGS data (M>=2.0) and compute all 12 ML features.
    Retries once before falling back to zone-based defaults.
    """
    now       = datetime.now(tz=timezone.utc)
    start_90  = (now - timedelta(days=91)).strftime("%Y-%m-%d")
    end_date  = now.strftime("%Y-%m-%d")

    bbox_pad = 2.5
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    params = {
        "format":       "geojson",
        "starttime":    start_90,
        "endtime":      end_date,
        "minlatitude":  lat - bbox_pad,
        "maxlatitude":  lat + bbox_pad,
        "minlongitude": lon - bbox_pad,
        "maxlongitude": lon + bbox_pad,
        "minmagnitude": 2.0,
        "orderby":      "time",
        "limit":        2000,
    }

    features_list = []
    last_err = None
    for attempt in range(2):
        try:
            r = requests.get(url, params=params, timeout=18)
            r.raise_for_status()
            features_list = r.json().get("features", [])
            break
        except Exception as e:
            last_err = e
            if attempt == 0:
                time.sleep(1)
            else:
                print(f"[EarthquakeService] USGS fetch failed: {e}. Using fallback.")
                return _fallback_features(lat, lon)

    if not features_list:
        return _fallback_features(lat, lon)

    rows = []
    for feat in features_list:
        props  = feat.get("properties", {})
        coords = feat.get("geometry", {}).get("coordinates", [None, None, None])
        ts_ms  = props.get("time")
        if ts_ms is None or coords[0] is None:
            continue
        rows.append({
            "time":  datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
            "lat":   float(coords[1]),
            "lon":   float(coords[0]),
            "depth": float(coords[2]) if coords[2] is not None else 10.0,
            "mag":   float(props.get("mag") or 0.0),
        })

    if not rows:
        return _fallback_features(lat, lon)

    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], utc=True)

    dists_all = _haversine_vec(lat, lon, df["lat"].values, df["lon"].values)

    # 150km / 30d window for standard features
    nearby_30 = df[(dists_all <= 150.0) & (df["time"] >= now - timedelta(days=30))].copy()
    nearby_7  = nearby_30[nearby_30["time"] >= now - timedelta(days=7)]

    # 200km / 90d window for b-value + CV
    nearby_90 = df[(dists_all <= 200.0)].copy()

    n_30d = len(nearby_30)
    n_7d  = len(nearby_7)

    max_mag_30d = float(nearby_30["mag"].max())  if n_30d > 0 else 0.0
    max_mag_7d  = float(nearby_7["mag"].max())   if n_7d  > 0 else 0.0
    energy_30d  = float(np.sum(10 ** (0.75 * nearby_30["mag"].values))) if n_30d > 0 else 0.0

    depths = nearby_30["depth"].dropna()
    depth_avg          = float(depths.mean()) if len(depths) > 0 else 35.0
    depth_shallow_frac = float((depths < 30.0).sum() / len(depths)) if len(depths) > 0 else 0.5

    rate_7d  = n_7d  / 7.0
    rate_30d = n_30d / 30.0
    quake_acceleration = float(np.clip(rate_7d / (rate_30d + 1e-6), 0.0, 20.0))

    zone = _seismic_zone(lat, lon)
    b_val = _compute_b_value(nearby_90["mag"].values) if len(nearby_90) >= 20 \
            else _ZONE_B_DEFAULT.get(zone, 0.85)
    cv_ie = _compute_cv_interevent(nearby_90["time"]) if len(nearby_90) >= 3 else 1.0

    return {
        "recent_quakes_7d":    n_7d,
        "recent_quakes_30d":   n_30d,
        "max_mag_7d":          round(max_mag_7d,   2),
        "max_mag_30d":         round(max_mag_30d,  2),
        "energy_index_30d":    round(energy_30d,   2),
        "b_value":             round(b_val,         3),
        "cv_interevent":       round(cv_ie,         3),
        "quake_acceleration":  round(quake_acceleration, 3),
        "depth_avg_30d":       round(depth_avg,     1),
        "depth_shallow_frac":  round(depth_shallow_frac, 3),
        "dist_to_fault_km":    _dist_to_fault(lat, lon),
        "seismic_zone":        zone,
        # display-only extras (not ML features)
        "seismic_zone_label":  _zone_label(zone),
        "total_events_bbox":   len(df),
    }


def _fallback_features(lat: float, lon: float) -> dict:
    zone = _seismic_zone(lat, lon)
    return {
        "recent_quakes_7d":    0,
        "recent_quakes_30d":   0,
        "max_mag_7d":          0.0,
        "max_mag_30d":         0.0,
        "energy_index_30d":    0.0,
        "b_value":             _ZONE_B_DEFAULT.get(zone, 0.85),
        "cv_interevent":       1.0,
        "quake_acceleration":  1.0,
        "depth_avg_30d":       35.0,
        "depth_shallow_frac":  0.5,
        "dist_to_fault_km":    _dist_to_fault(lat, lon),
        "seismic_zone":        zone,
        "seismic_zone_label":  _zone_label(zone),
        "total_events_bbox":   0,
    }


# ── Advice generator ────────────────────────────────────────────────────────────

def _earthquake_advice(prob: float, f: dict) -> list[str]:
    tips = []
    if f["recent_quakes_7d"] >= 5:
        tips.append(f"Elevated seismic activity: {f['recent_quakes_7d']} earthquakes in the past 7 days nearby.")
    if f["max_mag_7d"] >= 4.0:
        tips.append(f"Recent M{f['max_mag_7d']:.1f} earthquake detected nearby. Aftershocks possible.")
    if f["b_value"] < 0.75:
        tips.append(f"Low b-value ({f['b_value']:.2f}) detected — high tectonic stress, elevated large-quake probability.")
    if f["cv_interevent"] > 2.0:
        tips.append(f"Seismic clustering active (CV={f['cv_interevent']:.1f}) — aftershock sequence may be ongoing.")
    if f["quake_acceleration"] > 2.0:
        tips.append(f"Seismic rate accelerating ({f['quake_acceleration']:.1f}x) — possible foreshock swarm.")
    if f["dist_to_fault_km"] < 30:
        tips.append(f"Location is {f['dist_to_fault_km']:.0f} km from a major fault — high structural vulnerability.")
    if f["depth_shallow_frac"] > 0.7:
        tips.append(f"Most nearby quakes are shallow ({f['depth_shallow_frac']*100:.0f}% at depth < 30 km) — high surface impact risk.")
    if f["seismic_zone"] >= 4:
        tips.append(f"BIS Seismic Zone {f['seismic_zone_label']} — ensure buildings are earthquake-resistant.")
    if prob >= 0.70:
        tips.append("HIGH RISK: Prepare emergency kit and know your building's evacuation route.")
    elif prob >= 0.45:
        tips.append("MODERATE RISK: Be familiar with drop-cover-hold procedures.")
    if not tips:
        tips.append("No significant seismic activity detected. Standard preparedness is sufficient.")
    return tips


# ── Main prediction function ────────────────────────────────────────────────────

def predict_earthquake(lat: float, lon: float) -> dict:
    """
    Full earthquake prediction pipeline.
    Returns a dict ready to serve from the API endpoint.
    """
    features = fetch_earthquake_features(lat, lon)

    prob = 0.0
    ml_model_active = False

    if _EQ_MODEL is not None:
        try:
            row = {k: features[k] for k in EARTHQUAKE_FEATURES}
            df  = pd.DataFrame([row])
            prob = round(float(_EQ_MODEL.predict_proba(df)[0][1]), 3)
            ml_model_active = True
        except Exception as e:
            print(f"[EarthquakeService] ML inference failed: {e}")
            # Physics fallback: zone + fault + recent activity
            zone_score   = (features["seismic_zone"] - 2) / 3.0
            fault_score  = max(0.0, 1.0 - features["dist_to_fault_km"] / 500.0)
            quake_score  = min(features["recent_quakes_30d"] / 20.0, 1.0)
            b_score      = max(0.0, (1.0 - features["b_value"]) / 0.5)
            prob = round(min(zone_score * 0.35 + fault_score * 0.25 + quake_score * 0.25 + b_score * 0.15, 1.0), 3)
    else:
        # Physics fallback when model not loaded
        zone_score   = (features["seismic_zone"] - 2) / 3.0
        fault_score  = max(0.0, 1.0 - features["dist_to_fault_km"] / 500.0)
        quake_score  = min(features["recent_quakes_30d"] / 20.0, 1.0)
        b_score      = max(0.0, (1.0 - features["b_value"]) / 0.5)
        prob = round(min(zone_score * 0.35 + fault_score * 0.25 + quake_score * 0.25 + b_score * 0.15, 1.0), 3)

    risk = _risk_label(prob)

    return {
        "earthquake_risk":   risk,
        "probability":       prob,
        "probability_pct":   f"{prob * 100:.1f}%",
        "risk_high":         prob >= 0.45,
        "forecast_window":   "Next 7 days",
        "target_radius_km":  100,
        "seismic_zone":      features["seismic_zone_label"],
        "features":          features,
        "advice":            _earthquake_advice(prob, features),
        "ml_model_active":   ml_model_active,
        "data_sources":      ["USGS Earthquake Catalog", "ML Model (v2, 12 features)"] if ml_model_active
                             else ["USGS Earthquake Catalog", "Physics Model"],
    }
