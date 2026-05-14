from fastapi import APIRouter, Query, HTTPException
from services.weather_service import get_full_weather
from services.risk_service import calculate_risk
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.get("")
def weather(lat: float = Query(...), lon: float = Query(...)):
    try:
        data = get_full_weather(lat, lon)
        try:
            data["risk"] = calculate_risk(data["current"])
        except Exception as re:
            logger.warning(f"[Weather] risk calculation failed: {re}")
            data["risk"] = {
                "risk_level": "Low", "risk_color": "#4CAF50",
                "gauge_position": 0.2, "be_prepared": False,
                "breakdown": [],
            }
        return data
    except Exception as e:
        logger.error(f"[Weather] endpoint error lat={lat} lon={lon}: {e}")
        raise HTTPException(status_code=502, detail=f"Weather service error: {e}")
