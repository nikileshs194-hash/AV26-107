"""
Earthquake Risk ML Model — Training Script v1
==============================================
Predicts: probability of M >= 4.5 earthquake within 100 km in the next 7 days.

─── Scientific basis ──────────────────────────────────────────────────────────
  Gutenberg-Richter law  : log10(N) = a - b*M
      b-value captures tectonic stress accumulation in a region.
      High recent activity (low b-region) predicts continued risk.

  Omori-Utsu law         : λ(t) = K / (t + c)^p
      Aftershock rate after a mainshock decays as power-law.
      "recent_quakes_7d" directly captures this elevated rate.

  ETAS concept           : total rate = background + triggered component.
      "energy_index_30d" approximates the seismic moment sum.

  Fault proximity        : earthquakes cluster within 20-50 km of active faults
      (Kagan 2002). dist_to_fault is the strongest spatial predictor.

  Depth effect           : shallow quakes (< 35 km) cause more surface damage.
      depth_avg_30d < 20 km = higher hazard flag.

─── Data source ───────────────────────────────────────────────────────────────
  USGS Earthquake Catalog  (completely free, no API key required)
  https://earthquake.usgs.gov/fdsnws/event/1/

  Region  : Indian subcontinent + surrounding  (lat 4–38, lon 64–100)
  Period  : 2012-01-01 -> 2024-12-31  (13 years)
  Min mag : M >= 2.5  (detectable by most seismic networks in region)

─── Features (8) ──────────────────────────────────────────────────────────────
  recent_quakes_7d   Omori-type activity count  M>=2.5, 150 km, prior 7 d
  recent_quakes_30d  Background rate count       M>=2.5, 150 km, prior 30 d
  max_mag_7d         Foreshock indicator         largest M, 150 km, prior 7 d
  max_mag_30d        Regional stress proxy       largest M, 150 km, prior 30 d
  energy_index_30d   Seismic moment sum proxy    Σ 10^(0.75·M), 150 km, 30 d
  depth_avg_30d      Mean hypocenter depth (km)  shallow = more surface hazard
  dist_to_fault_km   Distance to nearest major Indian fault system (km)
  seismic_zone       India BIS 1893 zone (2–5)

─── Target ────────────────────────────────────────────────────────────────────
  Label = 1 if any M >= 4.5 occurs within 100 km in the next 7 days
  Label = 0 otherwise

Run:  python train_earthquake.py
  -> saves  backend/earthquake_model.pkl
  -> saves  backend/earthquake_dataset.csv
  -> prints feature stats + CV metrics + hold-out evaluation
"""

import math
import time
import os
import random
import requests
import numpy as np
import pandas as pd
import joblib
from datetime import datetime, timedelta, timezone

