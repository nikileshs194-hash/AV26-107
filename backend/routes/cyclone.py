from fastapi import APIRouter, HTTPException, Query
from services.cyclone_service import predict_cyclone

router = APIRouter(prefix="/api/cyclone", tags=["cyclone"])


@router.get("")
def cyclone_prediction(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
):
    """
    Real-time cyclone risk prediction for a given location.

    Uses:
      - Open-Meteo live wind, gusts, pressure, CAPE (+ 6-hour pressure trend)
      - GDACS RSS for active global tropical cyclone events
      - IMD meteorological thresholds for risk scoring
      - Indian coastline proximity and seasonal multipliers

    Returns risk_level, probability, IMD category, key features, and safety advice.
    """
    try:
        result = predict_cyclone(lat, lon)
        return result
    except Exception as e:
        # Return a safe degraded response instead of 502.
        # A 502 breaks the mobile UI; a 200 with "Very Low" risk lets the app
        # render normally while showing data-unavailable advice.
        print(f"[Cyclone] Prediction failed, returning fallback: {e}")
        return {
            "cyclone_risk":    "Unknown",
            "probability":     0.0,
            "category":        "No Data",
            "cyclone_likely":  False,
            "features": {
                "wind_speed_kmh": 0, "wind_gusts_kmh": 0,
                "surface_pressure_hpa": 1013, "pressure_6h_ago_hpa": 1013,
                "pressure_drop_6h": 0, "pressure_anomaly_hpa": 0,
                "cape_jkg": 0, "precipitation_mm": 0, "humidity": 0,
                "temperature_2m": 28, "tropical_instability": 0,
                "wind_intensity_index": 0, "wind_shear_kmh": 0,
                "humidity_500hpa": 50, "coastal_proximity_km": 0,
                "season_factor": 1.0, "lat_abs": abs(lat),
                "gdacs_active": False, "gdacs_name": "",
                "gdacs_distance_km": 9999, "gdacs_alert_level": "",
            },
            "advice": ["Real-time atmospheric data temporarily unavailable. Please try again shortly."],
            "data_sources":    ["Unavailable"],
            "forecast_window": "Current conditions + 6-hour trend",
            "ml_model_active": False,
        }
