"""
Cyclone Prediction ML Model — Scientific Training Script v4
=============================================================
Key improvements over v3:
  - Multi-day collection: each cyclone event contributes 2 training rows
    (D-1 and D = approach day + landfall day).  This doubles the effective
    positive-class dataset from 42 to ~84 rows without any new data source.
    Scientific rationale: a cyclone 24 h before landfall already shows
    depressed pressure, elevated gusts and heavy precip — all valid cyclone
    signatures the model should recognise.

  - Added temperature_2m as warm-ocean proxy (11th feature).
    Cyclones form and intensify only over SST > 26 °C.  Surface air temp
    correlates well with SST over the Indian Ocean.
    Cohen's d expected: ~1.2  (cyclone coastal tropics 28-32 °C vs.
    inland dry-season negatives 12-20 °C).

  - Hyperparameters re-tuned for the larger, denser dataset:
    less aggressive regularisation (gamma 0.15->0.08, reg_lambda 1.5->1.0)
    to avoid under-fitting on the expanded positive class.

  - Expected accuracy: ROC-AUC 88-93 % (was 82 %)

Dataset: 42 India cyclone events × 2 days = ~84 positive rows
         52 non-cyclone hard/easy negatives
         Total: ~136 rows (was 94)

Feature set (11 features — must match cyclone_service.py CYCLONE_FEATURES):
  wind_gusts_kmh, surface_pressure_hpa, pressure_drop_6h,
  pressure_anomaly_hpa, precipitation_mm, humidity, temperature_2m,
  wind_intensity_index, coastal_proximity_km, season_factor, lat_abs

Run: python train_cyclone.py
     -> saves  backend/cyclone_model.pkl
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
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.metrics import classification_report, roc_auc_score, brier_score_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

# ── Feature list (must match cyclone_service.py CYCLONE_FEATURES exactly) ─────
CYCLONE_FEATURES = [
    # --- Primary IMD signals ---
    "wind_gusts_kmh",          # surface wind gusts (km/h)
    "surface_pressure_hpa",    # low pressure = cyclone eye
    "pressure_drop_6h",        # rapid deepening (hPa per 6 hours)
    "pressure_anomaly_hpa",    # 1013.5 - pressure (warm-core signal)
    # --- Moisture / precipitation / thermal ---
    "precipitation_mm",        # total rainfall (mm)
    "humidity",                # surface relative humidity (%)
    "temperature_2m",          # surface air temp as warm-ocean proxy (°C)
    # --- Combined intensity index ---
    "wind_intensity_index",    # gusts * pressure_anomaly / 2000
    # --- Geospatial / seasonal ---
    "coastal_proximity_km",    # distance to nearest Indian coast (km)
    "season_factor",           # IMD seasonal cyclone multiplier
    "lat_abs",                 # absolute latitude (equatorial proximity)
]

# ── Indian coastline reference points ─────────────────────────────────────────
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


# ── Cyclone events: ONLY India-affecting landfalls (42 events) ────────────────
CYCLONE_EVENTS = [
    # ══ BAY OF BENGAL ══
    ("BOB1999",    20.3, 86.5, "1999-10-29"),
    ("Sidr",       22.0, 90.0, "2007-11-15"),
    ("Rashmi",     21.9, 88.2, "2008-10-25"),
    ("Aila",       21.9, 88.2, "2009-05-25"),
    ("Laila",      15.9, 80.6, "2010-05-20"),
    ("Jal",        13.1, 80.3, "2010-11-07"),
    ("Thane",      11.9, 79.8, "2011-12-30"),
    ("Nilam",      13.1, 80.3, "2012-10-31"),
    ("Phailin",    19.8, 85.8, "2013-10-12"),
    ("Helen",      16.0, 80.5, "2013-11-22"),
    ("Lehar",      15.9, 80.6, "2013-11-28"),
    ("Madi",       10.8, 79.8, "2013-12-13"),
    ("Hudhud",     17.7, 83.3, "2014-10-12"),
    ("Roanu",      13.1, 80.3, "2016-05-21"),
    ("Kyant",      16.5, 82.5, "2016-10-25"),
    ("Vardah",     13.1, 80.3, "2016-12-12"),
    ("Daye",       19.8, 85.8, "2018-09-21"),
    ("Titli",      19.8, 85.8, "2018-10-11"),
    ("Luban",       9.3, 79.3, "2018-10-14"),
    ("Gaja",       10.8, 79.8, "2018-11-16"),
    ("Phethai",    16.9, 82.2, "2018-12-17"),
    ("Fani",       19.8, 85.8, "2019-05-03"),
    ("Bulbul",     21.9, 88.2, "2019-11-09"),
    ("Amphan",     21.6, 88.9, "2020-05-20"),
    ("Nivar",      11.9, 79.8, "2020-11-25"),
    ("Burevi",      9.3, 79.3, "2020-12-04"),
    ("Yaas",       20.5, 86.7, "2021-05-26"),
    ("Gulab",      19.8, 85.8, "2021-09-26"),
    ("Jawad",      14.8, 80.1, "2021-12-05"),
    ("Asani",      15.9, 80.6, "2022-05-11"),
    ("Mandous",    13.1, 80.3, "2022-12-09"),
    ("Hamoon",     21.4, 88.0, "2023-10-25"),
    ("Michaung",   13.1, 80.3, "2023-12-04"),
    ("Remal",      21.9, 88.2, "2024-05-26"),
    ("Dana",       20.5, 86.7, "2024-10-25"),
    # ══ ARABIAN SEA (India-hitting only) ══
    ("Nilofar",    22.0, 70.0, "2014-10-31"),
    ("Vayu",       21.0, 70.5, "2019-06-13"),
    ("Kyarr",      15.5, 73.8, "2019-10-28"),
    ("Maha",       20.9, 70.4, "2019-11-06"),
    ("Nisarga",    18.6, 72.8, "2020-06-03"),
    ("Tauktae",    21.6, 69.6, "2021-05-17"),
    ("Biparjoy",   23.2, 68.9, "2023-06-15"),
]

# ── Negative samples (52 events) ──────────────────────────────────────────────
NON_CYCLONE_EVENTS = [
    # Hard negatives: Oct-Dec coastal monsoon days, no cyclone
    ("BOB-oct-2022a",  19.8, 85.8, "2022-10-01"),
    ("BOB-oct-2022b",  19.8, 85.8, "2022-10-20"),
    ("BOB-oct-2023a",  21.9, 88.2, "2023-10-10"),
    ("BOB-oct-2023b",  14.8, 80.1, "2023-10-15"),
    ("BOB-oct-2021",   15.9, 80.6, "2021-10-20"),
    ("BOB-oct-2020",   13.1, 80.3, "2020-10-05"),
    ("BOB-oct-2019",   21.9, 88.2, "2019-10-15"),
    ("BOB-oct-2018",   19.8, 85.8, "2018-10-01"),
    ("BOB-nov-2023",   13.1, 80.3, "2023-11-15"),
    ("BOB-nov-2022",   11.9, 79.8, "2022-11-20"),
    ("BOB-nov-2021",   21.9, 88.2, "2021-11-20"),
    ("BOB-nov-2020",   19.8, 85.8, "2020-11-10"),
    ("BOB-nov-2019a",  13.1, 80.3, "2019-11-01"),
    ("BOB-nov-2018",   17.7, 83.3, "2018-11-05"),
    ("BOB-nov-2017",   13.1, 80.3, "2017-11-15"),
    ("BOB-dec-2023",   19.8, 85.8, "2023-12-20"),
    ("BOB-dec-2022a",  13.1, 80.3, "2022-12-20"),
    ("BOB-dec-2021",   21.9, 88.2, "2021-12-20"),
    ("BOB-dec-2019",   14.8, 80.1, "2019-12-10"),
    ("BOB-dec-2017",   19.8, 85.8, "2017-12-20"),
    ("Mumbai-jul22",   19.2, 72.8, "2022-07-19"),
    ("Mumbai-jul21",   19.2, 72.8, "2021-07-18"),
    ("Mumbai-aug20",   19.2, 72.8, "2020-08-05"),
    ("Kochi-aug22",     9.9, 76.3, "2022-08-08"),
    ("Kochi-aug21",     9.9, 76.3, "2021-08-03"),
    ("Chennai-oct22",  13.1, 80.3, "2022-10-15"),
    ("WB-aug22",       21.9, 88.2, "2022-08-14"),
    ("Odisha-aug23",   19.8, 85.8, "2023-08-18"),
    ("AP-aug22",       15.9, 80.6, "2022-08-20"),
    ("Gujarat-jun24",  23.2, 68.9, "2024-06-20"),
    ("AS-may23",       19.2, 72.8, "2023-05-20"),
    ("AS-may22",       22.0, 70.0, "2022-05-25"),
    ("AS-may21",       21.6, 69.6, "2021-05-05"),
    ("AS-jun23",       21.0, 70.5, "2023-06-05"),
    ("AS-jun22",       15.5, 73.8, "2022-06-10"),
    ("AS-oct22",       22.0, 70.0, "2022-10-20"),
    ("AS-oct23",       15.5, 73.8, "2023-10-05"),
    ("AS-nov22",       19.2, 72.8, "2022-11-20"),
    ("AS-nov23",       21.6, 69.6, "2023-11-15"),
    ("AS-dec23",       22.0, 70.0, "2023-12-10"),
    # Easy negatives: inland dry season
    ("Delhi-dry1",     28.6, 77.2, "2024-01-05"),
    ("Delhi-dry2",     28.6, 77.2, "2023-04-20"),
    ("Jaipur-dry1",    26.9, 75.8, "2024-05-20"),
    ("Nagpur-dry1",    21.1, 79.1, "2024-03-25"),
    ("Hyderabad-dry1", 17.4, 78.5, "2024-04-15"),
    ("Bengaluru-dry1", 13.0, 77.6, "2024-01-30"),
    ("Bengaluru-dry2", 13.0, 77.6, "2023-02-18"),
    ("Lucknow-dry1",   26.8, 80.9, "2024-02-10"),
    ("Pune-dry1",      18.5, 73.9, "2024-01-20"),
    ("Chandigarh-dry1",30.7, 76.8, "2024-02-25"),
    ("Indore-dry1",    22.7, 75.9, "2024-04-10"),
    ("Indore-dry2",    22.7, 75.9, "2023-05-20"),
]


# ── ERA5 fetch (11 features including temperature_2m) ────────────────────────

def fetch_cyclone_features_for_date(lat: float, lon: float, date_str: str) -> dict | None:
    """
    Fetch ERA5 surface data for D-1 and D (48-hour window ending on date_str).
    Returns 11 ML features.  Uses minimum-pressure hour as the cyclone peak.
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
                    "precipitation",
                    "relative_humidity_2m",
                    "temperature_2m",       # NEW: warm-ocean proxy
                ],
                "wind_speed_unit": "kmh",
                "timezone":   "auto",
            },
            timeout=28,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[WARN] ERA5 {lat},{lon} {date_str}: {e}")
        return None

    h = data.get("hourly", {})

    def safe(lst, i, default=0.0):
        return float(lst[i]) if i < len(lst) and lst[i] is not None else default

    gusts  = h.get("wind_gusts_10m",      [])
    pres   = h.get("surface_pressure",     [])
    precip = h.get("precipitation",        [])
    humid  = h.get("relative_humidity_2m", [])
    temp   = h.get("temperature_2m",       [])

    # Event day = hours 24-47 (second day in the 48-h window)
    event_gusts = [safe(gusts,  i, 0.0)    for i in range(24, min(48, len(gusts)))]
    event_pres  = [safe(pres,   i, 1013.0) for i in range(24, min(48, len(pres)))]
    event_prec  = [safe(precip, i, 0.0)    for i in range(24, min(48, len(precip)))]
    event_humid = [safe(humid,  i, 70.0)   for i in range(24, min(48, len(humid)))]
    event_temp  = [safe(temp,   i, 28.0)   for i in range(24, min(48, len(temp)))]

    if not event_gusts:
        return None

    # Use minimum-pressure hour as the reference (cyclone peak signature)
    min_pres_idx = event_pres.index(min(event_pres))
    current_pres = event_pres[min_pres_idx]
    earlier_idx  = max(0, min_pres_idx - 6)
    pres_6h_ago  = event_pres[earlier_idx]
    pressure_drop_6h = round(pres_6h_ago - current_pres, 2)

    wind_gusts_kmh   = round(max(event_gusts), 1)
    precipitation_mm = round(sum(event_prec), 2)
    humidity         = round(sum(event_humid) / max(len(event_humid), 1), 1)
    temperature_2m   = round(sum(event_temp)  / max(len(event_temp),  1), 1)

    pressure_anomaly_hpa = round(1013.5 - current_pres, 2)
    wind_intensity_index = round(wind_gusts_kmh * max(pressure_anomaly_hpa, 0) / 2000, 5)

    coast_km = round(_coast_distance_km(lat, lon), 1)
    month    = d0.month
    season_f = _season_factor(month)
    lat_abs  = round(abs(lat), 2)

    return {
        "wind_gusts_kmh":        wind_gusts_kmh,
        "surface_pressure_hpa":  round(current_pres, 1),
        "pressure_drop_6h":      pressure_drop_6h,
        "pressure_anomaly_hpa":  pressure_anomaly_hpa,
        "precipitation_mm":      precipitation_mm,
        "humidity":              humidity,
        "temperature_2m":        temperature_2m,
        "wind_intensity_index":  wind_intensity_index,
        "coastal_proximity_km":  coast_km,
        "season_factor":         season_f,
        "lat_abs":               lat_abs,
    }


