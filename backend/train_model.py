"""
Urban Flood Prediction Model — Training Script
Run: python train_model.py
Trains on synthetic data calibrated to Indian city flood patterns,
saves model.pkl for use by the FastAPI predict endpoint.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
import joblib

np.random.seed(42)
N = 15000  # samples

# ── Feature generation ──────────────────────────────────────────────────────

rainfall_1h   = np.random.exponential(4, N).clip(0, 120)          # mm
rainfall_24h  = (rainfall_1h * np.random.uniform(3, 8, N)
                 + np.random.exponential(15, N)).clip(0, 500)      # mm
humidity      = np.random.normal(72, 14, N).clip(30, 100)          # %
temperature   = np.random.normal(28, 7, N).clip(10, 45)            # °C
elevation     = np.random.exponential(120, N).clip(0, 1500)        # m above sea level
soil_moisture = np.clip(
    np.random.uniform(0.1, 0.9, N) + rainfall_24h / 600,
    0, 1,
)                                                                   # 0–1
drainage      = np.random.normal(5, 2, N).clip(0, 10)              # quality 0–10
slope         = np.random.exponential(3, N).clip(0, 45)            # degrees
pressure      = np.random.normal(1005, 10, N).clip(960, 1030)      # hPa

df = pd.DataFrame({
    "rainfall_1h":   rainfall_1h,
    "rainfall_24h":  rainfall_24h,
    "humidity":      humidity,
    "temperature":   temperature,
    "elevation":     elevation,
    "soil_moisture": soil_moisture,
    "drainage":      drainage,
    "slope":         slope,
    "pressure":      pressure,
})

# ── Label generation (domain-calibrated) ────────────────────────────────────

def flood_score(row):
    s = 0.0

    # Rainfall 1h — most immediate trigger
    if   row.rainfall_1h > 40:  s += 5.0
    elif row.rainfall_1h > 25:  s += 3.5
    elif row.rainfall_1h > 15:  s += 2.0
    elif row.rainfall_1h > 7:   s += 1.0

    # Rainfall 24h — antecedent saturation
    if   row.rainfall_24h > 200: s += 5.0
    elif row.rainfall_24h > 100: s += 3.5
    elif row.rainfall_24h > 50:  s += 2.0
    elif row.rainfall_24h > 20:  s += 1.0

    # Humidity — atmosphere already saturated
    if   row.humidity > 92: s += 2.0
    elif row.humidity > 85: s += 1.0

    # Elevation — low-lying areas flood first
    if   row.elevation < 15:  s += 3.5
    elif row.elevation < 40:  s += 2.5
    elif row.elevation < 80:  s += 1.5
    elif row.elevation < 150: s += 0.5

    # Soil moisture — saturated soil can't absorb
    if   row.soil_moisture > 0.85: s += 2.5
    elif row.soil_moisture > 0.70: s += 1.5
    elif row.soil_moisture > 0.55: s += 0.5

    # Drainage — poor drainage traps water
    if   row.drainage < 2: s += 3.0
    elif row.drainage < 4: s += 2.0
    elif row.drainage < 6: s += 1.0

    # Slope — flat terrain can't drain
    if   row.slope < 0.5: s += 2.0
    elif row.slope < 2:   s += 1.0

    # Low pressure — storm system present
    if row.pressure < 990: s += 1.5
    elif row.pressure < 1000: s += 0.5

    s += np.random.normal(0, 0.8)   # realistic noise
    return s

df["score"] = df.apply(flood_score, axis=1)
df["flood"] = (df["score"] >= 8.5).astype(int)   # threshold tuned for ~25% flood rate

print(f"Samples: {N}  |  Flood rate: {df['flood'].mean():.1%}")

# ── Train / test split ───────────────────────────────────────────────────────

FEATURES = ["rainfall_1h", "rainfall_24h", "humidity", "temperature",
            "elevation", "soil_moisture", "drainage", "slope", "pressure"]

X = df[FEATURES]
y = df["flood"]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

# ── Model ───────────────────────────────────────────────────────────────────

model = Pipeline([
    ("scaler", StandardScaler()),
    ("clf", GradientBoostingClassifier(
        n_estimators=300,
        learning_rate=0.08,
        max_depth=5,
        min_samples_leaf=20,
        subsample=0.8,
        random_state=42,
    )),
])

model.fit(X_train, y_train)

# ── Evaluate ─────────────────────────────────────────────────────────────────

y_pred = model.predict(X_test)
print(f"\nTest accuracy: {accuracy_score(y_test, y_pred):.3f}")
print(classification_report(y_test, y_pred, target_names=["No Flood", "Flood"]))

# Feature importance (from the GBM inside the pipeline)
importances = model.named_steps["clf"].feature_importances_
for feat, imp in sorted(zip(FEATURES, importances), key=lambda x: -x[1]):
    print(f"  {feat:20s}  {imp:.3f}")

# ── Save ─────────────────────────────────────────────────────────────────────

joblib.dump(model, "model.pkl")
print("\nSaved → model.pkl")
