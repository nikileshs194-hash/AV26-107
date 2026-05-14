"""
Urban Flood Prediction — Enhanced Training Script v2
=====================================================
Key improvements over v1:
  - 30 Indian cities, 210+ real ERA5 data points (was 98)
  - Real slope from 5-point DEM elevation gradient (matches predict endpoint)
  - Real drainage from OpenStreetMap Overpass API (matches predict endpoint)
  - 3 engineered interaction features (sat_index, rain_burst, drain_eff)
  - Voting ensemble: XGBoost + GradientBoosting + RandomForest
  - 5-fold stratified cross-validation with AUC, F1, Precision, Recall
  - scale_pos_weight / class_weight for imbalance

Run: python collect_and_train.py
"""

import math
import time
import os
import requests
import numpy as np
import pandas as pd
import joblib
from datetime import datetime, timedelta

from sklearn.ensemble import (
    VotingClassifier,
    GradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

# ── Feature list (must match predict.py exactly) ──────────────────────────────
FEATURES = [
    "rainfall_1h", "rainfall_24h", "humidity", "temperature",
    "elevation", "soil_moisture", "drainage", "slope", "pressure",
    "sat_index",   # soil_moisture x rainfall_24h
    "rain_burst",  # rainfall_1h / (rainfall_24h + 1)
    "drain_eff",   # drainage x (slope + 0.5) / 10
]

# ── Flood events (real documented Indian urban floods) ─────────────────────────
FLOOD_EVENTS = [
    # Mumbai — coastal megacity, highest flood frequency
    ("Mumbai",           19.0760, 72.8777, "2005-07-26"),
    ("Mumbai",           19.0760, 72.8777, "2005-07-27"),
    ("Mumbai",           19.0760, 72.8777, "2017-08-29"),
    ("Mumbai",           19.0760, 72.8777, "2019-09-04"),
    ("Mumbai",           19.0760, 72.8777, "2020-08-05"),
    ("Mumbai",           19.0760, 72.8777, "2021-07-18"),
    ("Mumbai",           19.0760, 72.8777, "2022-07-01"),
    ("Mumbai",           19.0760, 72.8777, "2023-06-26"),
    ("Mumbai",           19.0760, 72.8777, "2023-07-25"),
    ("Mumbai",           19.0760, 72.8777, "2024-07-08"),
    # Chennai — low delta plain, NE monsoon floods
    ("Chennai",          13.0827, 80.2707, "2015-11-15"),
    ("Chennai",          13.0827, 80.2707, "2015-12-01"),
    ("Chennai",          13.0827, 80.2707, "2015-12-02"),
    ("Chennai",          13.0827, 80.2707, "2021-11-08"),
    ("Chennai",          13.0827, 80.2707, "2021-11-10"),
    ("Chennai",          13.0827, 80.2707, "2022-10-31"),
    ("Chennai",          13.0827, 80.2707, "2023-09-20"),
    ("Chennai",          13.0827, 80.2707, "2023-12-04"),
    # Hyderabad — flash floods, rapid runoff
    ("Hyderabad",        17.3850, 78.4867, "2020-10-13"),
    ("Hyderabad",        17.3850, 78.4867, "2020-10-14"),
    ("Hyderabad",        17.3850, 78.4867, "2021-09-10"),
    ("Hyderabad",        17.3850, 78.4867, "2022-08-01"),
    ("Hyderabad",        17.3850, 78.4867, "2023-09-08"),
    ("Hyderabad",        17.3850, 78.4867, "2024-07-07"),
    # Bengaluru — rapid urbanisation, lake flooding
    ("Bengaluru",        12.9716, 77.5946, "2017-08-30"),
    ("Bengaluru",        12.9716, 77.5946, "2021-09-06"),
    ("Bengaluru",        12.9716, 77.5946, "2021-08-13"),
    ("Bengaluru",        12.9716, 77.5946, "2022-08-18"),
    ("Bengaluru",        12.9716, 77.5946, "2022-09-05"),
    ("Bengaluru",        12.9716, 77.5946, "2023-09-06"),
    ("Bengaluru",        12.9716, 77.5946, "2024-08-21"),
    # Delhi / NCR — Yamuna flooding + drainage failure
    ("Delhi",            28.6139, 77.2090, "2018-07-28"),
    ("Delhi",            28.6139, 77.2090, "2021-08-01"),
    ("Delhi",            28.6139, 77.2090, "2022-08-07"),
    ("Delhi",            28.6139, 77.2090, "2023-07-09"),
    ("Delhi",            28.6139, 77.2090, "2023-07-10"),
    ("Delhi",            28.6139, 77.2090, "2024-06-28"),
    # Pune — Mula-Mutha river, low-lying areas
    ("Pune",             18.5204, 73.8567, "2019-08-01"),
    ("Pune",             18.5204, 73.8567, "2021-07-22"),
    ("Pune",             18.5204, 73.8567, "2022-09-22"),
    ("Pune",             18.5204, 73.8567, "2023-07-15"),
    ("Pune",             18.5204, 73.8567, "2023-09-24"),
    ("Pune",             18.5204, 73.8567, "2024-07-26"),
    # Kochi — backwaters, heavy SW monsoon
    ("Kochi",             9.9312, 76.2673, "2018-08-15"),
    ("Kochi",             9.9312, 76.2673, "2018-08-16"),
    ("Kochi",             9.9312, 76.2673, "2019-08-08"),
    ("Kochi",             9.9312, 76.2673, "2021-10-16"),
    ("Kochi",             9.9312, 76.2673, "2022-10-14"),
    ("Kochi",             9.9312, 76.2673, "2023-10-19"),
    # Guwahati — Brahmaputra basin, annual floods
    ("Guwahati",         26.1445, 91.7362, "2020-07-10"),
    ("Guwahati",         26.1445, 91.7362, "2021-06-10"),
    ("Guwahati",         26.1445, 91.7362, "2022-06-17"),
    ("Guwahati",         26.1445, 91.7362, "2023-06-25"),
    ("Guwahati",         26.1445, 91.7362, "2024-06-20"),
    # Patna — Ganga river flooding
    ("Patna",            25.5941, 85.1376, "2019-09-29"),
    ("Patna",            25.5941, 85.1376, "2020-08-25"),
    ("Patna",            25.5941, 85.1376, "2021-07-28"),
    ("Patna",            25.5941, 85.1376, "2022-08-10"),
    ("Patna",            25.5941, 85.1376, "2023-07-10"),
    # Kolkata — flat Gangetic delta
    ("Kolkata",          22.5726, 88.3639, "2017-06-20"),
    ("Kolkata",          22.5726, 88.3639, "2020-07-25"),
    ("Kolkata",          22.5726, 88.3639, "2021-05-26"),
    ("Kolkata",          22.5726, 88.3639, "2021-10-20"),
    ("Kolkata",          22.5726, 88.3639, "2022-09-20"),
    ("Kolkata",          22.5726, 88.3639, "2023-09-08"),
    ("Kolkata",          22.5726, 88.3639, "2024-08-01"),
    # Ahmedabad / Gujarat — Sabarmati flooding
    ("Ahmedabad",        23.0225, 72.5714, "2017-07-25"),
    ("Ahmedabad",        23.0225, 72.5714, "2020-08-22"),
    ("Ahmedabad",        23.0225, 72.5714, "2022-07-12"),
    ("Ahmedabad",        23.0225, 72.5714, "2023-08-27"),
    ("Ahmedabad",        23.0225, 72.5714, "2024-07-08"),
    # Surat — low coastal plain, Tapti river
    ("Surat",            21.1702, 72.8311, "2019-08-03"),
    ("Surat",            21.1702, 72.8311, "2022-07-05"),
    ("Surat",            21.1702, 72.8311, "2023-08-20"),
    ("Surat",            21.1702, 72.8311, "2024-07-06"),
    # Vadodara — Vishwamitri river
    ("Vadodara",         22.3072, 73.1812, "2019-08-03"),
    ("Vadodara",         22.3072, 73.1812, "2022-07-05"),
    ("Vadodara",         22.3072, 73.1812, "2023-08-25"),
    ("Vadodara",         22.3072, 73.1812, "2024-07-07"),
    # Vijayawada — Krishna river delta
    ("Vijayawada",       16.5062, 80.6480, "2020-08-17"),
    ("Vijayawada",       16.5062, 80.6480, "2022-08-10"),
    ("Vijayawada",       16.5062, 80.6480, "2022-10-19"),
    ("Vijayawada",       16.5062, 80.6480, "2023-09-01"),
    ("Vijayawada",       16.5062, 80.6480, "2024-09-02"),
    # Bhubaneswar / Odisha — cyclone + monsoon
    ("Bhubaneswar",      20.2961, 85.8245, "2018-05-03"),
    ("Bhubaneswar",      20.2961, 85.8245, "2021-09-02"),
    ("Bhubaneswar",      20.2961, 85.8245, "2022-09-22"),
    ("Bhubaneswar",      20.2961, 85.8245, "2023-10-05"),
    ("Bhubaneswar",      20.2961, 85.8245, "2024-09-27"),
    # Srinagar — Jhelum river
    ("Srinagar",         34.0837, 74.7973, "2014-09-04"),
    ("Srinagar",         34.0837, 74.7973, "2014-09-05"),
    ("Srinagar",         34.0837, 74.7973, "2021-07-26"),
    ("Srinagar",         34.0837, 74.7973, "2022-08-13"),
    ("Srinagar",         34.0837, 74.7973, "2023-07-09"),
    # Amritsar / Punjab — heavy monsoon + Beas river
    ("Amritsar",         31.6340, 74.8723, "2022-08-24"),
    ("Amritsar",         31.6340, 74.8723, "2023-07-09"),
    ("Amritsar",         31.6340, 74.8723, "2024-07-04"),
    # Dehradun — Uttarakhand flash floods
    ("Dehradun",         30.3165, 78.0322, "2021-10-18"),
    ("Dehradun",         30.3165, 78.0322, "2022-10-17"),
    ("Dehradun",         30.3165, 78.0322, "2023-07-10"),
    ("Dehradun",         30.3165, 78.0322, "2024-07-31"),
    # Lucknow — Gomti river, UP floods
    ("Lucknow",          26.8467, 80.9462, "2020-08-22"),
    ("Lucknow",          26.8467, 80.9462, "2022-09-01"),
    ("Lucknow",          26.8467, 80.9462, "2023-07-08"),
    ("Lucknow",          26.8467, 80.9462, "2024-07-03"),
    # Varanasi — Ganga flooding
    ("Varanasi",         25.3176, 82.9739, "2019-09-22"),
    ("Varanasi",         25.3176, 82.9739, "2021-08-11"),
    ("Varanasi",         25.3176, 82.9739, "2022-08-20"),
    ("Varanasi",         25.3176, 82.9739, "2023-07-15"),
    # Nagpur — Nag river, Vidarbha floods
    ("Nagpur",           21.1458, 79.0882, "2021-07-25"),
    ("Nagpur",           21.1458, 79.0882, "2022-07-13"),
    ("Nagpur",           21.1458, 79.0882, "2023-08-11"),
    ("Nagpur",           21.1458, 79.0882, "2024-07-26"),
    # Nashik — Godavari river
    ("Nashik",           19.9975, 73.7898, "2021-07-22"),
    ("Nashik",           19.9975, 73.7898, "2022-07-06"),
    ("Nashik",           19.9975, 73.7898, "2023-08-27"),
    ("Nashik",           19.9975, 73.7898, "2024-08-22"),
    # Aurangabad (Chhatrapati Sambhajinagar) — Maharashtra floods
    ("Aurangabad",       19.8762, 75.3433, "2021-08-01"),
    ("Aurangabad",       19.8762, 75.3433, "2022-09-14"),
    ("Aurangabad",       19.8762, 75.3433, "2023-07-19"),
    ("Aurangabad",       19.8762, 75.3433, "2024-08-01"),
    # Coimbatore — Tamil Nadu western ghats rain
    ("Coimbatore",       11.0168, 76.9558, "2021-11-19"),
    ("Coimbatore",       11.0168, 76.9558, "2022-10-20"),
    ("Coimbatore",       11.0168, 76.9558, "2023-11-18"),
    # Madurai — Vaigai river
    ("Madurai",           9.9252, 78.1198, "2021-11-25"),
    ("Madurai",           9.9252, 78.1198, "2022-10-20"),
    ("Madurai",           9.9252, 78.1198, "2023-12-04"),
    # Thiruvananthapuram — coastal Kerala
    ("Thiruvananthapuram", 8.5241, 76.9366, "2018-08-17"),
    ("Thiruvananthapuram", 8.5241, 76.9366, "2021-10-16"),
    ("Thiruvananthapuram", 8.5241, 76.9366, "2022-10-16"),
    ("Thiruvananthapuram", 8.5241, 76.9366, "2023-10-15"),
    # Mangaluru — coastal Karnataka, heavy SW monsoon
    ("Mangaluru",        12.9141, 74.8560, "2021-08-01"),
    ("Mangaluru",        12.9141, 74.8560, "2022-07-20"),
    ("Mangaluru",        12.9141, 74.8560, "2023-07-14"),
    ("Mangaluru",        12.9141, 74.8560, "2024-07-30"),
    # Raipur — Chhattisgarh monsoon
    ("Raipur",           21.2514, 81.6296, "2021-08-28"),
    ("Raipur",           21.2514, 81.6296, "2022-09-15"),
    ("Raipur",           21.2514, 81.6296, "2023-08-20"),
    # Agra — Yamuna river overflow
    ("Agra",             27.1767, 78.0081, "2021-08-02"),
    ("Agra",             27.1767, 78.0081, "2022-08-13"),
    ("Agra",             27.1767, 78.0081, "2023-07-19"),
    # Jamshedpur — Subarnarekha river, Jharkhand
    ("Jamshedpur",       22.8046, 86.2029, "2022-08-19"),
    ("Jamshedpur",       22.8046, 86.2029, "2023-09-01"),
    ("Jamshedpur",       22.8046, 86.2029, "2024-08-19"),
]

# ── Dry / non-flood reference events (clear, dry-season days) ─────────────────
NON_FLOOD_EVENTS = [
    ("Mumbai",           19.0760, 72.8777, "2024-01-15"),
    ("Mumbai",           19.0760, 72.8777, "2023-03-10"),
    ("Mumbai",           19.0760, 72.8777, "2022-02-20"),
    ("Mumbai",           19.0760, 72.8777, "2021-04-05"),
    ("Mumbai",           19.0760, 72.8777, "2020-01-12"),
    ("Mumbai",           19.0760, 72.8777, "2019-11-15"),
    ("Chennai",          13.0827, 80.2707, "2024-02-20"),
    ("Chennai",          13.0827, 80.2707, "2023-04-10"),
    ("Chennai",          13.0827, 80.2707, "2022-06-01"),
    ("Chennai",          13.0827, 80.2707, "2021-03-15"),
    ("Hyderabad",        17.3850, 78.4867, "2024-01-20"),
    ("Hyderabad",        17.3850, 78.4867, "2023-03-15"),
    ("Hyderabad",        17.3850, 78.4867, "2022-05-05"),
    ("Hyderabad",        17.3850, 78.4867, "2021-01-18"),
    ("Bengaluru",        12.9716, 77.5946, "2024-02-20"),
    ("Bengaluru",        12.9716, 77.5946, "2023-05-01"),
    ("Bengaluru",        12.9716, 77.5946, "2022-01-10"),
    ("Bengaluru",        12.9716, 77.5946, "2021-04-14"),
    ("Delhi",            28.6139, 77.2090, "2024-01-05"),
    ("Delhi",            28.6139, 77.2090, "2023-04-20"),
    ("Delhi",            28.6139, 77.2090, "2022-05-10"),
    ("Delhi",            28.6139, 77.2090, "2021-02-28"),
    ("Delhi",            28.6139, 77.2090, "2020-11-20"),
    ("Pune",             18.5204, 73.8567, "2024-01-25"),
    ("Pune",             18.5204, 73.8567, "2023-03-05"),
    ("Pune",             18.5204, 73.8567, "2022-12-20"),
    ("Kochi",             9.9312, 76.2673, "2024-02-10"),
    ("Kochi",             9.9312, 76.2673, "2023-01-15"),
    ("Kochi",             9.9312, 76.2673, "2022-03-20"),
    ("Guwahati",         26.1445, 91.7362, "2024-01-10"),
    ("Guwahati",         26.1445, 91.7362, "2023-02-20"),
    ("Guwahati",         26.1445, 91.7362, "2022-04-15"),
    ("Patna",            25.5941, 85.1376, "2024-01-20"),
    ("Patna",            25.5941, 85.1376, "2023-03-10"),
    ("Patna",            25.5941, 85.1376, "2022-05-20"),
    ("Kolkata",          22.5726, 88.3639, "2024-02-05"),
    ("Kolkata",          22.5726, 88.3639, "2023-12-10"),
    ("Kolkata",          22.5726, 88.3639, "2022-01-25"),
    ("Ahmedabad",        23.0225, 72.5714, "2024-01-30"),
    ("Ahmedabad",        23.0225, 72.5714, "2023-03-25"),
    ("Ahmedabad",        23.0225, 72.5714, "2022-04-10"),
    ("Surat",            21.1702, 72.8311, "2024-02-20"),
    ("Surat",            21.1702, 72.8311, "2023-04-05"),
    ("Vadodara",         22.3072, 73.1812, "2024-01-15"),
    ("Vadodara",         22.3072, 73.1812, "2023-03-01"),
    ("Vijayawada",       16.5062, 80.6480, "2024-02-25"),
    ("Vijayawada",       16.5062, 80.6480, "2023-04-15"),
    ("Bhubaneswar",      20.2961, 85.8245, "2024-01-10"),
    ("Bhubaneswar",      20.2961, 85.8245, "2023-02-15"),
    ("Srinagar",         34.0837, 74.7973, "2024-05-15"),
    ("Srinagar",         34.0837, 74.7973, "2023-06-01"),
    ("Amritsar",         31.6340, 74.8723, "2024-02-10"),
    ("Amritsar",         31.6340, 74.8723, "2023-04-20"),
    ("Dehradun",         30.3165, 78.0322, "2024-01-25"),
    ("Dehradun",         30.3165, 78.0322, "2023-05-10"),
    ("Lucknow",          26.8467, 80.9462, "2024-01-15"),
    ("Lucknow",          26.8467, 80.9462, "2023-03-20"),
    ("Varanasi",         25.3176, 82.9739, "2024-02-20"),
    ("Varanasi",         25.3176, 82.9739, "2023-04-10"),
    ("Nagpur",           21.1458, 79.0882, "2024-01-05"),
    ("Nagpur",           21.1458, 79.0882, "2023-03-15"),
    ("Nashik",           19.9975, 73.7898, "2024-02-10"),
    ("Nashik",           19.9975, 73.7898, "2023-04-05"),
    ("Aurangabad",       19.8762, 75.3433, "2024-01-25"),
    ("Aurangabad",       19.8762, 75.3433, "2023-03-20"),
    ("Coimbatore",       11.0168, 76.9558, "2024-02-15"),
    ("Coimbatore",       11.0168, 76.9558, "2023-04-20"),
    ("Madurai",           9.9252, 78.1198, "2024-01-20"),
    ("Madurai",           9.9252, 78.1198, "2023-03-10"),
    ("Thiruvananthapuram", 8.5241, 76.9366, "2024-02-05"),
    ("Thiruvananthapuram", 8.5241, 76.9366, "2023-04-25"),
    ("Mangaluru",        12.9141, 74.8560, "2024-01-10"),
    ("Mangaluru",        12.9141, 74.8560, "2023-03-05"),
    ("Raipur",           21.2514, 81.6296, "2024-02-15"),
    ("Raipur",           21.2514, 81.6296, "2023-04-10"),
    ("Agra",             27.1767, 78.0081, "2024-01-15"),
    ("Agra",             27.1767, 78.0081, "2023-02-20"),
    ("Jamshedpur",       22.8046, 86.2029, "2024-01-20"),
    ("Jamshedpur",       22.8046, 86.2029, "2023-03-10"),
    # Arid / dry cities — good negative examples
    ("Jaipur",           26.9124, 75.7873, "2024-05-20"),
    ("Jaipur",           26.9124, 75.7873, "2023-06-10"),
    ("Jaipur",           26.9124, 75.7873, "2024-04-15"),
    ("Jodhpur",          26.2389, 73.0243, "2024-05-15"),
    ("Jodhpur",          26.2389, 73.0243, "2023-06-05"),
    ("Jodhpur",          26.2389, 73.0243, "2024-03-20"),
    ("Chandigarh",       30.7333, 76.7794, "2024-02-20"),
    ("Chandigarh",       30.7333, 76.7794, "2023-05-15"),
    ("Chandigarh",       30.7333, 76.7794, "2024-04-10"),
]


# ── Real slope from 5-point DEM elevation gradient (same as predict.py) ───────

_SLOPE_CACHE: dict = {}

def _fetch_slope_and_elevation(lat: float, lon: float) -> tuple:
    key = (round(lat, 3), round(lon, 3))
    if key in _SLOPE_CACHE:
        return _SLOPE_CACHE[key]
    OFFSET = 0.005
    points = [
        (lat, lon), (lat + OFFSET, lon), (lat - OFFSET, lon),
        (lat, lon + OFFSET), (lat, lon - OFFSET),
    ]
    lats = ",".join(str(p[0]) for p in points)
    lons = ",".join(str(p[1]) for p in points)
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/elevation",
            params={"latitude": lats, "longitude": lons},
            timeout=12,
        )
        elevs = r.json().get("elevation", [])
        if len(elevs) < 5:
            raise ValueError("incomplete")
    except Exception:
        _SLOPE_CACHE[key] = (3.0, 50.0)
        return 3.0, 50.0

    centre, north, south, east, west = [float(e) for e in elevs[:5]]
    dist_ns = OFFSET * 111_000
    dist_ew = OFFSET * 111_000 * math.cos(math.radians(lat))
    dz_ns = abs(north - south) / (2 * dist_ns)
    dz_ew = abs(east  - west)  / (2 * dist_ew)
    slope_deg = math.degrees(math.atan(math.sqrt(dz_ns**2 + dz_ew**2)))
    result = (round(slope_deg, 3), round(centre, 1))
    _SLOPE_CACHE[key] = result
    return result