# ── Collect helpers ───────────────────────────────────────────────────────────

def collect_single(events: list, label: int, desc: str) -> list:
    """Collect one row per event (used for non-cyclone negatives)."""
    rows = []
    total = len(events)
    for i, (name, lat, lon, date) in enumerate(events):
        print(f"  [{i+1:3d}/{total}] {desc:8s}  {name:22s}  {date} ...", end=" ", flush=True)
        feats = fetch_cyclone_features_for_date(lat, lon, date)
        if feats:
            feats["cyclone"] = label
            feats["name"]    = name
            rows.append(feats)
            print(f"gusts={feats['wind_gusts_kmh']:.0f}  pres={feats['surface_pressure_hpa']:.0f}  "
                  f"temp={feats['temperature_2m']:.1f}C  ok")
        else:
            print("skip")
        time.sleep(0.4)
    return rows


def collect_multiday(events: list, label: int, desc: str, days_before: int = 1) -> list:
    """
    Collect multiple rows per cyclone event: landfall day + N approach days.

    For each event with landfall date D:
      - Fetch D   (peak cyclone day)
      - Fetch D-1 (approach day — cyclone already showing strong signature)

    This doubles the positive-class training data from 42 to ~84 rows
    without requiring any new data sources.
    Scientific basis: a cyclone 24h before landfall has depressed pressure,
    elevated gusts, and heavy precipitation — all valid positive signatures.
    """
    rows = []
    total = len(events)
    for i, (name, lat, lon, landfall_date) in enumerate(events):
        d0 = datetime.strptime(landfall_date, "%Y-%m-%d")
        for offset in range(days_before, -1, -1):   # e.g. [1, 0] for days_before=1
            fetch_date = (d0 - timedelta(days=offset)).strftime("%Y-%m-%d")
            tag        = f"D-{offset}" if offset > 0 else "D"
            row_name   = f"{name}_{tag}"
            print(f"  [{i+1:3d}/{total}] {desc:8s}  {row_name:26s}  {fetch_date} ...", end=" ", flush=True)
            feats = fetch_cyclone_features_for_date(lat, lon, fetch_date)
            if feats:
                feats["cyclone"] = label
                feats["name"]    = row_name
                rows.append(feats)
                print(f"gusts={feats['wind_gusts_kmh']:.0f}  pres={feats['surface_pressure_hpa']:.0f}  "
                      f"temp={feats['temperature_2m']:.1f}C  ok")
            else:
                print("skip")
            time.sleep(0.4)
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

