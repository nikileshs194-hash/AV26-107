import os
import joblib

_model = None


def _load_model():
    global _model
    if _model is None:
        path = os.path.join(os.path.dirname(__file__), "..", "model.pkl")
        try:
            _model = joblib.load(path)
        except Exception:
            _model = None
    return _model


def _level(score: float) -> str:
    if score >= 0.75: return "High"
    if score >= 0.45: return "Moderate"
    return "Low"


def _color(level: str) -> str:
    return {"High": "#F44336", "Moderate": "#FF9800", "Low": "#4CAF50"}.get(level, "#FF9800")


def calculate_risk(current: dict, historical: dict = None) -> dict:
    rainfall = current.get("rain_1h", 0)
    humidity = current.get("humidity", 60)
    saturation = (historical or {}).get("saturation_index", 0.0)
    total_7d = (historical or {}).get("total_7d", 0.0)

    drainage = max(1, 10 - min(rainfall * 2, 9))
    elevation = 50
    score = 0.0

    model = _load_model()
    if model:
        try:
            import pandas as pd
            df = pd.DataFrame([{
                "rainfall": rainfall, "humidity": humidity,
                "drainage": drainage, "elevation": elevation,
            }])
            if hasattr(model, "predict_proba"):
                prob = model.predict_proba(df)[0]
                score = float(prob[1]) if len(prob) > 1 else float(prob[0])
            else:
                score = float(model.predict(df)[0])
        except Exception:
            score = _heuristic(rainfall, humidity, current)
    else:
        score = _heuristic(rainfall, humidity, current)

    # Boost score based on historical soil saturation (NASA POWER data)
    # Saturated soil (saturation_index > 0) means water has nowhere to go
    score = min(score + saturation * 0.25, 1.0)

    # Additional boost if 7-day rainfall is extreme (> 100 mm)
    if total_7d > 100:
        score = min(score + 0.15, 1.0)
    elif total_7d > 50:
        score = min(score + 0.08, 1.0)

    overall = _level(score)
    condition = current.get("condition", "Clear").lower()  # WMO label e.g. "Rain", "Thunderstorm"

    rain_level = "High" if rainfall > 15 else ("Moderate" if rainfall > 3 or humidity > 85 else "Low")
    thunder_level = "High" if "thunderstorm" in condition else ("Moderate" if any(w in condition for w in ("rain", "drizzle", "shower")) else "Low")

    # Soil saturation level based on NASA historical data
    sat_level = "High" if saturation > 0.5 else ("Moderate" if saturation > 0.1 else "Low")

    return {
        "risk_score": round(score, 3),
        "risk_level": overall,
        "risk_color": _color(overall),
        "gauge_position": {"Low": 0.2, "Moderate": 0.55, "High": 0.85}.get(overall, 0.55),
        "be_prepared": overall != "Low",
        "breakdown": [
            {"label": "Heavy Rain", "icon": "water-outline", "level": rain_level, "color": _color(rain_level)},
            {"label": "Thunderstorm", "icon": "thunderstorm-outline", "level": thunder_level, "color": _color(thunder_level)},
            {"label": "Soil Saturation", "icon": "layers-outline", "level": sat_level, "color": _color(sat_level)},
            {"label": "Flood Risk", "icon": "home-outline", "level": overall, "color": _color(overall)},
        ],
    }


def _heuristic(rainfall: float, humidity: float, weather: dict) -> float:
    score = min(rainfall / 30.0, 0.4)
    score += (humidity - 50) / 100.0 * 0.3 if humidity > 50 else 0
    cond = weather.get("condition", "").lower()
    if "thunderstorm" in cond: score += 0.3
    elif any(w in cond for w in ("rain", "drizzle", "shower")): score += 0.2
    return min(score, 1.0)
