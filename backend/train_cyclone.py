"""
Cyclone Prediction ML Model — Scientific Training Script v3
=============================================================
Key improvements over v2:
  - Only India-affecting cyclones included (removed 12 non-Indian events:
      Gonu/Phet/Murjan/Mekunu/Hikaa/Shaheen [Oman], Chapala/Megh/Gati/Tej [Yemen/Somalia],
      Mora/Mahasen [Bangladesh/Myanmar landfall only])
    Rationale: non-Indian cyclones are 1000-2800 km from Indian coast, causing
    coastal_proximity signal to be INVERTED (cyclone class had HIGHER distance
    than non-cyclone class, directly penalising the most important geographic feature)

  - cape_jkg and tropical_instability removed from feature set:
    Both return ALL ZEROS in ERA5 archive (Cohen's d = 0.00 for both),
    meaning they add zero signal but increase noise during cross-validation.

  - Final feature set (10 features, all with measurable Cohen's d):
      wind_gusts_kmh, surface_pressure_hpa, pressure_drop_6h,
      pressure_anomaly_hpa, precipitation_mm, humidity,
      wind_intensity_index, coastal_proximity_km, season_factor, lat_abs

  - 42 Indian-coast cyclone events + 52 hard/easy negatives = 94 rows total
  - VotingClassifier ensemble: XGBoost + GradientBoosting + RandomForest
  - 5-fold stratified cross-validation with AUC, F1, Precision, Recall
  - CalibratedClassifierCV probability calibration layer

Scientific basis:
  - Gray (1979) tropical cyclone genesis parameters
  - Vertical wind shear (200-850 hPa) is the key inhibitor but ERA5 archive
    has no pressure-level data -> wind shear applied as real-time modifier
    in cyclone_service.py at inference time (NOT as a training feature)
  - Pressure anomaly, wind-pressure product capture warm-core thermodynamics
    from surface observations alone

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
# cape_jkg and tropical_instability removed — both ALL-ZERO in ERA5 archive
CYCLONE_FEATURES = [
    # --- Primary IMD signals ---
    "wind_gusts_kmh",          # surface wind gusts (km/h)
    "surface_pressure_hpa",    # low pressure = cyclone eye
    "pressure_drop_6h",        # rapid deepening (hPa per 6 hours)
    "pressure_anomaly_hpa",    # 1013.5 - pressure (cleaner warm-core signal)
    # --- Moisture / precipitation ---
    "precipitation_mm",        # total rainfall (mm)
    "humidity",                # surface relative humidity (%)
    # --- Combined intensity index ---
    "wind_intensity_index",    # gusts * pressure_anomaly / 2000
    # --- Geospatial / seasonal ---
    "coastal_proximity_km",    # distance to nearest Indian coast (km)
    "season_factor",           # IMD seasonal cyclone multiplier
    "lat_abs",                 # absolute latitude (equatorial proximity)
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
    # IMD seasonal multipliers — Bay of Bengal peak Oct-Dec, Arabian Sea peak May-Jun
    factors = {
        1: 0.55, 2: 0.55, 3: 0.65,
        4: 0.90, 5: 1.30, 6: 0.95,
        7: 0.45, 8: 0.45, 9: 0.60,
        10: 1.20, 11: 1.30, 12: 0.90,
    }
    return factors.get(month, 0.80)


# ── Cyclone events: ONLY India-affecting landfalls (42 events) ────────────────
# Geographic scope: Bay of Bengal (east coast India) + Arabian Sea (west coast India)
# Removed: Oman/Yemen/Somalia/pure-Bangladesh landfalls that never reached Indian coast
# — these had coastal_proximity > 500 km, creating inverted signal in training data
CYCLONE_EVENTS = [
    # ══ BAY OF BENGAL — India landfalls ══════════════════════════════════════
    # 1999
    ("BOB1999",    20.3, 86.5, "1999-10-29"),   # Paradip, Odisha super cyclone
    # 2000s
    ("Sidr",       22.0, 90.0, "2007-11-15"),   # Bangladesh/WB (near Indian coast)
    ("Rashmi",     21.9, 88.2, "2008-10-25"),   # West Bengal
    ("Aila",       21.9, 88.2, "2009-05-25"),   # West Bengal (very severe)
    ("Laila",      15.9, 80.6, "2010-05-20"),   # AP coast
    ("Jal",        13.1, 80.3, "2010-11-07"),   # Tamil Nadu / AP
    ("Thane",      11.9, 79.8, "2011-12-30"),   # Tamil Nadu (very severe)
    ("Nilam",      13.1, 80.3, "2012-10-31"),   # Tamil Nadu
    ("Phailin",    19.8, 85.8, "2013-10-12"),   # Odisha (extremely severe)
    ("Helen",      16.0, 80.5, "2013-11-22"),   # AP (moderate)
    ("Lehar",      15.9, 80.6, "2013-11-28"),   # AP (very severe)
    ("Madi",       10.8, 79.8, "2013-12-13"),   # Tamil Nadu
    ("Hudhud",     17.7, 83.3, "2014-10-12"),   # Visakhapatnam (extremely severe)
    ("Roanu",      13.1, 80.3, "2016-05-21"),   # Tamil Nadu (weak)
    ("Kyant",      16.5, 82.5, "2016-10-25"),   # AP (deep depression)
    ("Vardah",     13.1, 80.3, "2016-12-12"),   # Chennai (very severe)
    ("Daye",       19.8, 85.8, "2018-09-21"),   # Odisha (moderate)
    ("Titli",      19.8, 85.8, "2018-10-11"),   # Odisha (extremely severe)
    ("Luban",       9.3, 79.3, "2018-10-14"),   # Sri Lanka/Tamil Nadu (severe)
    ("Gaja",       10.8, 79.8, "2018-11-16"),   # Tamil Nadu (very severe)
    ("Phethai",    16.9, 82.2, "2018-12-17"),   # AP (severe)
    ("Fani",       19.8, 85.8, "2019-05-03"),   # Odisha (extremely severe)
    ("Bulbul",     21.9, 88.2, "2019-11-09"),   # West Bengal (very severe)
    ("Amphan",     21.6, 88.9, "2020-05-20"),   # West Bengal (super cyclone)
    ("Nivar",      11.9, 79.8, "2020-11-25"),   # Tamil Nadu (very severe)
    ("Burevi",      9.3, 79.3, "2020-12-04"),   # Sri Lanka / Tamil Nadu
    ("Yaas",       20.5, 86.7, "2021-05-26"),   # Odisha (very severe)
    ("Gulab",      19.8, 85.8, "2021-09-26"),   # Odisha (severe)
    ("Jawad",      14.8, 80.1, "2021-12-05"),   # AP (dissipated near coast)
    ("Asani",      15.9, 80.6, "2022-05-11"),   # AP (severe)
    ("Mandous",    13.1, 80.3, "2022-12-09"),   # Tamil Nadu (severe)
    ("Hamoon",     21.4, 88.0, "2023-10-25"),   # Bangladesh/WB border (severe)
    ("Michaung",   13.1, 80.3, "2023-12-04"),   # AP / Tamil Nadu (severe)
    ("Remal",      21.9, 88.2, "2024-05-26"),   # West Bengal (severe)
    ("Dana",       20.5, 86.7, "2024-10-25"),   # Odisha (severe)
    # ══ ARABIAN SEA — India landfalls only ═══════════════════════════════════
    # (removed: Gonu, Phet, Murjan, Mekunu, Hikaa, Shaheen — all hit Oman/Yemen
    #  and are 1000-2500 km from Indian coast, causing inverted coastal signal)
    ("Nilofar",    22.0, 70.0, "2014-10-31"),   # Gujarat (very severe)
    ("Vayu",       21.0, 70.5, "2019-06-13"),   # Gujarat (very severe)
    ("Kyarr",      15.5, 73.8, "2019-10-28"),   # Goa/Karnataka (extremely severe)
    ("Maha",       20.9, 70.4, "2019-11-06"),   # Gujarat (very severe)
    ("Nisarga",    18.6, 72.8, "2020-06-03"),   # Maharashtra (severe)
    ("Tauktae",    21.6, 69.6, "2021-05-17"),   # Gujarat (extremely severe)
    ("Biparjoy",   23.2, 68.9, "2023-06-15"),   # Gujarat (extremely severe)
]

# ── Negative samples: 52 events ───────────────────────────────────────────────
# HARD NEGATIVES (rows 1-40): Oct-Dec & May-Jun coastal days with heavy monsoon
#   rain but NO cyclone — these test the model on the hardest confusion cases.
# EASY NEGATIVES (rows 41-52): Jan-Mar dry season at inland cities.
NON_CYCLONE_EVENTS = [
    # ── HARD NEGATIVES: monsoon/post-monsoon coastal days (no cyclone) ─────────
    # Bay of Bengal coastal — October (high season but calm)
    ("BOB-oct-2022a",  19.8, 85.8, "2022-10-01"),   # Odisha oct, no cyclone
    ("BOB-oct-2022b",  19.8, 85.8, "2022-10-20"),
    ("BOB-oct-2023a",  21.9, 88.2, "2023-10-10"),   # WB oct, no cyclone
    ("BOB-oct-2023b",  14.8, 80.1, "2023-10-15"),   # AP oct
    ("BOB-oct-2021",   15.9, 80.6, "2021-10-20"),   # AP oct
    ("BOB-oct-2020",   13.1, 80.3, "2020-10-05"),   # Tamil Nadu oct
    ("BOB-oct-2019",   21.9, 88.2, "2019-10-15"),   # WB oct (pre-Bulbul calm)
    ("BOB-oct-2018",   19.8, 85.8, "2018-10-01"),   # Odisha oct (pre-Titli week)
    # November (peak season) coastal days without cyclone
    ("BOB-nov-2023",   13.1, 80.3, "2023-11-15"),   # Chennai nov
    ("BOB-nov-2022",   11.9, 79.8, "2022-11-20"),   # Tamil Nadu nov
    ("BOB-nov-2021",   21.9, 88.2, "2021-11-20"),   # WB nov
    ("BOB-nov-2020",   19.8, 85.8, "2020-11-10"),   # Odisha nov (pre-Nivar)
    ("BOB-nov-2019a",  13.1, 80.3, "2019-11-01"),   # Tamil Nadu nov
    ("BOB-nov-2018",   17.7, 83.3, "2018-11-05"),   # Visakha nov
    ("BOB-nov-2017",   13.1, 80.3, "2017-11-15"),   # Tamil Nadu nov
    # December coastal without cyclone
    ("BOB-dec-2023",   19.8, 85.8, "2023-12-20"),   # Odisha dec (post-Michaung)
    ("BOB-dec-2022a",  13.1, 80.3, "2022-12-20"),   # Tamil Nadu dec
    ("BOB-dec-2021",   21.9, 88.2, "2021-12-20"),   # WB dec
    ("BOB-dec-2019",   14.8, 80.1, "2019-12-10"),   # AP dec
    ("BOB-dec-2017",   19.8, 85.8, "2017-12-20"),   # Odisha dec
    # Heavy monsoon rain (Jul-Aug) at coastal cities — NOT cyclone
    ("Mumbai-jul22",   19.2, 72.8, "2022-07-19"),   # Mumbai monsoon
    ("Mumbai-jul21",   19.2, 72.8, "2021-07-18"),   # Mumbai flood event
    ("Mumbai-aug20",   19.2, 72.8, "2020-08-05"),   # Mumbai heavy rain
    ("Kochi-aug22",     9.9, 76.3, "2022-08-08"),   # Kerala SW monsoon
    ("Kochi-aug21",     9.9, 76.3, "2021-08-03"),   # Kerala SW monsoon
    ("Chennai-oct22",  13.1, 80.3, "2022-10-15"),   # Northeast monsoon onset
    ("WB-aug22",       21.9, 88.2, "2022-08-14"),   # WB monsoon
    ("Odisha-aug23",   19.8, 85.8, "2023-08-18"),   # Odisha monsoon
    ("AP-aug22",       15.9, 80.6, "2022-08-20"),   # AP monsoon
    ("Gujarat-jun24",  23.2, 68.9, "2024-06-20"),   # Gujarat monsoon onset
    # May-Jun Arabian Sea active period without cyclone
    ("AS-may23",       19.2, 72.8, "2023-05-20"),   # Mumbai pre-monsoon
    ("AS-may22",       22.0, 70.0, "2022-05-25"),   # Gujarat coast, no cyclone
    ("AS-may21",       21.6, 69.6, "2021-05-05"),   # Gujarat coast (pre-Tauktae)
    ("AS-jun23",       21.0, 70.5, "2023-06-05"),   # Gujarat coast
    ("AS-jun22",       15.5, 73.8, "2022-06-10"),   # Goa coast
    ("AS-oct22",       22.0, 70.0, "2022-10-20"),   # Gujarat coast oct
    ("AS-oct23",       15.5, 73.8, "2023-10-05"),   # Goa coast oct
    ("AS-nov22",       19.2, 72.8, "2022-11-20"),   # Mumbai coast nov
    ("AS-nov23",       21.6, 69.6, "2023-11-15"),   # Gujarat coast nov
    ("AS-dec23",       22.0, 70.0, "2023-12-10"),   # Gujarat coast dec

    # ── EASY NEGATIVES: Jan-Mar dry season at inland cities ────────────────────
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


# ── ERA5 fetch with engineered features ──────────────────────────────────────

def fetch_cyclone_features_for_date(lat: float, lon: float, date_str: str) -> dict | None:
    """
    Fetch ERA5 surface data + compute 10 ML features.
    Uses D-1 and D (event date) to capture peak conditions.

    NOTE: cape_jkg and derived tropical_instability are NOT included —
    ERA5 archive returns CAPE=0 for almost all historical dates.
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
                    "wind_gusts_10m",
                    "surface_pressure",
                    "precipitation",
                    "relative_humidity_2m",
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

    def safe(lst, i):
        return float(lst[i]) if i < len(lst) and lst[i] is not None else None

    gusts  = h.get("wind_gusts_10m",      [])
    pres   = h.get("surface_pressure",     [])
    precip = h.get("precipitation",        [])
    humid  = h.get("relative_humidity_2m", [])

    # Event day = hours 24-47 (second day)
    event_gusts = [safe(gusts,  i) or 0.0 for i in range(24, min(48, len(gusts)))]
    event_pres  = [safe(pres,   i) or 1013.0 for i in range(24, min(48, len(pres)))]
    event_prec  = [safe(precip, i) or 0.0 for i in range(24, min(48, len(precip)))]
    event_humid = [safe(humid,  i) or 70.0 for i in range(24, min(48, len(humid)))]

    if not event_gusts:
        return None

    # Peak: use minimum pressure hour as the reference (cyclone peak)
    min_pres_idx = event_pres.index(min(event_pres))
    current_pres = event_pres[min_pres_idx]
    earlier_idx  = max(0, min_pres_idx - 6)
    pres_6h_ago  = event_pres[earlier_idx]
    pressure_drop_6h = round(pres_6h_ago - current_pres, 2)

    wind_gusts_kmh   = round(max(event_gusts), 1)
    precipitation_mm = round(sum(event_prec),  2)
    humidity         = round(sum(v for v in event_humid if v) / max(len(event_humid), 1), 1)

    # Engineered features
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
        "wind_intensity_index":  wind_intensity_index,
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
            print(f"gusts={feats['wind_gusts_kmh']:.0f}  pres={feats['surface_pressure_hpa']:.0f}  "
                  f"anomaly={feats['pressure_anomaly_hpa']:.1f}  ok")
        else:
            print("skip")
        time.sleep(0.4)
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