print("=" * 78)
print(f"Collecting CYCLONE data  ({len(CYCLONE_EVENTS)} events x 2 days = ~{len(CYCLONE_EVENTS)*2} rows)...")
print("  Multi-day: landfall day (D) + approach day (D-1)")
print("=" * 78)
cyclone_rows = collect_multiday(CYCLONE_EVENTS, label=1, desc="CYCLONE", days_before=1)

print()
print("=" * 78)
print(f"Collecting NON-CYCLONE data  ({len(NON_CYCLONE_EVENTS)} events, single day each)...")
print("  Includes 40 hard negatives: Oct-Dec coastal monsoon days")
print("=" * 78)
clear_rows = collect_single(NON_CYCLONE_EVENTS, label=0, desc="CLEAR")

df = pd.DataFrame(cyclone_rows + clear_rows)
n_cyc = int(df["cyclone"].sum())
n_clr = len(df) - n_cyc
print(f"\nDataset: {len(df)} rows  |  Cyclone: {n_cyc}  |  Non-cyclone: {n_clr}")

_csv = os.path.join(os.path.dirname(__file__), "cyclone_dataset_real.csv")
df.to_csv(_csv, index=False)
print(f"Saved -> {_csv}")

# ── Feature matrix ────────────────────────────────────────────────────────────

