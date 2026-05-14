"""
Cyclone Prediction ML Model — Training Script
================================================
Historical documented Indian Ocean tropical-cyclone landfalls (2007-2024)
vs. clear-weather control days at the same coastal locations.

Features (must match cyclone_service.py CYCLONE_FEATURES exactly):
  wind_gusts_kmh, surface_pressure_hpa, pressure_drop_6h,
  cape_jkg, precipitation_mm, humidity,
  coastal_proximity_km, season_factor, lat_abs

Model: VotingClassifier (XGBoost + GradientBoosting + RandomForest)
       with 5-fold stratified cross-validation.

Run:  python train_cyclone.py
      → saves  backend/cyclone_model.pkl
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

# ── Feature list (must match cyclone_service.py CYCLONE_FEATURES exactly) ─────
CYCLONE_FEATURES = [
    "wind_gusts_kmh",        # primary IMD cyclone trigger
    "surface_pressure_hpa",  # low pressure = cyclone eye
    "pressure_drop_6h",      # rapid deepening signal
    "cape_jkg",              # convective instability (J/kg)
    "precipitation_mm",      # associated rainfall
    "humidity",              # atmospheric moisture content
    "coastal_proximity_km",  # coastal = higher risk
    "season_factor",         # IMD seasonal cyclone multiplier
    "lat_abs",               # equatorial proximity (lower = more prone)
]

# ── Indian coastline reference points for coastal distance ────────────────────
_COAST_PTS = [
    (23.2, 68.9), (21.6, 69.6), (20.9, 70.4), (19.2, 72.8),
    (15.5, 73.8), (14.8, 74.1), (12.9, 74.8), (11.2, 75.8),
    (10.0, 76.2), (8.5,  77.0), (8.1,  77.5),
    (9.3,  79.3), (10.8, 79.8), (11.9, 79.8), (13.1, 80.3),
    (14.8, 80.1), (15.9, 80.6), (16.9, 82.2), (17.7, 83.3),
    (19.8, 85.8), (20.5, 86.7), (21.4, 87.2), (21.9, 88.2),
    (21.6, 88.9),
]


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _coast_distance_km(lat, lon):
    return min(_haversine_km(lat, lon, cp[0], cp[1]) for cp in _COAST_PTS)


def _season_factor(month):
    factors = {
        1: 0.55, 2: 0.55, 3: 0.65,
        4: 0.90, 5: 1.30, 6: 0.95,
        7: 0.45, 8: 0.45, 9: 0.60,
        10: 1.20, 11: 1.30, 12: 0.90,
    }
    return factors.get(month, 0.80)


# ── Documented Indian Ocean cyclone landfalls (positive samples) ──────────────
# Format: (name, lat, lon, "YYYY-MM-DD", imd_category)
# lat/lon = nearest Indian coastal city / landfall point
CYCLONE_EVENTS = [
    # Bay of Bengal — east coast
    ("Sidr",       22.0,  90.0, "2007-11-15"),   # Bangladesh
    ("Aila",       21.9,  88.2, "2009-05-25"),   # West Bengal
    ("Jal",        13.1,  80.3, "2010-11-07"),   # Tamil Nadu / AP
    ("Thane",      11.9,  79.8, "2011-12-30"),   # Tamil Nadu
    ("Phailin",    19.8,  85.8, "2013-10-12"),   # Odisha
    ("Helen",      16.0,  80.5, "2013-11-22"),   # AP
    ("Lehar",      15.9,  80.6, "2013-11-28"),   # AP
    ("Hudhud",     17.7,  83.3, "2014-10-12"),   # Visakhapatnam
    ("Vardah",     13.1,  80.3, "2016-12-12"),   # Chennai
    ("Mora",       21.9,  88.2, "2017-05-30"),   # Bangladesh
    ("Ockhi",       8.5,  77.0, "2017-12-01"),   # Kerala / Tamil Nadu
    ("Titli",      19.8,  85.8, "2018-10-11"),   # Odisha
    ("Gaja",       10.8,  79.8, "2018-11-16"),   # Tamil Nadu
    ("Fani",       19.8,  85.8, "2019-05-03"),   # Odisha (Very Severe)
    ("Bulbul",     21.9,  88.2, "2019-11-09"),   # West Bengal
    ("Amphan",     21.6,  88.9, "2020-05-20"),   # West Bengal (Super)
    ("Nivar",      11.9,  79.8, "2020-11-25"),   # Tamil Nadu
    ("Burevi",      9.3,  79.3, "2020-12-04"),   # Sri Lanka / Tamil Nadu
    ("Yaas",       20.5,  86.7, "2021-05-26"),   # Odisha
    ("Gulab",      19.8,  85.8, "2021-09-26"),   # Odisha
    ("Jawad",      14.8,  80.1, "2021-12-05"),   # AP
    ("Asani",      15.9,  80.6, "2022-05-11"),   # AP
    ("Mandous",    13.1,  80.3, "2022-12-09"),   # Tamil Nadu
    ("Michaung",   13.1,  80.3, "2023-12-04"),   # AP / Tamil Nadu
    ("Remal",      21.9,  88.2, "2024-05-26"),   # West Bengal
    ("Dana",       20.5,  86.7, "2024-10-25"),   # Odisha

    # Arabian Sea — west coast
    ("Gonu",       23.5,  57.5, "2007-06-06"),   # Oman (nearest)
    ("Phet",       22.8,  59.5, "2010-06-01"),   # Oman / Gujarat
    ("Nilofar",    22.0,  70.0, "2014-10-31"),   # Gujarat
    ("Chapala",    12.8,  45.0, "2015-11-01"),   # Yemen
    ("Megh",       12.8,  45.0, "2015-11-09"),   # Yemen
    ("Ockhi-AS",    8.5,  77.0, "2017-12-02"),   # Kerala (secondary track)
    ("Vayu",       21.0,  70.5, "2019-06-13"),   # Gujarat
    ("Kyarr",      15.5,  73.8, "2019-10-28"),   # Goa area
    ("Maha",       20.9,  70.4, "2019-11-06"),   # Gujarat
    ("Tauktae",    21.6,  69.6, "2021-05-17"),   # Gujarat
    ("Shaheen",    23.5,  58.0, "2021-10-03"),   # Oman
    ("Biparjoy",   23.2,  68.9, "2023-06-15"),   # Gujarat
]

# ── Non-cyclone control events (negative samples) ─────────────────────────────
# Clear dry-season days at the same coastal locations
NON_CYCLONE_EVENTS = [
    # East coast — clear days (Jan-Mar, non-cyclone months)
    ("Chennai-dry1",   13.1, 80.3, "2024-02-15"),
    ("Chennai-dry2",   13.1, 80.3, "2023-01-20"),
    ("Chennai-dry3",   13.1, 80.3, "2022-03-10"),
    ("Chennai-dry4",   13.1, 80.3, "2021-02-05"),
    ("Chennai-dry5",   13.1, 80.3, "2020-03-20"),
    ("Chennai-dry6",   13.1, 80.3, "2019-01-10"),
    ("Chennai-dry7",   13.1, 80.3, "2018-02-25"),
    ("Chennai-dry8",   13.1, 80.3, "2017-03-15"),
    ("Odisha-dry1",    19.8, 85.8, "2024-01-25"),
    ("Odisha-dry2",    19.8, 85.8, "2023-02-20"),
    ("Odisha-dry3",    19.8, 85.8, "2022-03-15"),
    ("Odisha-dry4",    19.8, 85.8, "2021-01-30"),
    ("Odisha-dry5",    19.8, 85.8, "2020-02-28"),
    ("Odisha-dry6",    19.8, 85.8, "2019-03-10"),
    ("Odisha-dry7",    19.8, 85.8, "2018-01-20"),
    ("Visakha-dry1",   17.7, 83.3, "2024-02-10"),
    ("Visakha-dry2",   17.7, 83.3, "2023-03-05"),
    ("Visakha-dry3",   17.7, 83.3, "2022-01-15"),
    ("Visakha-dry4",   17.7, 83.3, "2021-02-20"),
    ("Visakha-dry5",   17.7, 83.3, "2020-03-12"),
    ("WB-dry1",        21.9, 88.2, "2024-01-15"),
    ("WB-dry2",        21.9, 88.2, "2023-02-10"),
    ("WB-dry3",        21.9, 88.2, "2022-03-20"),
    ("WB-dry4",        21.9, 88.2, "2021-01-25"),
    ("WB-dry5",        21.9, 88.2, "2020-02-15"),
    ("WB-dry6",        21.9, 88.2, "2019-03-05"),
    ("AP-dry1",        15.9, 80.6, "2024-02-20"),
    ("AP-dry2",        15.9, 80.6, "2023-01-15"),
    ("AP-dry3",        15.9, 80.6, "2022-02-28"),
    ("AP-dry4",        15.9, 80.6, "2021-03-10"),
    ("Kerala-dry1",     8.5, 77.0, "2024-02-05"),
    ("Kerala-dry2",     8.5, 77.0, "2023-01-20"),
    ("Kerala-dry3",     8.5, 77.0, "2022-03-15"),
    ("Kerala-dry4",     8.5, 77.0, "2021-02-10"),
    # West coast — clear days
    ("Gujarat-dry1",   23.2, 68.9, "2024-01-20"),
    ("Gujarat-dry2",   23.2, 68.9, "2023-02-15"),
    ("Gujarat-dry3",   23.2, 68.9, "2022-03-10"),
    ("Gujarat-dry4",   23.2, 68.9, "2021-01-28"),
    ("Gujarat-dry5",   23.2, 68.9, "2020-02-20"),
    ("Gujarat-dry6",   23.2, 68.9, "2019-03-08"),
    ("Gujarat-dry7",   23.2, 68.9, "2018-01-15"),
    ("Goa-dry1",       15.5, 73.8, "2024-02-25"),
    ("Goa-dry2",       15.5, 73.8, "2023-01-10"),
    ("Goa-dry3",       15.5, 73.8, "2022-02-20"),
    ("Goa-dry4",       15.5, 73.8, "2021-03-05"),
    ("Mangaluru-dry1", 12.9, 74.8, "2024-01-15"),
    ("Mangaluru-dry2", 12.9, 74.8, "2023-02-25"),
    ("Mangaluru-dry3", 12.9, 74.8, "2022-01-10"),
    # Deep inland cities (low cyclone risk by definition)
    ("Delhi-dry1",     28.6, 77.2, "2024-06-01"),
    ("Delhi-dry2",     28.6, 77.2, "2023-05-15"),
    ("Delhi-dry3",     28.6, 77.2, "2022-04-20"),
    ("Delhi-dry4",     28.6, 77.2, "2021-05-10"),
    ("Jaipur-dry1",    26.9, 75.8, "2024-05-20"),
    ("Jaipur-dry2",    26.9, 75.8, "2023-06-10"),
    ("Jaipur-dry3",    26.9, 75.8, "2022-05-05"),
    ("Nagpur-dry1",    21.1, 79.1, "2024-03-25"),
    ("Nagpur-dry2",    21.1, 79.1, "2023-04-10"),
    ("Hyderabad-dry1", 17.4, 78.5, "2024-04-15"),
    ("Hyderabad-dry2", 17.4, 78.5, "2023-03-20"),
    ("Bengaluru-dry1", 13.0, 77.6, "2024-01-30"),
    ("Bengaluru-dry2", 13.0, 77.6, "2023-02-18"),
    ("Bengaluru-dry3", 13.0, 77.6, "2022-04-10"),
]


# ── ERA5 historical fetch for cyclone features ────────────────────────────────

def fetch_cyclone_features_for_date(lat: float, lon: float, date_str: str) -> dict | None:
    """
    Fetch ERA5 hourly data for D-1 and D (event date).
    Returns cyclone-relevant features using peak conditions from:
      - hours 18-23 of D-1  (pre-event)
      - hours  0-23 of D    (event day, peak conditions)
    """
    d0     = datetime.strptime(date_str, "%Y-%m-%d")
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
                    "wind_gusts_10m",
                    "surface_pressure",
                    "cape",
                    "precipitation",
                    "relative_humidity_2m",
                    "temperature_2m",
                ],
                "wind_speed_unit": "kmh",
                "timezone":   "auto",
            },
            timeout=25,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[WARN] ERA5 error {lat},{lon} {date_str}: {e}")
        return None

    hourly = data.get("hourly", {})
    gusts  = hourly.get("wind_gusts_10m",       [])
    pres   = hourly.get("surface_pressure",      [])
    cape   = hourly.get("cape",                  [])
    precip = hourly.get("precipitation",         [])
    humid  = hourly.get("relative_humidity_2m",  [])

    def safe(lst, i):
        return float(lst[i]) if i < len(lst) and lst[i] is not None else None

    # Event day = hours 24-47 (second day of the 2-day fetch)
    # Pre-event 6h = hours 18-23 of D-1

    # Peak wind gusts on event day (hours 0-23 = indices 24-47)
    event_gusts = [safe(gusts, i) or 0.0 for i in range(24, min(48, len(gusts)))]
    event_pres  = [safe(pres,  i) or 1013.0 for i in range(24, min(48, len(pres)))]
    event_cape  = [safe(cape,  i) or 0.0 for i in range(24, min(48, len(cape)))]
    event_prec  = [safe(precip, i) or 0.0 for i in range(24, min(48, len(precip)))]
    event_humid = [safe(humid, i) or 70.0 for i in range(24, min(48, len(humid)))]

    if not event_gusts:
        return None

    # Pre-event pressure (6h before peak = 6 hours earlier on event day)
    # Use minimum pressure on the event day as the reference (cyclone peak)
    min_pres_idx = event_pres.index(min(event_pres))
    current_pres = event_pres[min_pres_idx]

    # Pressure 6h earlier
    earlier_idx  = max(0, min_pres_idx - 6)
    pres_6h_ago  = event_pres[earlier_idx] if event_pres else current_pres
    pressure_drop_6h = round(pres_6h_ago - current_pres, 2)  # positive = drop = deepening

    # Peak values on event day
    wind_gusts_kmh     = round(max(event_gusts), 1)
    cape_jkg           = round(max(event_cape),  1)
    precipitation_mm   = round(sum(event_prec),  2)
    humidity           = round(
        sum(v for v in event_humid if v) / max(len(event_humid), 1), 1
    )

    # Geospatial features
    coast_km      = round(_coast_distance_km(lat, lon), 1)
    month         = d0.month
    season_f      = _season_factor(month)
    lat_abs       = round(abs(lat), 2)

    return {
        "wind_gusts_kmh":        wind_gusts_kmh,
        "surface_pressure_hpa":  round(current_pres, 1),
        "pressure_drop_6h":      pressure_drop_6h,
        "cape_jkg":              cape_jkg,
        "precipitation_mm":      precipitation_mm,
        "humidity":              humidity,
        "coastal_proximity_km":  coast_km,
        "season_factor":         season_f,
        "lat_abs":               lat_abs,
    }


# ── Collect dataset ───────────────────────────────────────────────────────────

def collect(events: list, label: int, desc: str) -> list:
    rows = []
    total = len(events)
    for i, (name, lat, lon, date) in enumerate(events):
        print(f"  [{i+1:3d}/{total}] {desc:8s}  {name:20s}  {date} ...", end=" ", flush=True)
        feats = fetch_cyclone_features_for_date(lat, lon, date)
        if feats:
            feats["cyclone"] = label
            feats["name"]    = name
            rows.append(feats)
            print(f"gusts={feats['wind_gusts_kmh']:.0f}km/h  pres={feats['surface_pressure_hpa']:.0f}hPa  ok")
        else:
            print("skip")
        time.sleep(0.5)
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

print("=" * 70)
print(f"Collecting CYCLONE weather data ({len(CYCLONE_EVENTS)} events)...")
print("=" * 70)
cyclone_rows = collect(CYCLONE_EVENTS, label=1, desc="CYCLONE")

print()
print("=" * 70)
print(f"Collecting CLEAR weather data ({len(NON_CYCLONE_EVENTS)} events)...")
print("=" * 70)
clear_rows = collect(NON_CYCLONE_EVENTS, label=0, desc="CLEAR")

df = pd.DataFrame(cyclone_rows + clear_rows)
n_cyc  = int(df["cyclone"].sum())
n_clr  = len(df) - n_cyc
print(f"\nDataset: {len(df)} rows  |  Cyclone: {n_cyc}  |  Clear: {n_clr}")

_csv = os.path.join(os.path.dirname(__file__), "cyclone_dataset_real.csv")
df.to_csv(_csv, index=False)
print(f"Saved → {_csv}")

# ── Feature matrix ────────────────────────────────────────────────────────────

X = df[CYCLONE_FEATURES]
y = df["cyclone"]

spw = round(n_clr / max(n_cyc, 1), 2)
print(f"\nClass balance  →  cyclone: {n_cyc}  clear: {n_clr}  (scale_pos_weight={spw})")

# ── Voting ensemble: XGBoost + GBM + RandomForest ────────────────────────────

print("\nBuilding voting ensemble (XGBoost + GradientBoosting + RandomForest)...")

xgb_clf = XGBClassifier(
    n_estimators=400,
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
    n_estimators=300,
    learning_rate=0.06,
    max_depth=4,
    min_samples_leaf=2,
    subsample=0.85,
    max_features="sqrt",
    random_state=42,
)

rf_clf = RandomForestClassifier(
    n_estimators=250,
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
print(classification_report(y_te, y_pred, target_names=["No Cyclone", "Cyclone"]))

# ── Feature importance (from XGBoost inside ensemble) ────────────────────────

print("Feature importances (from XGBoost):")
xgb_fitted = model.named_steps["clf"].estimators_[0]
for feat, imp in sorted(
    zip(CYCLONE_FEATURES, xgb_fitted.feature_importances_),
    key=lambda x: -x[1],
):
    bar = "#" * int(imp * 50)
    print(f"  {feat:25s}  {imp:.3f}  {bar}")

# ── Save model ────────────────────────────────────────────────────────────────

_model_path = os.path.join(os.path.dirname(__file__), "cyclone_model.pkl")
joblib.dump(model, _model_path)
print(f"\nSaved → {_model_path}")
print("The cyclone_service.py will auto-load this model on next startup.")
