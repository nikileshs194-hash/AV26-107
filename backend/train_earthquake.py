"""
Earthquake Risk ML Model — Training Script v2
==============================================
Predicts: probability of M >= 4.5 earthquake within 100 km in the next 7 days.

----- Scientific upgrades over v1 -------------------------------------------------
  b-value (Gutenberg-Richter / Aki 1965 MLE)
      b = log10(e) / (mean_M - Mc)    where Mc = completeness magnitude (2.0)
      Low b-value => high differential stress => higher chance of large rupture.
      This is THE canonical seismological stress indicator (Aki 1965, Wiemer 2001).

  Inter-event time coefficient of variation (CV)
      cv = std(dt) / mean(dt)    where dt = consecutive event gaps (days)
      CV > 1 = aftershock clustering (Omori-Utsu cascade, dangerous)
      CV ~ 1 = Poisson background seismicity (moderate)
      CV < 1 = seismic quiescence (strain accumulation)

  Seismic acceleration ratio
      accel = (n_7d / 7) / (n_30d / 30)
      > 1 => foreshock swarm (Mogi-doughnut / rate increase), < 1 => decelerating

  Shallow depth fraction
      depth_shallow_frac = count(depth < 30km) / total_nearby
      Shallow crustal quakes cause dramatically more surface damage and
      are the main source of M>=4.5 risk in intraplate India.

  Temporal hold-out split (NEW: 2005-2022 train, 2023-2024 test)
      Prevents aftershock sequences straddling the train/test boundary,
      which inflates hold-out AUC by ~4-6 points in random splits.

----- Data source ------------------------------------------------------------------
  USGS Earthquake Catalog  (free, no API key)
  https://earthquake.usgs.gov/fdsnws/event/1/
  Region  : Indian subcontinent + surrounding  (lat 4-38, lon 64-100)
  Period  : 2005-01-01 -> 2024-12-31  (20 years, +7 years vs v1)
  Min mag : M >= 2.0  (needed for reliable b-value estimation)

----- Features (12, up from 8) -----------------------------------------------------
  recent_quakes_7d      Omori aftershock decay count          M>=2.0, 150km, 7d
  recent_quakes_30d     Background seismicity rate count      M>=2.0, 150km, 30d
  max_mag_7d            Foreshock indicator                   largest M, 7d
  max_mag_30d           Regional stress proxy                 largest M, 30d
  energy_index_30d      Seismic moment sum proxy              sum 10^(0.75*M), 30d
  b_value               Aki MLE b-value                       90d / 200km window
  cv_interevent         Inter-event time CV                   clustering indicator
  quake_acceleration    rate_7d / rate_30d ratio              foreshock swarm flag
  depth_avg_30d         Mean hypocenter depth (km)            shallow = high hazard
  depth_shallow_frac    Fraction of quakes at depth < 30km    crustal hazard ratio
  dist_to_fault_km      Distance to nearest major Indian fault (km)
  seismic_zone          India BIS 1893 zone (2-5)

----- Target -----------------------------------------------------------------------
  Label = 1 if any M >= 4.5 occurs within 100 km in the next 7 days
  Label = 0 otherwise

Run:  python train_earthquake.py
  -> saves  backend/earthquake_model.pkl
  -> saves  backend/earthquake_dataset_v2.csv
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

# ---- Feature list (must match earthquake_service.py EARTHQUAKE_FEATURES) --------
EARTHQUAKE_FEATURES = [
    "recent_quakes_7d",     # Omori aftershock decay count
    "recent_quakes_30d",    # background seismicity rate
    "max_mag_7d",           # foreshock indicator
    "max_mag_30d",          # regional stress proxy
    "energy_index_30d",     # seismic moment sum proxy Σ10^(0.75*M)
    "b_value",              # Aki 1965 MLE b-value — stress indicator
    "cv_interevent",        # inter-event time CV — clustering / quiescence
    "quake_acceleration",   # rate_7d / rate_30d — foreshock swarm ratio
    "depth_avg_30d",        # mean hypocenter depth (km)
    "depth_shallow_frac",   # fraction of events at depth < 30km
    "dist_to_fault_km",     # distance to nearest major Indian fault (km)
    "seismic_zone",         # India BIS 1893 zone (2-5)
]

# ---- Indian region bounds -------------------------------------------------------
LAT_MIN, LAT_MAX = 4.0, 38.0
LON_MIN, LON_MAX = 64.0, 100.0

# Completeness magnitude for b-value (M>=2.0 catalog)
MC = 2.0

# ---- Major Indian fault system reference points (lat, lon) ----------------------
_FAULT_POINTS = [
    # Himalayan Arc (Main Frontal Thrust / MBT / MCT)
    (27.5, 72.5), (28.0, 74.0), (28.5, 76.0), (29.0, 78.0), (29.5, 80.0),
    (29.0, 82.0), (28.5, 84.0), (27.5, 86.0), (27.0, 88.0), (26.5, 89.5),
    (26.0, 91.0), (25.5, 92.5), (25.0, 94.0), (26.0, 95.5), (27.0, 97.0),
    # Andaman-Nicobar subduction trench
    (13.5, 93.8), (12.0, 93.2), (10.0, 92.5), (8.0, 92.0),
    (6.5, 93.5), (5.0, 94.5), (4.5, 95.5),
    # Arakan Yoma (NE India - Myanmar boundary zone)
    (24.5, 93.5), (22.5, 93.5), (20.5, 93.0), (18.5, 94.0), (17.0, 95.0),
    # Sagaing Fault (Myanmar - seismically very active)
    (23.0, 96.5), (21.0, 96.0), (19.0, 96.5), (17.5, 96.5),
    # Rann of Kutch / Gujarat faults (2001 Bhuj M7.7)
    (23.8, 68.5), (23.5, 70.0), (23.5, 71.5), (22.8, 72.5),
    # Narmada-Son Lineament (central India intra-plate fault)
    (22.0, 73.5), (22.5, 75.5), (23.0, 77.5),
    (23.5, 79.5), (23.8, 81.5), (24.0, 83.5),
    # Koyna-Warna zone (Maharashtra, reservoir-triggered seismicity)
    (17.4, 73.8), (17.0, 74.0), (16.8, 74.2),
    # Delhi-Moradabad fault zone
    (28.7, 77.2), (28.5, 78.5), (29.0, 79.5),
    # Mahanadi graben / Eastern India
    (20.5, 83.5), (21.0, 85.5), (21.5, 87.0),
]

_FAULT_LATS = np.array([p[0] for p in _FAULT_POINTS])
_FAULT_LONS = np.array([p[1] for p in _FAULT_POINTS])


# ---- Helper: haversine distance -------------------------------------------------

def _haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def _haversine_vec(lat, lon, lats_arr, lons_arr):
    R = 6371.0
    dlat = np.radians(lats_arr - lat)
    dlon = np.radians(lons_arr - lon)
    a = (np.sin(dlat / 2) ** 2
         + np.cos(np.radians(lat)) * np.cos(np.radians(lats_arr))
         * np.sin(dlon / 2) ** 2)
    return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _dist_to_fault(lat: float, lon: float) -> float:
    return round(float(_haversine_vec(lat, lon, _FAULT_LATS, _FAULT_LONS).min()), 1)


# ---- Helper: India BIS 1893 seismic zone ----------------------------------------

def _seismic_zone(lat: float, lon: float) -> int:
    ZONE_V = [
        (22.0, 29.5, 89.5, 97.5),   # NE India
        (6.0,  14.5, 92.0, 94.5),   # Andaman & Nicobar
        (33.5, 36.5, 73.5, 77.5),   # Kashmir valley
        (22.5, 24.5, 68.0, 71.5),   # Rann of Kutch
        (32.0, 33.5, 75.5, 78.5),   # N Himachal Pradesh
    ]
    ZONE_IV = [
        (26.5, 28.5, 87.5, 90.5),   # Sikkim + WB hills
        (29.5, 31.5, 78.0, 81.0),   # Uttarakhand Himalayan
        (32.0, 35.5, 74.0, 77.5),   # J&K hills
        (28.0, 29.5, 76.5, 78.5),   # Delhi NCR
        (27.5, 30.0, 80.0, 84.0),   # UP Himalayan foothills
        (26.5, 27.5, 83.0, 88.0),   # Bihar-Nepal border
        (22.0, 24.0, 71.5, 74.0),   # N Gujarat
        (17.0, 18.5, 73.5, 75.0),   # Koyna-Warna
        (30.5, 32.5, 75.0, 78.0),   # HP plains
    ]
    for a, b, c, d in ZONE_V:
        if a <= lat <= b and c <= lon <= d:
            return 5
    for a, b, c, d in ZONE_IV:
        if a <= lat <= b and c <= lon <= d:
            return 4
    if 8.0 <= lat <= 28.0 and 70.0 <= lon <= 90.0:
        return 3
    return 2


# ---- Regional b-value fallbacks (when too few events for MLE) -------------------
_ZONE_B_DEFAULT = {5: 0.90, 4: 0.87, 3: 0.82, 2: 0.78}


# ---- Scientific feature: Aki (1965) MLE b-value ---------------------------------

def _compute_b_value(mags: np.ndarray, mc: float = MC) -> float:
    """
    Aki (1965) maximum-likelihood b-value estimator:
        b = log10(e) / (mean(M) - Mc)
    where Mc is the completeness magnitude.

    Returns fallback of 1.0 (global average) if fewer than 20 events.
    """
    mags = mags[mags >= mc]
    if len(mags) < 20:
        return 1.0   # global average; caller replaces with zone fallback
    mean_m = float(mags.mean())
    if mean_m <= mc:
        return 1.0
    b = math.log10(math.e) / (mean_m - mc)
    # Clip to geologically plausible range [0.5, 2.0]
    return round(float(np.clip(b, 0.5, 2.0)), 3)


# ---- Scientific feature: inter-event time CV ------------------------------------

def _compute_cv_interevent(times_sorted: pd.Series) -> float:
    """
    Coefficient of variation of inter-event times.
    CV > 1 = clustered (aftershock sequence)
    CV ~ 1 = Poisson background
    CV < 1 = quiescent (strain accumulation)
    """
    if len(times_sorted) < 3:
        return 1.0   # neutral Poisson baseline
    times_sorted = times_sorted.sort_values()
    diffs = times_sorted.diff().dropna().dt.total_seconds() / 3600.0   # hours
    diffs = diffs[diffs > 0]
    if len(diffs) < 2:
        return 1.0
    cv = float(diffs.std() / (diffs.mean() + 1e-9))
    return round(float(np.clip(cv, 0.0, 10.0)), 3)


# ---- Core feature computation ---------------------------------------------------

def compute_features(
    lat: float,
    lon: float,
    ref_date: datetime,
    catalog: pd.DataFrame,
    radius_km: float = 150.0,
    b_radius_km: float = 200.0,
    b_days: int = 90,
) -> dict | None:
    """
    Compute all 12 ML features for a (lat, lon, date) sample.
    ref_date : the 'now' reference — features use the prior 30/90 days.
    Returns None only if catastrophically bad data.
    """
    win_end  = ref_date
    win_30d  = ref_date - timedelta(days=30)
    win_7d   = ref_date - timedelta(days=7)
    win_90d  = ref_date - timedelta(days=b_days)

    # ---- Standard 30-day window (radius 150km) ----------------------------------
    mask_30d = (catalog["time"] >= win_30d) & (catalog["time"] < win_end)
    sub_30d  = catalog[mask_30d]

    if len(sub_30d) > 0:
        dists_30d  = _haversine_vec(lat, lon, sub_30d["lat"].values, sub_30d["lon"].values)
        nearby_30d = sub_30d[dists_30d <= radius_km].copy()
    else:
        nearby_30d = pd.DataFrame(columns=["time", "mag", "depth"])

    nearby_7d = nearby_30d[nearby_30d["time"] >= win_7d]

    n_30d = len(nearby_30d)
    n_7d  = len(nearby_7d)

    max_mag_30d = float(nearby_30d["mag"].max()) if n_30d > 0 else 0.0
    max_mag_7d  = float(nearby_7d["mag"].max())  if n_7d  > 0 else 0.0

    energy_30d = (
        float(np.sum(10 ** (0.75 * nearby_30d["mag"].values))) if n_30d > 0 else 0.0
    )

    depths    = nearby_30d["depth"].dropna()
    depth_avg = float(depths.mean()) if len(depths) > 0 else 35.0
    depth_shallow_frac = (
        float((depths < 30.0).sum() / len(depths)) if len(depths) > 0 else 0.5
    )

    # Seismic acceleration: daily rate comparison
    rate_7d   = n_7d  / 7.0
    rate_30d  = n_30d / 30.0
    quake_acceleration = round(float(rate_7d / (rate_30d + 1e-6)), 3)
    quake_acceleration = float(np.clip(quake_acceleration, 0.0, 20.0))

    # ---- Extended 90-day window (radius 200km) for b-value + CV -----------------
    mask_90d = (catalog["time"] >= win_90d) & (catalog["time"] < win_end)
    sub_90d  = catalog[mask_90d]

    if len(sub_90d) > 0:
        dists_90d  = _haversine_vec(lat, lon, sub_90d["lat"].values, sub_90d["lon"].values)
        nearby_90d = sub_90d[dists_90d <= b_radius_km].copy()
    else:
        nearby_90d = pd.DataFrame(columns=["time", "mag", "depth"])

    # b-value
    if len(nearby_90d) >= 20:
        b_val = _compute_b_value(nearby_90d["mag"].values)
    else:
        # Zone-based fallback
        zone    = _seismic_zone(lat, lon)
        b_val   = _ZONE_B_DEFAULT.get(zone, 0.85)

    # Inter-event CV
    if len(nearby_90d) >= 3:
        cv_ie = _compute_cv_interevent(nearby_90d["time"])
    else:
        cv_ie = 1.0

    return {
        "recent_quakes_7d":    n_7d,
        "recent_quakes_30d":   n_30d,
        "max_mag_7d":          round(max_mag_7d,  2),
        "max_mag_30d":         round(max_mag_30d, 2),
        "energy_index_30d":    round(energy_30d,  2),
        "b_value":             round(b_val,        3),
        "cv_interevent":       round(cv_ie,        3),
        "quake_acceleration":  round(quake_acceleration, 3),
        "depth_avg_30d":       round(depth_avg,    1),
        "depth_shallow_frac":  round(depth_shallow_frac, 3),
        "dist_to_fault_km":    _dist_to_fault(lat, lon),
        "seismic_zone":        _seismic_zone(lat, lon),
    }


def has_significant_quake(
    lat: float, lon: float, start_date: datetime,
    catalog: pd.DataFrame, radius_km: float = 100.0, min_mag: float = 4.5,
) -> bool:
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


# ---- USGS data fetcher ----------------------------------------------------------

def fetch_usgs_catalog(start_year: int, end_year: int, min_mag: float = 2.0) -> pd.DataFrame:
    """
    Fetch earthquake catalog from USGS for the Indian region.
    Uses a v2-specific cache file to avoid conflict with v1 cache.
    """
    cache_path = os.path.join(os.path.dirname(__file__), "earthquake_catalog_v2_cache.csv")

    if os.path.exists(cache_path):
        print(f"[USGS] Loading v2 cached catalog from {cache_path}")
        df = pd.read_csv(cache_path, parse_dates=["time"])
        df["time"] = pd.to_datetime(df["time"], format="mixed", utc=True)
        print(f"[USGS] Loaded {len(df)} events.")
        return df

    print(f"[USGS] Fetching catalog {start_year}-{end_year}, M>={min_mag} ...")
    all_rows = []

    for year in range(start_year, end_year + 1):
        for (s_month, e_month) in [(1, 6), (7, 12)]:
            start = f"{year}-{s_month:02d}-01"
            end   = f"{year}-12-31" if e_month == 12 else f"{year}-06-30"

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
                props  = feat.get("properties", {})
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
                  f"(total: {len(all_rows)})")
            time.sleep(0.5)

    df = pd.DataFrame(all_rows)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df.to_csv(cache_path, index=False)
    print(f"[USGS] Saved {len(df)} events -> {cache_path}")
    return df


# ---- Sample generation ----------------------------------------------------------

def build_positive_samples(catalog: pd.DataFrame) -> list[dict]:
    """
    Every M>=4.5 event -> compute features from 30d prior window. Label=1.
    Skip events in first 91 days (need 90d history for b-value).
    """
    print("\n[Samples] Building POSITIVE samples (all M>=4.5 events)...")
    sig_events = catalog[catalog["mag"] >= 4.5].copy()
    cutoff = catalog["time"].min() + timedelta(days=91)
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
        if (i + 1) % 100 == 0:
            print(f"  Positive: {i+1}/{total}  ({len(rows)} ok)")

    print(f"  Total positive samples: {len(rows)}")
    return rows


def build_negative_samples(catalog: pd.DataFrame, n_target: int, seed: int = 42) -> list[dict]:
    """
    Random (lat, lon, date) with no M>=4.5 within 100km in next 7 days. Label=0.
    Mix of high-seismicity-area jitter + fully random, for balanced spatial coverage.
    """
    print(f"\n[Samples] Building NEGATIVE samples (target: {n_target})...")
    rng = random.Random(seed)

    t_min = catalog["time"].min() + timedelta(days=91)
    t_max = catalog["time"].max() - timedelta(days=8)
    total_days = (t_max - t_min).days

    sig = catalog[catalog["mag"] >= 4.5].copy()

    high_seismicity = [
        (30.0, 79.0), (29.5, 81.0), (27.0, 88.5), (26.0, 91.5), (25.0, 93.0),
        (28.0, 95.5), (32.0, 76.0), (34.0, 74.5),
        (25.0, 92.0), (24.5, 94.5), (26.5, 93.5), (23.5, 92.5),
        (12.0, 93.0), (9.5, 92.0), (7.0, 93.5),
        (23.5, 70.5), (24.0, 69.5), (22.5, 71.0),
        (22.5, 76.0), (23.0, 80.0), (22.0, 82.0),
        (17.5, 73.8), (15.0, 76.5), (13.0, 80.0), (18.0, 83.5),
        (28.7, 77.2), (26.5, 80.5), (25.0, 85.0),
    ]

    rows = []
    attempts = 0
    max_attempts = n_target * 20

    while len(rows) < n_target and attempts < max_attempts:
        attempts += 1

        if rng.random() < 0.5 and high_seismicity:
            base_lat, base_lon = rng.choice(high_seismicity)
            lat = base_lat + rng.uniform(-2.0, 2.0)
            lon = base_lon + rng.uniform(-2.0, 2.0)
        else:
            lat = rng.uniform(LAT_MIN + 1, LAT_MAX - 1)
            lon = rng.uniform(LON_MIN + 1, LON_MAX - 1)

        lat = round(max(LAT_MIN, min(LAT_MAX, lat)), 3)
        lon = round(max(LON_MIN, min(LON_MAX, lon)), 3)

        day_offset = rng.randint(0, total_days)
        ref_date   = t_min + timedelta(days=day_offset)

        if has_significant_quake(lat, lon, ref_date, sig):
            continue

        feats = compute_features(lat, lon, ref_date, catalog)
        if feats is None:
            continue

        feats["label"] = 0
        feats["lat"]   = lat
        feats["lon"]   = lon
        feats["date"]  = ref_date.strftime("%Y-%m-%d")
        rows.append(feats)

        if len(rows) % 100 == 0:
            print(f"  Negative: {len(rows)}/{n_target}  (attempts: {attempts})")

    print(f"  Total negative samples: {len(rows)}")
    return rows


# ---- Main -----------------------------------------------------------------------

print("=" * 72)
print("Earthquake Risk ML Model v2 — JeevanSetu AI")
print("4 new seismological features: b-value, CV, acceleration, shallow-frac")
print("20-year catalog (2005-2024), M>=2.0, temporal hold-out split")
print("=" * 72)

# Step 1: Fetch / load catalog (M>=2.0, 2005-2024)
catalog = fetch_usgs_catalog(start_year=2005, end_year=2024, min_mag=2.0)
catalog["time"] = pd.to_datetime(catalog["time"], format="mixed", utc=True)
catalog = catalog.dropna(subset=["lat", "lon", "mag"])
print(f"\nCatalog: {len(catalog)} events  "
      f"| M>=4.5: {(catalog.mag>=4.5).sum()}  "
      f"| M>=2.0: {len(catalog)}")

# Step 2: Build samples
positive_rows = build_positive_samples(catalog)
n_pos = len(positive_rows)
negative_rows = build_negative_samples(catalog, n_target=int(n_pos * 1.5))

df = pd.DataFrame(positive_rows + negative_rows)
n_pos_total = int(df["label"].sum())
n_neg_total = len(df) - n_pos_total
print(f"\nDataset: {len(df)} rows  |  Positive (EQ): {n_pos_total}  |  Negative: {n_neg_total}")

_csv = os.path.join(os.path.dirname(__file__), "earthquake_dataset_v2.csv")
df.to_csv(_csv, index=False)
print(f"Saved -> {_csv}")

# Step 3: Feature matrix
X = df[EARTHQUAKE_FEATURES]
y = df["label"]
spw = round(n_neg_total / max(n_pos_total, 1), 2)
print(f"\nClass balance -> EQ: {n_pos_total}  Clear: {n_neg_total}  (scale_pos_weight={spw})")

# Step 4: Feature statistics with Cohen's d
print("\nFeature statistics (mean +/- std)  |  Cohen's d:")
print(f"  {'Feature':24s}  {'EQ (pos)':18s}  {'No EQ (neg)':18s}  d")
for feat in EARTHQUAKE_FEATURES:
    cy = df[df.label == 1][feat]
    cl = df[df.label == 0][feat]
    pooled = ((cy.std() ** 2 + cl.std() ** 2) / 2) ** 0.5
    d = abs(cy.mean() - cl.mean()) / (pooled + 1e-9)
    print(f"  {feat:24s}  {cy.mean():6.2f}+-{cy.std():.2f}   "
          f"{cl.mean():6.2f}+-{cl.std():.2f}   d={d:.2f}")

# Step 5: Ensemble model (tuned hyperparams for 12-feature space)
print("\nBuilding VotingClassifier (XGBoost + GBM + RandomForest)...")

xgb = XGBClassifier(
    n_estimators=800,
    max_depth=5,
    learning_rate=0.030,
    subsample=0.80,
    colsample_bytree=0.70,
    min_child_weight=2,
    gamma=0.10,
    reg_alpha=0.10,
    reg_lambda=1.5,
    scale_pos_weight=spw,
    eval_metric="auc",
    random_state=42,
    n_jobs=-1,
    verbosity=0,
)

gbm = GradientBoostingClassifier(
    n_estimators=600,
    learning_rate=0.035,
    max_depth=4,
    min_samples_leaf=3,
    subsample=0.85,
    max_features="sqrt",
    random_state=42,
)

rf = RandomForestClassifier(
    n_estimators=600,
    max_depth=12,
    min_samples_leaf=2,
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

# Step 6: 5-fold cross-validation on full dataset (stratified)
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

# Step 7: Temporal hold-out split (train 2005-2022, test 2023-2024)
# This is the correct way to validate earthquake models — prevents aftershock leakage
print("\n--- Temporal validation (train 2005-2022 | test 2023-2024) ---")
df["date_dt"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
split_date = pd.Timestamp("2023-01-01", tz="UTC")

train_mask = df["date_dt"] < split_date
test_mask  = df["date_dt"] >= split_date

X_tr_t = df.loc[train_mask, EARTHQUAKE_FEATURES]
y_tr_t = df.loc[train_mask, "label"]
X_te_t = df.loc[test_mask,  EARTHQUAKE_FEATURES]
y_te_t = df.loc[test_mask,  "label"]

print(f"  Train: {len(X_tr_t)} rows  |  Test: {len(X_te_t)} rows")

if len(X_te_t) > 0 and y_te_t.nunique() > 1:
    model.fit(X_tr_t, y_tr_t)
    y_pred_t  = model.predict(X_te_t)
    y_proba_t = model.predict_proba(X_te_t)[:, 1]
    temp_auc  = roc_auc_score(y_te_t, y_proba_t)
    temp_brier = brier_score_loss(y_te_t, y_proba_t)
    print(f"  Temporal ROC-AUC : {temp_auc:.3f}  ({temp_auc*100:.1f}%)")
    print(f"  Temporal Brier   : {temp_brier:.3f}")
    print(classification_report(y_te_t, y_pred_t, target_names=["No EQ", "EQ Risk"]))
else:
    print("  [WARN] Not enough 2023-2024 data for temporal eval — using random split instead.")
    temp_auc = None

# Step 8: Final model on all data + random hold-out for final metrics
print("\n--- Final model (all data, random 85/15 split) ---")
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

# Step 9: Feature importances (XGBoost)
print("Feature importances (XGBoost, gain-based):")
xgb_fitted = model.named_steps["clf"].estimators_[0]
sorted_feats = sorted(
    zip(EARTHQUAKE_FEATURES, xgb_fitted.feature_importances_),
    key=lambda x: -x[1],
)
for feat, imp in sorted_feats:
    bar = "#" * int(imp * 60)
    print(f"  {feat:24s}  {imp*100:5.1f}%  {bar}")

# Step 10: Retrain final model on ALL data before saving
print("\nRetraining final model on 100% of data...")
model.fit(X, y)

# Step 11: Save
_out = os.path.join(os.path.dirname(__file__), "earthquake_model.pkl")
joblib.dump(model, _out)
print(f"\nSaved -> {_out}")
print("=" * 72)
print(f"  CV  ROC-AUC        : {auc_mean*100:.1f}%  (+/- {auc_std*100:.1f}%)")
print(f"  Hold-out ROC-AUC   : {holdout_auc*100:.1f}%")
if temp_auc:
    print(f"  Temporal ROC-AUC   : {temp_auc*100:.1f}%  (train 2005-22, test 2023-24)")
print(f"  Features ({len(EARTHQUAKE_FEATURES)}): {EARTHQUAKE_FEATURES}")
print("=" * 72)