X = df[CYCLONE_FEATURES]
y = df["cyclone"]
spw = round(n_clr / max(n_cyc, 1), 2)
print(f"\nClass balance  ->  cyclone:{n_cyc}  clear:{n_clr}  (scale_pos_weight={spw})")

# ── Feature statistics with Cohen's d ────────────────────────────────────────

print("\nFeature statistics (mean +/- std)  |  Cohen d = separation power:")
print(f"  {'Feature':28s}  {'Cyclone':18s}  {'Non-cyclone':18s}  d")
for feat in CYCLONE_FEATURES:
    cy = df[df.cyclone == 1][feat]
    cl = df[df.cyclone == 0][feat]
    pooled = ((cy.std()**2 + cl.std()**2) / 2) ** 0.5
    d = abs(cy.mean() - cl.mean()) / (pooled + 1e-9)
    flag = " <-- NEW" if feat == "temperature_2m" else ""
    print(f"  {feat:28s}  {cy.mean():.2f}+-{cy.std():.2f}   "
          f"{cl.mean():.2f}+-{cl.std():.2f}   d={d:.2f}{flag}")

# ── Voting ensemble — tuned for expanded dataset ──────────────────────────────

print("\nBuilding voting ensemble (XGBoost + GradientBoosting + RandomForest)...")

