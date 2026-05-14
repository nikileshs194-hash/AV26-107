from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import List
from services.alert_service import get_alerts
from services.supabase_service import _get_service_client

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class AlertSaveRequest(BaseModel):
    phone: str
    alerts: List[dict]


@router.get("")
def alerts(lat: float = Query(...), lon: float = Query(...)):
    try:
        return get_alerts(lat, lon)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/save")
def save_alerts(req: AlertSaveRequest):
    """Save fetched alerts to DB for this user (upsert by phone+alert_id)."""
    db = _get_service_client()
    if not db:
        return {"success": False, "message": "DB not available"}
    try:
        for a in req.alerts:
            row = {
                "phone":        req.phone,
                "alert_id":     a.get("id", ""),
                "title":        a.get("title", ""),
                "description":  a.get("desc", ""),
                "severity":     a.get("severity", "Minor"),
                "source":       a.get("source", ""),
                "location":     a.get("location", ""),
                "icon":         a.get("icon", ""),
                "icon_bg":      a.get("iconBg", ""),
                "icon_color":   a.get("iconColor", ""),
                "border_color": a.get("borderColor", ""),
                "when_text":    a.get("when", ""),
                "when_color":   a.get("whenColor", ""),
            }
            db.table("user_alerts").upsert(row, on_conflict="phone,alert_id").execute()
        return {"success": True, "saved": len(req.alerts)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/saved")
def get_saved_alerts(phone: str = Query(...)):
    """Get all saved alerts for a user from DB."""
    db = _get_service_client()
    if not db:
        return {"alerts": []}
    try:
        try:
            res = (
                db.table("user_alerts")
                .select("*")
                .eq("phone", phone)
                .order("created_at", desc=True)
                .execute()
            )
        except Exception:
            res = db.table("user_alerts").select("*").eq("phone", phone).execute()
        # Map DB rows back to AlertItem format
        alerts = []
        for row in (res.data or []):
            alerts.append({
                "id":          row.get("alert_id", row.get("id", "")),
                "db_id":       row.get("id", ""),
                "title":       row.get("title", ""),
                "desc":        row.get("description", ""),
                "severity":    row.get("severity", "Minor"),
                "source":      row.get("source", ""),
                "location":    row.get("location", ""),
                "icon":        row.get("icon", "warning-outline"),
                "iconBg":      row.get("icon_bg", "#FFF3E0"),
                "iconColor":   row.get("icon_color", "#FB8C00"),
                "borderColor": row.get("border_color", "#FB8C00"),
                "when":        row.get("when_text", ""),
                "whenColor":   row.get("when_color", "#FB8C00"),
                "time":        row.get("created_at", "")[:16] if row.get("created_at") else "Just now",
            })
        return {"alerts": alerts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clear")
def clear_alert(phone: str = Query(...), db_id: str = Query(None)):
    """Clear one alert (db_id given) or all alerts for the user."""
    db = _get_service_client()
    if not db:
        raise HTTPException(status_code=503, detail="DB not available")
    try:
        if db_id:
            db.table("user_alerts").delete().eq("id", db_id).eq("phone", phone).execute()
        else:
            db.table("user_alerts").delete().eq("phone", phone).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
