from fastapi import APIRouter, Query, HTTPException
from services.weather_service import get_full_weather
from services.risk_service import calculate_risk

router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.get("")
def weather(lat: float = Query(...), lon: float = Query(...)):
    try:
        data = get_full_weather(lat, lon)
        data["risk"] = calculate_risk(data["current"])
        return data
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
