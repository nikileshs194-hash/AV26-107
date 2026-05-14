import pandas as pd
from xgboost import XGBClassifier
import joblib

# Load dataset
df = pd.read_csv("dataset.csv")

# Convert columns to numeric
df["rainfall"] = pd.to_numeric(df["rainfall"])
df["humidity"] = pd.to_numeric(df["humidity"])
df["drainage"] = pd.to_numeric(df["drainage"])
df["elevation"] = pd.to_numeric(df["elevation"])
df["flood"] = pd.to_numeric(df["flood"])

# Features and target
X = df[["rainfall", "humidity", "drainage", "elevation"]]
y = df["flood"]

# Train model
model = XGBClassifier()
model.fit(X, y)

# Save model
joblib.dump(model, "model.pkl")

print("Model Trained Successfully")