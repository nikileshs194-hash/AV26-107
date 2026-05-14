from fastapi import APIRouter, Query
from services.earthquake_service import predict_earthquake

router = APIRouter(prefix="/api/earthquake", tags=["earthquake"])


@router.get("")
def earthquake_prediction(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
):
    """
    Real-time earthquake risk prediction for a given location.

    Uses:
      - USGS Earthquake Catalog (live, last 90 days, M>=2.0, 200km radius)
      - Aki (1965) MLE b-value — tectonic stress indicator
      - Inter-event time CV — seismic clustering / quiescence detector
      - Seismic acceleration ratio — foreshock swarm detection
      - India BIS 1893 seismic zone + fault proximity
      - VotingClassifier ML model (XGBoost + GBM + RF, 12 features)
        CV ROC-AUC 90.7% | Temporal AUC 88.0%

    Returns risk_level, probability, seismic zone, all 12 features, and safety advice.
    Predicts probability of M>=4.5 within 100 km in the next 7 days.
    """
    try:
        result = predict_earthquake(lat, lon)
        return result
    except Exception as e:
        print(f"[Earthquake] Prediction failed, returning fallback: {e}")
        zone = max(2, min(5, 3))  # default Zone III
        return {
            "earthquake_risk":  "Unknown",
            "probability":      0.0,
            "probability_pct":  "0.0%",
            "risk_high":        False,
            "forecast_window":  "Next 7 days",
            "target_radius_km": 100,
            "seismic_zone":     "Unknown",
            "features": {
                "recent_quakes_7d":    0,
                "recent_quakes_30d":   0,
                "max_mag_7d":          0.0,
                "max_mag_30d":         0.0,
                "energy_index_30d":    0.0,
                "b_value":             0.85,
                "cv_interevent":       1.0,
                "quake_acceleration":  1.0,
                "depth_avg_30d":       35.0,
                "depth_shallow_frac":  0.5,
                "dist_to_fault_km":    0.0,
                "seismic_zone":        3,
                "seismic_zone_label":  "Unknown",
                "total_events_bbox":   0,
            },
            "advice":           ["Real-time seismic data temporarily unavailable. Please try again shortly."],
            "ml_model_active":  False,
            "data_sources":     ["Unavailable"],
        }
