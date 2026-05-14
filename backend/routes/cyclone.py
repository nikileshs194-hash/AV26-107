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
        raise HTTPException(status_code=502, detail=f"Cyclone prediction failed: {e}")