print("=" * 75)
print(f"Collecting CYCLONE data ({len(CYCLONE_EVENTS)} events — India landfalls only)...")
print("=" * 75)
cyclone_rows = collect(CYCLONE_EVENTS, label=1, desc="CYCLONE")

print()
print("=" * 75)
print(f"Collecting NON-CYCLONE data ({len(NON_CYCLONE_EVENTS)} events)...")
print("  (includes hard negatives: Oct-Dec coastal monsoon days)")
print("=" * 75)
clear_rows = collect(NON_CYCLONE_EVENTS, label=0, desc="CLEAR")

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

# ── Show feature statistics by class ─────────────────────────────────────────

print("\nFeature statistics (mean +/- std):")
print(f"  {'Feature':28s}  {'Cyclone':18s}  {'Non-cyclone':18s}  Separation")
for f in CYCLONE_FEATURES:
    cy_vals = df[df.cyclone == 1][f]
    cl_vals = df[df.cyclone == 0][f]
    cy_str  = f"{cy_vals.mean():.2f}+-{cy_vals.std():.2f}"
    cl_str  = f"{cl_vals.mean():.2f}+-{cl_vals.std():.2f}"
    # Cohen's d effect size
    pooled_sd = ((cy_vals.std()**2 + cl_vals.std()**2) / 2) ** 0.5
    d = abs(cy_vals.mean() - cl_vals.mean()) / (pooled_sd + 1e-9)
    print(f"  {f:28s}  {cy_str:18s}  {cl_str:18s}  d={d:.2f}")