from sklearn.ensemble import (
    VotingClassifier,
    GradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.metrics import classification_report, roc_auc_score, brier_score_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

random.seed(42)
np.random.seed(42)

# ── Feature list (must match earthquake_service.py EARTHQUAKE_FEATURES) ───────
EARTHQUAKE_FEATURES = [
    "recent_quakes_7d",    # Omori aftershock decay — elevated = high risk
    "recent_quakes_30d",   # background seismicity rate
    "max_mag_7d",          # foreshock indicator (large recent quake)
    "max_mag_30d",         # regional stress proxy
    "energy_index_30d",    # total seismic moment proxy Σ10^(0.75*M)
    "depth_avg_30d",       # mean depth (km) — shallow < 35 km = higher hazard
    "dist_to_fault_km",    # distance to nearest major Indian fault (km)
    "seismic_zone",        # India BIS 1893 seismic zone (2–5)
]

# ── Indian region bounds ──────────────────────────────────────────────────────
LAT_MIN, LAT_MAX = 4.0, 38.0
LON_MIN, LON_MAX = 64.0, 100.0

# ── Major Indian fault system reference points (lat, lon) ────────────────────
# Represents 8 major fault / plate boundary zones affecting Indian seismicity.
# Distance to nearest point is used as the "dist_to_fault_km" feature.
_FAULT_POINTS = [
    # ── Himalayan Arc (Main Frontal Thrust / MBT / MCT) ──────────────────────
    (27.5, 72.5), (28.0, 74.0), (28.5, 76.0), (29.0, 78.0), (29.5, 80.0),
    (29.0, 82.0), (28.5, 84.0), (27.5, 86.0), (27.0, 88.0), (26.5, 89.5),
    (26.0, 91.0), (25.5, 92.5), (25.0, 94.0), (26.0, 95.5), (27.0, 97.0),
    # ── Andaman–Nicobar subduction trench ────────────────────────────────────
    (13.5, 93.8), (12.0, 93.2), (10.0, 92.5), (8.0, 92.0),
    (6.5, 93.5), (5.0, 94.5), (4.5, 95.5),
    # ── Arakan Yoma (NE India – Myanmar boundary zone) ───────────────────────
    (24.5, 93.5), (22.5, 93.5), (20.5, 93.0), (18.5, 94.0), (17.0, 95.0),
    # ── Sagaing Fault (Myanmar – seismically very active) ────────────────────
    (23.0, 96.5), (21.0, 96.0), (19.0, 96.5), (17.5, 96.5),
    # ── Rann of Kutch / Gujarat faults (2001 Bhuj M7.7) ─────────────────────
    (23.8, 68.5), (23.5, 70.0), (23.5, 71.5), (22.8, 72.5),
    # ── Narmada–Son Lineament (central India intra-plate fault) ──────────────
    (22.0, 73.5), (22.5, 75.5), (23.0, 77.5),
    (23.5, 79.5), (23.8, 81.5), (24.0, 83.5),
    # ── Koyna–Warna zone (Maharashtra, reservoir-triggered seismicity) ────────
    (17.4, 73.8), (17.0, 74.0), (16.8, 74.2),
    # ── Indo-Gangetic plain / Delhi–Moradabad fault zone ─────────────────────
    (28.7, 77.2), (28.5, 78.5), (29.0, 79.5),
    # ── Mahanadi graben / Eastern India ──────────────────────────────────────
    (20.5, 83.5), (21.0, 85.5), (21.5, 87.0),
]


# ── Helper: haversine distance ────────────────────────────────────────────────

def _haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _haversine_vec(lat, lon, lats_arr, lons_arr):
    """Vectorised haversine: returns array of distances from (lat,lon) to each row."""
    R = 6371.0
    dlat = np.radians(lats_arr - lat)
    dlon = np.radians(lons_arr - lon)
    a = (np.sin(dlat / 2) ** 2
         + np.cos(np.radians(lat)) * np.cos(np.radians(lats_arr))
         * np.sin(dlon / 2) ** 2)
    return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


# ── Helper: distance to nearest fault point ───────────────────────────────────

_FAULT_LATS = np.array([p[0] for p in _FAULT_POINTS])
_FAULT_LONS = np.array([p[1] for p in _FAULT_POINTS])


def _dist_to_fault(lat: float, lon: float) -> float:
    dists = _haversine_vec(lat, lon, _FAULT_LATS, _FAULT_LONS)
    return round(float(dists.min()), 1)


# ── Helper: India BIS 1893 seismic zone ───────────────────────────────────────

def _seismic_zone(lat: float, lon: float) -> int:
    """
    Approximate India BIS 1893 seismic zone from lat/lon.
    Zone V = Very High (5), Zone II = Low (2).
    Based on the official seismic zone map (BIS 1893 Part 1: 2016).
    """
    # Zone V regions (Very High Damage Risk)
    ZONE_V = [
        # NE India (Assam, Manipur, Meghalaya, Mizoram, Nagaland, Arunachal)
        (22.0, 29.5, 89.5, 97.5),
        # Andaman & Nicobar islands
        (6.0, 14.5, 92.0, 94.5),
        # Kashmir valley
        (33.5, 36.5, 73.5, 77.5),
        # Rann of Kutch (Gujarat)
        (22.5, 24.5, 68.0, 71.5),
        # N Himachal Pradesh (Chamba–Kangra)
        (32.0, 33.5, 75.5, 78.5),
    ]
    # Zone IV regions (High Damage Risk)
    ZONE_IV = [
        # Sikkim + WB hills
        (26.5, 28.5, 87.5, 90.5),
        # Uttarakhand Himalayan region
        (29.5, 31.5, 78.0, 81.0),
        # J&K hills (non-Zone V)
        (32.0, 35.5, 74.0, 77.5),
        # Delhi NCR
        (28.0, 29.5, 76.5, 78.5),
        # UP Himalayan foothills
        (27.5, 30.0, 80.0, 84.0),
        # Bihar–Nepal border zone
        (26.5, 27.5, 83.0, 88.0),
        # Parts of N Gujarat (non-Kutch)
        (22.0, 24.0, 71.5, 74.0),
        # Koyna–Warna (Maharashtra)
        (17.0, 18.5, 73.5, 75.0),
        # Parts of HP plains
        (30.5, 32.5, 75.0, 78.0),
    ]
    for lat_min, lat_max, lon_min, lon_max in ZONE_V:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return 5
    for lat_min, lat_max, lon_min, lon_max in ZONE_IV:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return 4
    # Zone III: most Gangetic plains, coastal belts, parts of Rajasthan
    if 8.0 <= lat <= 28.0 and 70.0 <= lon <= 90.0:
        return 3
    # Zone II: stable Deccan plateau and southern peninsula
    return 2


# ── USGS data fetcher ─────────────────────────────────────────────────────────

def fetch_usgs_catalog(start_year: int, end_year: int, min_mag: float = 2.5) -> pd.DataFrame:
    """
    Fetch earthquake catalog from USGS for the Indian region.
    Fetches year-by-year to stay within the 20,000-result API limit.
    Saves/loads cache CSV to avoid re-fetching.
    """
    cache_path = os.path.join(os.path.dirname(__file__), "earthquake_catalog_cache.csv")

    if os.path.exists(cache_path):
        print(f"[USGS] Loading cached catalog from {cache_path}")
        df = pd.read_csv(cache_path, parse_dates=["time"])
        print(f"[USGS] Loaded {len(df)} events from cache.")
        return df

    print(f"[USGS] Fetching catalog {start_year}–{end_year}, M>={min_mag} ...")
    all_rows = []

    for year in range(start_year, end_year + 1):
        # Split into 6-month windows to avoid 20k limit
        for (s_month, e_month) in [(1, 6), (7, 12)]:
            start = f"{year}-{s_month:02d}-01"
            if e_month == 12:
                end = f"{year}-12-31"
            else:
                end = f"{year}-06-30"

            url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
            params = {
                "format":       "geojson",
                "starttime":    start,
                "endtime":      end,
                "minlatitude":  LAT_MIN,
                "maxlatitude":  LAT_MAX,
                "minlongitude": LON_MIN,
                "maxlongitude": LON_MAX,
                "minmagnitude": min_mag,
                "orderby":      "time",
                "limit":        20000,
            }

            for attempt in range(3):
                try:
                    r = requests.get(url, params=params, timeout=30)
                    r.raise_for_status()
                    features = r.json().get("features", [])
                    break
                except Exception as e:
                    print(f"  [WARN] {year}-H{1 if s_month==1 else 2} attempt {attempt+1}: {e}")
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                    else:
                        features = []

            for feat in features:
                props = feat.get("properties", {})
                coords = feat.get("geometry", {}).get("coordinates", [None, None, None])
                ts_ms  = props.get("time")
                if ts_ms is None or coords[0] is None:
                    continue
                all_rows.append({
                    "time":  datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
                    "lat":   float(coords[1]),
                    "lon":   float(coords[0]),
                    "depth": float(coords[2]) if coords[2] is not None else 10.0,
                    "mag":   float(props.get("mag") or 0.0),
                })

            print(f"  {year}-H{1 if s_month==1 else 2}: {len(features)} events  "
                  f"(total so far: {len(all_rows)})")
            time.sleep(0.5)   # polite rate-limiting

    df = pd.DataFrame(all_rows)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df.to_csv(cache_path, index=False)
    print(f"[USGS] Saved {len(df)} events -> {cache_path}")
    return df


# ── Feature computation from in-memory catalog ────────────────────────────────

def compute_features(
    lat: float,
    lon: float,
    ref_date: datetime,
    catalog: pd.DataFrame,
    radius_km: float = 150.0,
) -> dict | None:
    """
    Compute all 8 ML features for a (lat, lon, date) sample using in-memory catalog.
    ref_date:  the "now" reference point — features use the prior 30 days.
    Returns None if there are too few events to compute reliable features.
    """
    # 30-day and 7-day windows ending at ref_date
    win_end  = ref_date
    win_30d  = ref_date - timedelta(days=30)
    win_7d   = ref_date - timedelta(days=7)

    # Filter catalog to the 30-day window
    mask_time = (catalog["time"] >= win_30d) & (catalog["time"] < win_end)
    sub = catalog[mask_time]

    if len(sub) == 0:
        # Use zone + fault only (no recent activity data)
        return {
            "recent_quakes_7d":  0,
            "recent_quakes_30d": 0,
            "max_mag_7d":        0.0,
            "max_mag_30d":       0.0,
            "energy_index_30d":  0.0,
            "depth_avg_30d":     35.0,
            "dist_to_fault_km":  _dist_to_fault(lat, lon),
            "seismic_zone":      _seismic_zone(lat, lon),
        }

    # Vectorised distance filter
    dists = _haversine_vec(lat, lon, sub["lat"].values, sub["lon"].values)
    in_radius = dists <= radius_km
    nearby = sub[in_radius].copy()
    nearby_7d = nearby[nearby["time"] >= win_7d]

    n_30d = len(nearby)
    n_7d  = len(nearby_7d)
    max_mag_30d = float(nearby["mag"].max())    if n_30d > 0 else 0.0
    max_mag_7d  = float(nearby_7d["mag"].max()) if n_7d  > 0 else 0.0

    # Energy index: proportional to seismic moment (Hanks & Kanamori 1979)
    energy_30d = float(np.sum(10 ** (0.75 * nearby["mag"].values))) if n_30d > 0 else 0.0

    depths = nearby["depth"].dropna()
    depth_avg = float(depths.mean()) if len(depths) > 0 else 35.0

    return {
        "recent_quakes_7d":  n_7d,
        "recent_quakes_30d": n_30d,
        "max_mag_7d":        round(max_mag_7d,  2),
        "max_mag_30d":       round(max_mag_30d, 2),
        "energy_index_30d":  round(energy_30d,  2),
        "depth_avg_30d":     round(depth_avg,   1),
        "dist_to_fault_km":  _dist_to_fault(lat, lon),
        "seismic_zone":      _seismic_zone(lat, lon),
    }


def has_significant_quake(
    lat: float,
    lon: float,
    start_date: datetime,
    catalog: pd.DataFrame,
    radius_km: float = 100.0,
    min_mag: float = 4.5,
) -> bool:
    """Return True if any M>=min_mag occurred within radius_km in [start_date, +7 days]."""
    win_end = start_date + timedelta(days=7)
    mask = (
        (catalog["time"] >= start_date) &
        (catalog["time"] <  win_end) &
        (catalog["mag"]  >= min_mag)
    )
    candidates = catalog[mask]
    if len(candidates) == 0:
        return False
    dists = _haversine_vec(lat, lon, candidates["lat"].values, candidates["lon"].values)
    return bool(np.any(dists <= radius_km))


# ── Sample generation ─────────────────────────────────────────────────────────

def build_positive_samples(catalog: pd.DataFrame) -> list[dict]:
    """
    For every M >= 4.5 event in the catalog, use its location as the sample point
    and compute features from the 30 days BEFORE that event.
    Label = 1.
    """
    print("\n[Samples] Building POSITIVE samples (all M>=4.5 events)...")
    sig_events = catalog[catalog["mag"] >= 4.5].copy()
    # Need at least 30 days of history -> skip first month
    cutoff = catalog["time"].min() + timedelta(days=31)
    sig_events = sig_events[sig_events["time"] > cutoff]

    rows = []
    total = len(sig_events)
    for i, (_, evt) in enumerate(sig_events.iterrows()):
        feats = compute_features(evt["lat"], evt["lon"], evt["time"], catalog)
        if feats is None:
            continue
        feats["label"] = 1
        feats["lat"]   = round(evt["lat"], 4)
        feats["lon"]   = round(evt["lon"], 4)
        feats["date"]  = evt["time"].strftime("%Y-%m-%d")
        rows.append(feats)
        if (i + 1) % 50 == 0:
            print(f"  Positive: {i+1}/{total} processed ({len(rows)} ok)")
    print(f"  Total positive samples: {len(rows)}")
    return rows


def build_negative_samples(
    catalog: pd.DataFrame,
    n_target: int,
    seed: int = 42,
) -> list[dict]:
    """
    Generate negative samples (label=0) by:
    1. Sampling random (lat, lon) points across the Indian region.
    2. Sampling a random date from the catalog time range.
    3. Verifying no M>=4.5 occurs within 100km in the next 7 days.
    4. Computing features from the 30-day prior window.
    """
    print(f"\n[Samples] Building NEGATIVE samples (target: {n_target})...")
    rng = random.Random(seed)

    t_min = catalog["time"].min() + timedelta(days=31)
    t_max = catalog["time"].max() - timedelta(days=8)
    total_days = (t_max - t_min).days

    # Pre-cache all M>=4.5 events for fast negative checking
    sig = catalog[catalog["mag"] >= 4.5].copy()

    # Candidate grid: spread across the Indian region
    # Use a mix of high-seismicity locations + random
    high_seismicity = [
        # Himalayan belt
        (30.0, 79.0), (29.5, 81.0), (27.0, 88.5), (26.0, 91.5), (25.0, 93.0),
        (28.0, 95.5), (32.0, 76.0), (34.0, 74.5),
        # Northeast India
        (25.0, 92.0), (24.5, 94.5), (26.5, 93.5), (23.5, 92.5),
        # Andaman
        (12.0, 93.0), (9.5, 92.0), (7.0, 93.5),
        # Gujarat / Kutch
        (23.5, 70.5), (24.0, 69.5), (22.5, 71.0),
        # Central India (Narmada belt)
        (22.5, 76.0), (23.0, 80.0), (22.0, 82.0),
        # Peninsular India
        (17.5, 73.8), (15.0, 76.5), (13.0, 80.0), (18.0, 83.5),
        # Indo-Gangetic plain
        (28.7, 77.2), (26.5, 80.5), (25.0, 85.0),
    ]

    rows = []
    attempts = 0
    max_attempts = n_target * 20

    while len(rows) < n_target and attempts < max_attempts:
        attempts += 1

        # Alternate between high-seismicity points and fully random
        if rng.random() < 0.5 and high_seismicity:
            base_lat, base_lon = rng.choice(high_seismicity)
            # Add small jitter
            lat = base_lat + rng.uniform(-2.0, 2.0)
            lon = base_lon + rng.uniform(-2.0, 2.0)
        else:
            lat = rng.uniform(LAT_MIN + 1, LAT_MAX - 1)
            lon = rng.uniform(LON_MIN + 1, LON_MAX - 1)

        lat = round(max(LAT_MIN, min(LAT_MAX, lat)), 3)
        lon = round(max(LON_MIN, min(LON_MAX, lon)), 3)

        day_offset = rng.randint(0, total_days)
        ref_date   = t_min + timedelta(days=day_offset)

        # Check: must NOT have M>=4.5 within 100km in next 7 days
        if has_significant_quake(lat, lon, ref_date, sig, radius_km=100.0):
            continue   # positive case — skip

        feats = compute_features(lat, lon, ref_date, catalog)
        if feats is None:
            continue

        feats["label"] = 0
        feats["lat"]   = lat
        feats["lon"]   = lon
        feats["date"]  = ref_date.strftime("%Y-%m-%d")
        rows.append(feats)

        if len(rows) % 50 == 0:
            print(f"  Negative: {len(rows)}/{n_target}  (attempts: {attempts})")

    print(f"  Total negative samples: {len(rows)}")
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

print("=" * 72)
print("Earthquake Risk ML Model — Training Script v1")
print("=" * 72)

# Step 1: Fetch / load catalog
catalog = fetch_usgs_catalog(start_year=2012, end_year=2024, min_mag=2.5)
catalog["time"] = pd.to_datetime(catalog["time"], format="mixed", utc=True)
catalog = catalog.dropna(subset=["lat", "lon", "mag"])
print(f"\nCatalog size: {len(catalog)} events  "
      f"| M>=4.5: {(catalog.mag>=4.5).sum()}  "
      f"| M>=2.5: {len(catalog)}")

# Step 2: Build samples
positive_rows = build_positive_samples(catalog)
n_pos = len(positive_rows)
# Use 1.5× negatives for slight imbalance (helps precision on rare positive class)
negative_rows = build_negative_samples(catalog, n_target=int(n_pos * 1.5))

df = pd.DataFrame(positive_rows + negative_rows)
n_cyc = int(df["label"].sum())
n_clr = len(df) - n_cyc
print(f"\nDataset: {len(df)} rows  |  Positive (EQ): {n_cyc}  |  Negative: {n_clr}")

_csv = os.path.join(os.path.dirname(__file__), "earthquake_dataset.csv")
df.to_csv(_csv, index=False)
print(f"Saved -> {_csv}")

# Step 3: Feature matrix
X = df[EARTHQUAKE_FEATURES]
y = df["label"]
spw = round(n_clr / max(n_cyc, 1), 2)
print(f"\nClass balance -> EQ:{n_cyc}  Clear:{n_clr}  (scale_pos_weight={spw})")

# Step 4: Feature statistics with Cohen's d
print("\nFeature statistics (mean +/- std)  |  Cohen d:")
print(f"  {'Feature':22s}  {'EQ (pos)':18s}  {'No EQ (neg)':18s}  d")
for feat in EARTHQUAKE_FEATURES:
    cy = df[df.label == 1][feat]
    cl = df[df.label == 0][feat]
    pooled = ((cy.std() ** 2 + cl.std() ** 2) / 2) ** 0.5
    d = abs(cy.mean() - cl.mean()) / (pooled + 1e-9)
    print(f"  {feat:22s}  {cy.mean():6.2f}+-{cy.std():.2f}   "
          f"{cl.mean():6.2f}+-{cl.std():.2f}   d={d:.2f}")

# Step 5: Ensemble model
print("\nBuilding VotingClassifier ensemble (XGBoost + GBM + RandomForest)...")

xgb = XGBClassifier(
    n_estimators=700,
    max_depth=5,
    learning_rate=0.035,
    subsample=0.80,
    colsample_bytree=0.75,
    min_child_weight=2,
    gamma=0.10,
    reg_alpha=0.10,
    reg_lambda=1.2,
    scale_pos_weight=spw,
    eval_metric="auc",
    random_state=42,
    n_jobs=-1,
    verbosity=0,
)

gbm = GradientBoostingClassifier(
    n_estimators=500,
    learning_rate=0.04,
    max_depth=4,
    min_samples_leaf=3,
    subsample=0.85,
    max_features="sqrt",
    random_state=42,
)

rf = RandomForestClassifier(
    n_estimators=500,
    max_depth=10,
    min_samples_leaf=3,
    class_weight="balanced",
    random_state=42,
    n_jobs=-1,
)

model = Pipeline([
    ("scaler", StandardScaler()),
    ("clf", VotingClassifier(
        estimators=[("xgb", xgb), ("gbm", gbm), ("rf", rf)],
        voting="soft",
    )),
])

# Step 6: 5-fold cross-validation
print("\nRunning 5-fold stratified cross-validation...")
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
cv_res = cross_validate(
    model, X, y, cv=cv,
    scoring=["roc_auc", "f1", "precision", "recall"],
    n_jobs=1,
)

auc_mean = cv_res["test_roc_auc"].mean()
auc_std  = cv_res["test_roc_auc"].std()
print(f"\n  ROC-AUC   : {auc_mean:.3f} +/- {auc_std:.3f}   ({auc_mean*100:.1f}%)")
print(f"  F1        : {cv_res['test_f1'].mean():.3f} +/- {cv_res['test_f1'].std():.3f}")
print(f"  Precision : {cv_res['test_precision'].mean():.3f} +/- {cv_res['test_precision'].std():.3f}")
print(f"  Recall    : {cv_res['test_recall'].mean():.3f} +/- {cv_res['test_recall'].std():.3f}")

# Step 7: Hold-out evaluation
print("\nFitting on 85% data, testing on 15% hold-out...")
X_tr, X_te, y_tr, y_te = train_test_split(
    X, y, test_size=0.15, random_state=42, stratify=y
)
model.fit(X_tr, y_tr)

y_pred  = model.predict(X_te)
y_proba = model.predict_proba(X_te)[:, 1]
holdout_auc = roc_auc_score(y_te, y_proba)
brier       = brier_score_loss(y_te, y_proba)

print(f"  Hold-out ROC-AUC : {holdout_auc:.3f}  ({holdout_auc*100:.1f}%)")
print(f"  Brier Score      : {brier:.3f}  (0=perfect, 0.25=random)")
print(classification_report(y_te, y_pred, target_names=["No EQ", "EQ Risk"]))

# Step 8: Feature importances (XGBoost)
print("Feature importances (XGBoost):")
xgb_fitted = model.named_steps["clf"].estimators_[0]
for feat, imp in sorted(
    zip(EARTHQUAKE_FEATURES, xgb_fitted.feature_importances_),
    key=lambda x: -x[1],
):
    bar = "#" * int(imp * 60)
    print(f"  {feat:22s}  {imp*100:5.1f}%  {bar}")

# Step 9: Save
_out = os.path.join(os.path.dirname(__file__), "earthquake_model.pkl")
joblib.dump(model, _out)
print(f"\nSaved -> {_out}")
print(f"CV  ROC-AUC : {auc_mean*100:.1f}%  (+/- {auc_std*100:.1f}%)")
print(f"Hold-out AUC: {holdout_auc*100:.1f}%")
print(f"Features ({len(EARTHQUAKE_FEATURES)}): {EARTHQUAKE_FEATURES}")