xgb_clf = XGBClassifier(
    n_estimators=700,
    max_depth=5,
    learning_rate=0.035,
    subsample=0.82,
    colsample_bytree=0.78,
    min_child_weight=2,
    gamma=0.08,           # reduced from 0.15 — less pruning on larger dataset
    reg_alpha=0.08,
    reg_lambda=1.0,       # reduced from 1.5 — larger dataset needs less L2
    scale_pos_weight=spw,
    eval_metric="auc",
    random_state=42,
    n_jobs=-1,
    verbosity=0,
)

gbm_clf = GradientBoostingClassifier(
    n_estimators=500,
    learning_rate=0.04,
    max_depth=4,
    min_samples_leaf=2,
    subsample=0.85,
    max_features="sqrt",
    random_state=42,
)

rf_clf = RandomForestClassifier(
    n_estimators=500,
    max_depth=10,
    min_samples_leaf=2,
    class_weight="balanced",
    random_state=42,
    n_jobs=-1,
)

base_model = Pipeline([
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
    base_model, X, y, cv=cv,
    scoring=["roc_auc", "f1", "precision", "recall"],
    n_jobs=1,
)

auc_mean = cv_results['test_roc_auc'].mean()
auc_std  = cv_results['test_roc_auc'].std()
f1_mean  = cv_results['test_f1'].mean()

print(f"\n  ROC-AUC   : {auc_mean:.3f} +/- {auc_std:.3f}   ({auc_mean*100:.1f}%)")
print(f"  F1        : {cv_results['test_f1'].mean():.3f} +/- {cv_results['test_f1'].std():.3f}")
print(f"  Precision : {cv_results['test_precision'].mean():.3f} +/- {cv_results['test_precision'].std():.3f}")
print(f"  Recall    : {cv_results['test_recall'].mean():.3f} +/- {cv_results['test_recall'].std():.3f}")

# ── Hold-out evaluation ───────────────────────────────────────────────────────

print("\nFitting on 85% data, testing on 15% hold-out...")
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.15, random_state=42, stratify=y)
base_model.fit(X_tr, y_tr)

y_pred  = base_model.predict(X_te)
y_proba = base_model.predict_proba(X_te)[:, 1]
holdout_auc = roc_auc_score(y_te, y_proba)
brier      = brier_score_loss(y_te, y_proba)

print(f"  Hold-out ROC-AUC : {holdout_auc:.3f}  ({holdout_auc*100:.1f}%)")
print(f"  Brier Score      : {brier:.3f}  (0=perfect, 0.25=random)")
print(classification_report(y_te, y_pred, target_names=["No Cyclone", "Cyclone"]))

# ── Feature importance ────────────────────────────────────────────────────────

print("Feature importances (XGBoost):")
xgb_fitted = base_model.named_steps["clf"].estimators_[0]
imp_pairs  = sorted(zip(CYCLONE_FEATURES, xgb_fitted.feature_importances_), key=lambda x: -x[1])
for feat, imp in imp_pairs:
    bar = "#" * int(imp * 60)
    print(f"  {feat:28s}  {imp*100:5.1f}%  {bar}")

# ── Save ──────────────────────────────────────────────────────────────────────

_model_path = os.path.join(os.path.dirname(__file__), "cyclone_model.pkl")
joblib.dump(base_model, _model_path)
print(f"\nSaved -> {_model_path}")
print(f"CV ROC-AUC  : {auc_mean*100:.1f}%  (+/- {auc_std*100:.1f}%)")
print(f"Hold-out AUC: {holdout_auc*100:.1f}%")
print(f"Final FEATURES ({len(CYCLONE_FEATURES)}): {CYCLONE_FEATURES}")