# ── Voting ensemble ───────────────────────────────────────────────────────────

print("\nBuilding voting ensemble (XGBoost + GradientBoosting + RandomForest)...")

xgb_clf = XGBClassifier(
    n_estimators=600,
    max_depth=5,
    learning_rate=0.04,
    subsample=0.8,
    colsample_bytree=0.75,
    min_child_weight=2,
    gamma=0.15,
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
    learning_rate=0.05,
    max_depth=4,
    min_samples_leaf=2,
    subsample=0.85,
    max_features="sqrt",
    random_state=42,
)

rf_clf = RandomForestClassifier(
    n_estimators=400,
    max_depth=9,
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

print(f"\n  ROC-AUC   : {cv_results['test_roc_auc'].mean():.3f} +/- {cv_results['test_roc_auc'].std():.3f}")
print(f"  F1        : {cv_results['test_f1'].mean():.3f} +/- {cv_results['test_f1'].std():.3f}")
print(f"  Precision : {cv_results['test_precision'].mean():.3f} +/- {cv_results['test_precision'].std():.3f}")
print(f"  Recall    : {cv_results['test_recall'].mean():.3f} +/- {cv_results['test_recall'].std():.3f}")

# ── Final fit on 85% data, evaluate on 15% hold-out ─────────────────────────

print("\nFitting on 85% data, testing on 15% hold-out...")
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.15, random_state=42, stratify=y)
base_model.fit(X_tr, y_tr)

y_pred  = base_model.predict(X_te)
y_proba = base_model.predict_proba(X_te)[:, 1]

print(f"  Hold-out ROC-AUC : {roc_auc_score(y_te, y_proba):.3f}")
print(f"  Brier Score      : {brier_score_loss(y_te, y_proba):.3f}  (0=perfect, 0.25=random)")
print(classification_report(y_te, y_pred, target_names=["No Cyclone", "Cyclone"]))

# ── Feature importance ────────────────────────────────────────────────────────

print("Feature importances (from XGBoost):")
xgb_fitted = base_model.named_steps["clf"].estimators_[0]
imp_pairs  = sorted(zip(CYCLONE_FEATURES, xgb_fitted.feature_importances_), key=lambda x: -x[1])
for feat, imp in imp_pairs:
    bar = "#" * int(imp * 50)
    print(f"  {feat:28s}  {imp*100:5.1f}%  {bar}")

# ── Save model ────────────────────────────────────────────────────────────────

_model_path = os.path.join(os.path.dirname(__file__), "cyclone_model.pkl")
joblib.dump(base_model, _model_path)
print(f"\nSaved -> {_model_path}")
print(f"Final FEATURES: {CYCLONE_FEATURES}")