# ── Real drainage from OpenStreetMap Overpass API (same as predict.py) ────────

_DRAIN_CACHE: dict = {}

def _fetch_drainage_score(lat: float, lon: float, radius_m: int = 1000) -> float:
    key = (round(lat, 3), round(lon, 3))
    if key in _DRAIN_CACHE:
        return _DRAIN_CACHE[key]
    query = f"""
    [out:json][timeout:15];
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
            timeout=18,
        )
        result = r.json()
        total = int(result.get("elements", [{}])[0].get("tags", {}).get("total", 0))
    except Exception:
        _DRAIN_CACHE[key] = 4.0
        return 4.0
    score = min(9.0, 1.0 + (total / 100.0) * 8.0)
    score = round(score, 2)
    _DRAIN_CACHE[key] = score
    return score


# ── Pre-fetch geospatial data for all unique locations ────────────────────────

def prefetch_geo(all_events: list) -> dict:
    """Fetch real slope + drainage once per unique (lat, lon) location."""
    unique = list({(round(lat, 3), round(lon, 3)) for _, lat, lon, _ in all_events})
    print(f"\nFetching real slope + drainage for {len(unique)} unique locations...")
    for i, (lat, lon) in enumerate(unique):
        print(f"  [{i+1}/{len(unique)}] ({lat}, {lon}) ...", end=" ", flush=True)
        slope, elev = _fetch_slope_and_elevation(lat, lon)
        drain = _fetch_drainage_score(lat, lon)
        print(f"slope={slope:.2f}deg  elev={elev:.0f}m  drain={drain:.1f}/10")
        time.sleep(0.6)
    print("Geospatial prefetch complete.\n")


# ── ERA5 historical weather fetch ─────────────────────────────────────────────

def fetch_weather_for_date(lat: float, lon: float, date_str: str) -> dict | None:
    """
    Fetch ERA5 conditions representing state 12 hours BEFORE the event.
    Matches the live /predict endpoint's 12h-ahead forecast structure:
      - past_12h  = hours 12-23 of D-1  (observed before event)
      - next_12h  = hours  0-11 of D    (the flood/dry window)
      - rainfall_1h  = peak hour in next_12h
      - rainfall_24h = past_12h sum + next_12h sum
      - humidity/temp/pressure at D-1 21:00
      - soil_moisture at D-1 12:00
    """
    d0    = datetime.strptime(date_str, "%Y-%m-%d")
    d_prev = (d0 - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        r = requests.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params={
                "latitude":   lat,
                "longitude":  lon,
                "start_date": d_prev,
                "end_date":   date_str,
                "hourly": [
                    "precipitation",
                    "relative_humidity_2m",
                    "temperature_2m",
                    "surface_pressure",
                    "soil_moisture_0_to_7cm",
                ],
                "timezone": "Asia/Kolkata",
            },
            timeout=22,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[WARN] ERA5 error {lat},{lon} {date_str}: {e}")
        return None

    hourly = data.get("hourly", {})
    precip = hourly.get("precipitation", [])
    humid  = hourly.get("relative_humidity_2m", [])
    temp   = hourly.get("temperature_2m", [])
    pres   = hourly.get("surface_pressure", [])
    soil   = hourly.get("soil_moisture_0_to_7cm", [])

    def safe(lst, i): return float(lst[i]) if i < len(lst) and lst[i] is not None else None

    past_12h_rain  = [safe(precip, i) or 0.0 for i in range(12, 24)]
    next_12h_rain  = [safe(precip, i) or 0.0 for i in range(24, 36)]
    if not next_12h_rain:
        return None

    rainfall_1h  = max(next_12h_rain)
    rainfall_24h = sum(past_12h_rain) + sum(next_12h_rain)

    atm_idx     = 21  # D-1 21:00
    humidity    = safe(humid, atm_idx) or 70.0
    temperature = safe(temp,  atm_idx) or 28.0
    pressure    = safe(pres,  atm_idx) or 1005.0
    soil_moist  = safe(soil, 12)       or 0.4

    # Real geospatial (pre-fetched, cached)
    slope, elevation = _fetch_slope_and_elevation(lat, lon)
    drainage         = _fetch_drainage_score(lat, lon)

    # Engineered features
    sat_index  = round(soil_moist * rainfall_24h, 3)
    rain_burst = round(rainfall_1h / max(rainfall_24h, 1.0), 4)
    drain_eff  = round(drainage * (slope + 0.5) / 10.0, 3)

    return {
        "rainfall_1h":   round(rainfall_1h,  3),
        "rainfall_24h":  round(rainfall_24h, 3),
        "humidity":      round(humidity,     2),
        "temperature":   round(temperature,  2),
        "elevation":     round(elevation,    1),
        "soil_moisture": round(min(soil_moist, 1.0), 4),
        "drainage":      round(drainage,     2),
        "slope":         round(slope,        3),
        "pressure":      round(pressure,     2),
        "sat_index":     sat_index,
        "rain_burst":    rain_burst,
        "drain_eff":     drain_eff,
    }


# ── Collect dataset ───────────────────────────────────────────────────────────

def collect(events: list, label: int, desc: str) -> list:
    rows = []
    total = len(events)
    for i, (city, lat, lon, date) in enumerate(events):
        print(f"  [{i+1:3d}/{total}] {desc:8s}  {city:22s}  {date} ...", end=" ", flush=True)
        feats = fetch_weather_for_date(lat, lon, date)
        if feats:
            feats["flood"] = label
            feats["city"]  = city
            rows.append(feats)
            print(f"rain1h={feats['rainfall_1h']:.1f}  rain24h={feats['rainfall_24h']:.1f}  ok")
        else:
            print("skip")
        time.sleep(0.4)
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

all_events = FLOOD_EVENTS + NON_FLOOD_EVENTS
prefetch_geo(all_events)

print("=" * 65)
print(f"Collecting FLOOD weather data ({len(FLOOD_EVENTS)} events)...")
print("=" * 65)
flood_rows = collect(FLOOD_EVENTS, label=1, desc="FLOOD")

print()
print("=" * 65)
print(f"Collecting DRY weather data ({len(NON_FLOOD_EVENTS)} events)...")
print("=" * 65)
dry_rows = collect(NON_FLOOD_EVENTS, label=0, desc="DRY")

df = pd.DataFrame(flood_rows + dry_rows)
n_flood = int(df["flood"].sum())
n_dry   = len(df) - n_flood
print(f"\nDataset: {len(df)} rows  |  Flood: {n_flood}  |  No flood: {n_dry}")

_csv = os.path.join(os.path.dirname(__file__), "flood_dataset_real.csv")
df.to_csv(_csv, index=False)
print(f"Saved -> {_csv}")

# ── Feature matrix ────────────────────────────────────────────────────────────

X = df[FEATURES]
y = df["flood"]

spw = round(n_dry / max(n_flood, 1), 2)
print(f"\nClass balance  ->  flood: {n_flood}  dry: {n_dry}  (scale_pos_weight={spw})")

# ── Voting ensemble: XGBoost + GBM + RandomForest ────────────────────────────

print("\nBuilding voting ensemble (XGBoost + GradientBoosting + RandomForest)...")

xgb_clf = XGBClassifier(
    n_estimators=500,
    max_depth=5,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=2,
    gamma=0.1,
    reg_alpha=0.1,
    reg_lambda=1.5,
    scale_pos_weight=spw,
    eval_metric="auc",
    random_state=42,
    n_jobs=-1,
    verbosity=0,
)

gbm_clf = GradientBoostingClassifier(
    n_estimators=400,
    learning_rate=0.06,
    max_depth=4,
    min_samples_leaf=2,
    subsample=0.85,
    max_features="sqrt",
    random_state=42,
)

rf_clf = RandomForestClassifier(
    n_estimators=300,
    max_depth=8,
    min_samples_leaf=2,
    class_weight="balanced",
    random_state=42,
    n_jobs=-1,
)

model = Pipeline([
    ("scaler", StandardScaler()),
    ("clf", VotingClassifier(
        estimators=[("xgb", xgb_clf), ("gbm", gbm_clf), ("rf", rf_clf)],
        voting="soft",
    )),
])

# ── 5-fold stratified cross-validation ───────────────────────────────────────

print("\nRunning 5-fold stratified cross-validation...")
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
cv_results = cross_validate(
    model, X, y, cv=cv,
    scoring=["roc_auc", "f1", "precision", "recall"],
    n_jobs=1,
)

print(f"\n  ROC-AUC   : {cv_results['test_roc_auc'].mean():.3f} +/- {cv_results['test_roc_auc'].std():.3f}")
print(f"  F1        : {cv_results['test_f1'].mean():.3f} +/- {cv_results['test_f1'].std():.3f}")
print(f"  Precision : {cv_results['test_precision'].mean():.3f} +/- {cv_results['test_precision'].std():.3f}")
print(f"  Recall    : {cv_results['test_recall'].mean():.3f} +/- {cv_results['test_recall'].std():.3f}")

# ── Final fit on full data ────────────────────────────────────────────────────

print("\nFitting final ensemble on full dataset...")
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.15, random_state=42, stratify=y)
model.fit(X_tr, y_tr)

y_pred  = model.predict(X_te)
y_proba = model.predict_proba(X_te)[:, 1]

print(f"\nHold-out test ROC-AUC : {roc_auc_score(y_te, y_proba):.3f}")
print(classification_report(y_te, y_pred, target_names=["No Flood", "Flood"]))

# ── Feature importance (from XGBoost inside the ensemble) ────────────────────

print("Feature importances (from XGBoost):")
xgb_fitted = model.named_steps["clf"].estimators_[0]
for feat, imp in sorted(
    zip(FEATURES, xgb_fitted.feature_importances_),
    key=lambda x: -x[1],
):
    bar = "#" * int(imp * 50)
    print(f"  {feat:20s}  {imp:.3f}  {bar}")

# ── Save model ────────────────────────────────────────────────────────────────

_model_path = os.path.join(os.path.dirname(__file__), "model.pkl")
joblib.dump(model, _model_path)
print(f"\nSaved -> {_model_path}")
print("Run: uvicorn main:app --reload  then  GET /predict?lat=19.07&lon=72.87")
