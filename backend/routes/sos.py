"""
Emergency SOS Routes
POST /api/sos                  — fire SOS (stores alert, notifies nearby, rescue team)
POST /api/sos/notify-nearby    — "Call Nearby People"
GET  /api/sos/dashboard        — rescue-team live dashboard (beautiful HTML)
GET  /api/sos/dashboard/data   — JSON feed
POST /api/sos/push-token       — store Expo push token
PUT  /api/sos/{id}/resolve     — mark resolved
GET  /api/sos/shelters         — nearby shelters
"""

import math
import requests as _req
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from services.supabase_service import _get_service_client, _haversine

router = APIRouter(prefix="/api/sos", tags=["emergency"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reverse_geocode(lat: float, lon: float) -> str:
    try:
        r = _req.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json"},
            headers={"User-Agent": "FloodAISystem/1.0"},
            timeout=8,
        )
        d = r.json()
        addr = d.get("address", {})
        parts = [
            addr.get("road") or addr.get("pedestrian") or addr.get("neighbourhood"),
            addr.get("suburb") or addr.get("town") or addr.get("village"),
            addr.get("city") or addr.get("county"),
            addr.get("state"),
        ]
        return ", ".join(p for p in parts if p) or d.get("display_name", "Unknown location")
    except Exception:
        return f"{round(lat, 4)}, {round(lon, 4)}"


def _send_expo_push(notifications: list) -> int:
    if not notifications:
        print("[PUSH] No notifications to send")
        return 0
    try:
        print(f"[PUSH] Sending {len(notifications)} notification(s)...")
        for n in notifications:
            print(f"[PUSH]  → to={n.get('to')} body={n.get('body','')[:60]}")

        resp = _req.post(
            "https://exp.host/--/api/v2/push/send",
            json=notifications,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=12,
        )
        result = resp.json()
        print(f"[PUSH] Expo response: {result}")

        # Count only successful ones
        sent = 0
        data = result.get("data", [])
        if isinstance(data, list):
            for item in data:
                if item.get("status") == "ok":
                    sent += 1
                else:
                    print(f"[PUSH] ❌ Error: {item}")
        else:
            sent = len(notifications)
        return sent
    except Exception as e:
        print(f"[PUSH] Exception: {e}")
        return 0


def _normalise_phone(phone: str) -> str:
    """Strip everything except digits, then strip leading country-code prefix (91)
    so '+919353124446', '919353124446', '9353124446' all compare equal."""
    digits = ''.join(c for c in (phone or '') if c.isdigit())
    # If it looks like an Indian number with country code (12 digits starting with 91)
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    return digits


def _find_nearby_users(lat: float, lon: float, exclude_phone: str, radius_m: int = 2000) -> list:
    db = _get_service_client()
    if not db:
        return []
    try:
        # full_name is the correct column (not name)
        res = db.table("users").select("full_name, phone, push_token, latitude, longitude").execute()
        nearby = []
        exclude_norm = _normalise_phone(exclude_phone)
        for u in (res.data or []):
            if not u.get("latitude") or not u.get("longitude"):
                continue
            # Exclude the caller — compare normalised digits so +91/91 prefix mismatches don't break it
            if _normalise_phone(u.get("phone", "")) == exclude_norm:
                continue
            dist_m = _haversine(lat, lon, u["latitude"], u["longitude"]) * 1000
            if dist_m <= radius_m:
                nearby.append({
                    "name":       u.get("full_name") or u.get("phone", "Nearby User"),
                    "phone":      u.get("phone"),
                    "push_token": u.get("push_token"),
                    "distance_m": round(dist_m),
                })
        return sorted(nearby, key=lambda x: x["distance_m"])
    except Exception as e:
        print(f"[NEARBY] {e}")
        return []


# ── Request models ────────────────────────────────────────────────────────────

class SOSRequest(BaseModel):
    phone: str
    name: str = "Unknown"
    age: int | None = None
    lat: float
    lon: float
    message: str = "In Danger"
    severity: str = "High"

class NotifyNearbyRequest(BaseModel):
    phone: str
    name: str
    lat: float
    lon: float
    radius_m: int = 2000

class PushTokenRequest(BaseModel):
    phone: str
    push_token: str


# ── SOS endpoints ─────────────────────────────────────────────────────────────

@router.post("")
def send_sos(req: SOSRequest):
    address         = _reverse_geocode(req.lat, req.lon)
    google_maps_url = f"https://maps.google.com/?q={req.lat},{req.lon}"
    db              = _get_service_client()
    sos_id          = None
    is_duplicate    = False

    if db:
        try:
            # ── Deduplication: if this phone already has an active SOS, ──────
            # update the location (they may have moved) but don't create a new row.
            existing = (
                db.table("sos_requests")
                .select("id")
                .eq("phone", req.phone)
                .eq("status", "active")
                .limit(1)
                .execute()
            )
            if existing.data:
                sos_id       = existing.data[0]["id"]
                is_duplicate = True
                # Refresh location + address in case they moved
                db.table("sos_requests").update({
                    "latitude":        req.lat,
                    "longitude":       req.lon,
                    "address":         address,
                    "google_maps_url": google_maps_url,
                    "severity":        req.message,
                }).eq("id", sos_id).execute()
                print(f"[SOS] Duplicate SOS for {req.phone} — updated existing {sos_id}")
            else:
                # Fresh SOS — insert a new row
                row = {
                    "phone":           req.phone,
                    "name":            req.name,
                    "latitude":        req.lat,
                    "longitude":       req.lon,
                    "address":         address,
                    "google_maps_url": google_maps_url,
                    "severity":        req.message,   # "In Danger" / "Stranded" / "Injured"
                    "status":          "active",
                }
                if req.age:
                    row["age"] = req.age
                res    = db.table("sos_requests").insert(row).execute()
                sos_id = res.data[0]["id"] if res.data else None
        except Exception as e:
            print(f"[SOS DB] {e}")

    # SOS only alerts the rescue team dashboard — no push to nearby people.
    # "Call Nearby People" is the separate button for peer notifications.
    return {
        "success":        True,
        "sos_id":         str(sos_id) if sos_id else "local",
        "address":        address,
        "google_maps_url": google_maps_url,
        "notified_count": 0,
        "duplicate":      is_duplicate,
        "message": (
            "SOS already active. Location updated on rescue dashboard."
            if is_duplicate else
            "SOS sent. Rescue team has been alerted."
        ),
    }


@router.post("/notify-nearby")
def notify_nearby(req: NotifyNearbyRequest):
    address         = _reverse_geocode(req.lat, req.lon)
    google_maps_url = f"https://maps.google.com/?q={req.lat},{req.lon}"
    nearby          = _find_nearby_users(req.lat, req.lon, req.phone, req.radius_m)

    # Fetch the sender's own push token so we can hard-exclude it from pushes
    # (double safety on top of the phone-based filter in _find_nearby_users)
    sender_token = None
    sender_norm  = _normalise_phone(req.phone)
    db = _get_service_client()
    if db:
        try:
            rows = db.table("users").select("push_token").execute().data or []
            for row in rows:
                if _normalise_phone(row.get("phone", "")) == sender_norm:
                    sender_token = row.get("push_token")
                    break
        except Exception as e:
            print(f"[NEARBY] Could not fetch sender token: {e}")

    print(f"[NEARBY] sender={req.phone!r}  sender_token={str(sender_token)[:30] if sender_token else None}")
    print(f"[NEARBY] found {len(nearby)} nearby user(s) after phone exclusion")

    # Send push notification to every nearby user that has a token
    pushes = []
    for u in nearby:
        if not u.get("push_token"):
            continue
        # Skip sender by push token (belt-and-suspenders over phone filter)
        if sender_token and u["push_token"] == sender_token:
            print(f"[NEARBY] Skipping {u.get('name')} — same push token as sender")
            continue
        dist_m   = u["distance_m"]
        dist_str = f"{round(dist_m / 1000, 1)} km" if dist_m >= 1000 else f"{dist_m} m"
        print(f"[NEARBY] Notifying {u.get('name')} at {dist_str}")
        pushes.append({
            "to":        u["push_token"],
            "title":     "🚨 EMERGENCY — Someone needs help nearby!",
            "body":      f"{req.name} needs urgent help — {dist_str} from you",
            "sound":     "default",
            "priority":  "high",
            "badge":     1,
            "channelId": "sos",          # ← routes to MAX-importance channel on Android
            "data": {
                "type":            "sos_alert",
                "sos_id":          "",
                "victim_name":     req.name,
                "victim_phone":    req.phone,
                "victim_lat":      req.lat,
                "victim_lon":      req.lon,
                "address":         address,
                "distance_m":      dist_m,
                "google_maps_url": google_maps_url,
            },
        })
    notified = _send_expo_push(pushes)

    # nearest is the closest person regardless of whether they have push token
    nearest = nearby[0] if nearby else None

    dist_str = None
    if nearest:
        dm = nearest["distance_m"]
        dist_str = f"{round(dm / 1000, 1)} km" if dm >= 1000 else f"{dm} m"

    return {
        "success":        True,
        "notified_count": notified,
        "nearest_phone":  nearest["phone"]      if nearest else None,
        "nearest_name":   nearest["name"]       if nearest else None,
        "nearest_dist_m": nearest["distance_m"] if nearest else None,
        "nearest_dist_str": dist_str,
        "nearby_users": [
            {"name": u["name"], "distance_m": u["distance_m"]} for u in nearby[:5]
        ],
    }


@router.post("/push-token")
def save_push_token(req: PushTokenRequest):
    db = _get_service_client()
    if not db:
        return {"success": False}
    try:
        db.table("users").update({"push_token": req.push_token}).eq("phone", req.phone).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/users")
def debug_users():
    """Debug endpoint — shows which users have push tokens and location saved."""
    db = _get_service_client()
    if not db:
        return {"error": "DB not available"}
    try:
        res = db.table("users").select("full_name, phone, push_token, latitude, longitude").execute()
        users = []
        for u in (res.data or []):
            users.append({
                "name":       u.get("full_name") or "—",
                "phone":      u.get("phone"),
                "has_token":  bool(u.get("push_token")),
                "token_preview": (u.get("push_token") or "")[:30] + "..." if u.get("push_token") else None,
                "has_location": bool(u.get("latitude") and u.get("longitude")),
                "lat": u.get("latitude"),
                "lon": u.get("longitude"),
            })
        return {
            "total_users": len(users),
            "with_token": sum(1 for u in users if u["has_token"]),
            "with_location": sum(1 for u in users if u["has_location"]),
            "users": users,
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/find-nearest")
def find_nearest(phone: str, lat: float, lon: float, radius_m: int = 5000):
    """
    Find the single nearest registered user to (lat, lon).
    Used by 'Call Nearby People' — returns phone + name so the app can dial directly.
    radius_m default is 5 km (wider than notify-nearby so someone is always found).
    """
    nearby = _find_nearby_users(lat, lon, phone, radius_m)
    if not nearby:
        # Try wider radius — 20 km fallback
        nearby = _find_nearby_users(lat, lon, phone, 20000)

    if not nearby:
        return {
            "found": False,
            "message": "No registered users found near your location.",
            "nearest": None,
        }

    nearest = nearby[0]
    dist_m  = nearest["distance_m"]
    dist_str = f"{round(dist_m / 1000, 1)} km" if dist_m >= 1000 else f"{dist_m} m"

    return {
        "found":   True,
        "nearest": {
            "name":      nearest["name"],
            "phone":     nearest["phone"],
            "distance_m": dist_m,
            "distance_str": dist_str,
        },
        "total_nearby": len(nearby),
    }


@router.get("/dashboard/data")
def dashboard_data():
    db = _get_service_client()
    if not db:
        return {"alerts": []}
    try:
        # Only return active alerts — resolved ones are excluded at the source
        try:
            res = (
                db.table("sos_requests")
                .select("*")
                .eq("status", "active")
                .order("created_at", desc=True)
                .limit(100)
                .execute()
            )
        except Exception:
            # Fallback: no ordering (created_at column may not exist yet)
            res = (
                db.table("sos_requests")
                .select("*")
                .eq("status", "active")
                .limit(100)
                .execute()
            )
        return {"alerts": res.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{sos_id}/resolve")
def resolve_sos(sos_id: str):
    db = _get_service_client()
    if not db:
        raise HTTPException(status_code=503, detail="DB not available")
    try:
        db.table("sos_requests").delete().eq("id", sos_id).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/shelters")
def shelters(lat: float, lon: float, radius_km: float = 20):
    from services.supabase_service import get_nearby_shelters
    try:
        return {"shelters": get_nearby_shelters(lat, lon, radius_km)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Test / Debug endpoints ────────────────────────────────────────────────────

@router.post("/test-flood-alert")
def test_flood_alert(phone: str):
    """
    DEV ONLY — fires a real flood_alert push notification to the given phone
    immediately, using their saved location and nearest shelter.
    Use this to verify the FloodAlertModal works end-to-end.

    Example:
        POST /api/sos/test-flood-alert?phone=+91XXXXXXXXXX
    """
    db = _get_service_client()
    if not db:
        raise HTTPException(status_code=503, detail="DB not available")

    # Fetch user
    try:
        res  = db.table("users").select("full_name,push_token,latitude,longitude").eq("phone", phone).execute()
        user = (res.data or [None])[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not user:
        raise HTTPException(status_code=404, detail=f"User with phone {phone} not found")
    if not user.get("push_token"):
        raise HTTPException(status_code=400, detail="User has no push token — open the app (dev build) first")
    if not user.get("latitude") or not user.get("longitude"):
        raise HTTPException(status_code=400, detail="User has no saved location — open the app and allow location once")

    lat = float(user["latitude"])
    lon = float(user["longitude"])

    # Get nearest shelter
    from services.scheduler import _get_shelter_for_user
    shelter = _get_shelter_for_user(lat, lon)

    # Fire push
    payload = {
        "to":        user["push_token"],
        "title":     "🚨 URBAN FLOOD ALERT",
        "body":      f"⚠️ TEST — High flood risk (87%) at your location. Nearest shelter: {shelter['name']} — {shelter['distance_str']}.",
        "sound":     "default",
        "priority":  "high",
        "badge":     1,
        "channelId": "sos",
        "data": {
            "type":             "flood_alert",
            "probability":      0.87,
            "risk_level":       "High",
            "shelter_name":     shelter["name"],
            "shelter_distance": shelter["distance_str"],
            "shelter_maps_url": shelter["maps_url"],
            "shelter_lat":      shelter["lat"],
            "shelter_lon":      shelter["lon"],
            "user_lat":         lat,
            "user_lon":         lon,
        },
    }
    sent = _send_expo_push([payload])

    return {
        "success":       sent > 0,
        "sent_to":       user.get("full_name", phone),
        "push_token":    user["push_token"][:30] + "...",
        "shelter_found": shelter["name"],
        "shelter_dist":  shelter["distance_str"],
        "note":          "Check your phone — the FloodAlertModal should appear.",
    }


@router.post("/test-weather-tip")
def test_weather_tip(phone: str):
    """
    DEV ONLY — fires a real weather_tip push notification to the given phone
    using their saved location.

    Example:
        POST /api/sos/test-weather-tip?phone=+91XXXXXXXXXX
    """
    db = _get_service_client()
    if not db:
        raise HTTPException(status_code=503, detail="DB not available")

    try:
        res  = db.table("users").select("full_name,push_token,latitude,longitude").eq("phone", phone).execute()
        user = (res.data or [None])[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not user:
        raise HTTPException(status_code=404, detail=f"User with phone {phone} not found")
    if not user.get("push_token"):
        raise HTTPException(status_code=400, detail="User has no push token")

    lat = float(user.get("latitude") or 12.97)
    lon = float(user.get("longitude") or 77.59)

    from services.scheduler import _build_weather_tip
    tip = _build_weather_tip(lat, lon, user.get("full_name", "User"))
    if not tip:
        tip = {"title": "🌤️ Weather Update", "body": "Stay aware of local flood conditions."}

    payload = {
        "to":        user["push_token"],
        "title":     tip["title"],
        "body":      tip["body"],
        "sound":     "default",
        "priority":  "normal",
        "channelId": "weather",
        "data":      {"type": "weather_tip"},
    }
    sent = _send_expo_push([payload])

    return {
        "success":   sent > 0,
        "sent_to":   user.get("full_name", phone),
        "title":     tip["title"],
        "body":      tip["body"],
    }


# ── Rescue Team Dashboard HTML ────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_html():
    return HTMLResponse(content=DASHBOARD_HTML)


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rescue Team Dashboard</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8fafc;height:100vh;display:flex;flex-direction:column;overflow:hidden;}

/* ── Header ── */
header{height:64px;background:#fff;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;justify-content:space-between;padding:0 24px;flex-shrink:0;z-index:100;}
.brand{display:flex;align-items:center;gap:12px;}
.shield-icon{width:40px;height:40px;background:#ef4444;border-radius:10px;display:flex;align-items:center;justify-content:center;}
.shield-icon svg{width:22px;height:22px;}
.brand-name{font-size:16px;font-weight:700;color:#0f172a;}
.brand-sub{font-size:12px;color:#22c55e;display:flex;align-items:center;gap:4px;margin-top:1px;}
.live-dot{width:7px;height:7px;background:#22c55e;border-radius:50%;animation:blink 1.5s infinite;}
@keyframes blink{0%,100%{opacity:1;}50%{opacity:.3;}}
.header-right{display:flex;align-items:center;gap:20px;}
.online-badge{display:flex;align-items:center;gap:6px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:20px;padding:5px 12px;font-size:13px;font-weight:600;color:#16a34a;}
.clock{display:flex;align-items:center;gap:6px;font-size:13px;color:#64748b;}

/* ── Layout ── */
.layout{display:flex;flex:1;overflow:hidden;}

/* ── Left panel ── */
.left-panel{width:440px;flex-shrink:0;display:flex;flex-direction:column;background:#fff;border-right:1px solid #e2e8f0;overflow:hidden;}
.panel-header{padding:16px 20px;border-bottom:1px solid #f1f5f9;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;}
.panel-title{font-size:15px;font-weight:700;color:#0f172a;display:flex;align-items:center;gap:8px;}
.count-badge{background:#ef4444;color:#fff;font-size:12px;font-weight:700;padding:2px 8px;border-radius:99px;}
.refresh-btn{display:flex;align-items:center;gap:6px;background:none;border:1px solid #e2e8f0;border-radius:8px;padding:5px 10px;font-size:12px;color:#64748b;cursor:pointer;}
.refresh-btn:hover{background:#f8fafc;}
.cards-list{flex:1;overflow-y:auto;padding:12px;}
.cards-list::-webkit-scrollbar{width:4px;}
.cards-list::-webkit-scrollbar-track{background:transparent;}
.cards-list::-webkit-scrollbar-thumb{background:#e2e8f0;border-radius:4px;}

/* ── Alert card ── */
.alert-card{background:#fff;border:1.5px solid #e2e8f0;border-radius:14px;padding:16px;margin-bottom:10px;cursor:pointer;transition:all .18s;border-left-width:4px;}
.alert-card:hover{box-shadow:0 4px 12px rgba(0,0,0,.08);}
.alert-card.active{box-shadow:0 4px 16px rgba(0,0,0,.1);}
.card-top{display:flex;align-items:flex-start;gap:12px;}
.avatar{width:56px;height:56px;border-radius:14px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.avatar svg{width:28px;height:28px;}
.card-info{flex:1;min-width:0;}
.card-name{font-size:15px;font-weight:700;color:#0f172a;margin-bottom:5px;}
.status-badge{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:600;padding:3px 10px;border-radius:99px;margin-bottom:7px;}
.card-loc{display:flex;align-items:flex-start;gap:5px;font-size:12px;color:#64748b;margin-bottom:4px;line-height:1.4;}
.card-time{display:flex;align-items:center;gap:5px;font-size:12px;color:#64748b;}
.live-label{color:#22c55e;font-weight:600;}
.card-call-btn{flex-shrink:0;border:none;border-radius:10px;padding:9px 16px;font-size:13px;font-weight:600;color:#fff;cursor:pointer;display:flex;align-items:center;gap:6px;}
.card-call-btn:hover{filter:brightness(1.08);}
.card-bottom{display:flex;align-items:center;justify-content:space-between;margin-top:12px;padding-top:12px;border-top:1px solid #f1f5f9;}
.rescued-btn{display:flex;align-items:center;gap:6px;background:#f0fdf4;border:1.5px solid #86efac;border-radius:8px;padding:6px 14px;font-size:12px;font-weight:600;color:#16a34a;cursor:pointer;transition:all .18s;}
.rescued-btn:hover{background:#dcfce7;border-color:#4ade80;}
.rescued-btn.loading{opacity:.6;pointer-events:none;}
.coords{font-size:12px;color:#64748b;}
.coords-label{font-size:10px;color:#94a3b8;margin-bottom:2px;}
.maps-btn{display:flex;align-items:center;gap:6px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:6px 12px;font-size:12px;color:#3b82f6;cursor:pointer;font-weight:500;}
.maps-btn:hover{background:#eff6ff;border-color:#bfdbfe;}

/* ── Right panel ── */
.right-panel{flex:1;display:flex;flex-direction:column;overflow:hidden;position:relative;}
.empty-state{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#94a3b8;gap:12px;}
.empty-icon{width:64px;height:64px;background:#f1f5f9;border-radius:16px;display:flex;align-items:center;justify-content:center;}

/* ── Detail bar ── */
.detail-bar{background:#fff;border-bottom:1px solid #e2e8f0;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;}
.detail-left{display:flex;align-items:center;gap:14px;}
.detail-avatar{width:48px;height:48px;border-radius:12px;display:flex;align-items:center;justify-content:center;}
.detail-name{font-size:18px;font-weight:700;color:#0f172a;display:flex;align-items:center;gap:10px;margin-bottom:4px;}
.detail-meta{font-size:13px;color:#64748b;display:flex;flex-direction:column;gap:3px;}
.detail-meta-row{display:flex;align-items:center;gap:6px;}
.call-now-btn{display:flex;align-items:center;gap:8px;background:#ef4444;color:#fff;border:none;border-radius:12px;padding:12px 24px;font-size:15px;font-weight:700;cursor:pointer;box-shadow:0 4px 12px rgba(239,68,68,.3);}
.call-now-btn:hover{background:#dc2626;}

/* ── Map ── */
#map{flex:1;z-index:1;}
.route-info-box{background:#fff;border-radius:12px;padding:12px 16px;box-shadow:0 4px 16px rgba(0,0,0,.12);min-width:220px;}
.route-mins{font-size:18px;font-weight:700;color:#0f172a;}
.route-via{font-size:12px;color:#64748b;margin-top:2px;}
.route-maps-link{display:flex;align-items:center;gap:6px;color:#3b82f6;font-size:13px;font-weight:600;margin-top:8px;text-decoration:none;}
.route-maps-link:hover{text-decoration:underline;}

/* ── Warning bar ── */
.warning-bar{background:#fff1f2;border-top:1px solid #fecaca;padding:12px 24px;display:flex;align-items:center;gap:10px;flex-shrink:0;}
.warning-icon{width:36px;height:36px;background:#fee2e2;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.warning-text{font-size:13px;color:#991b1b;}
.warning-text strong{color:#ef4444;}

/* ── Toast animation ── */
@keyframes slideInToast{from{transform:translateY(16px);opacity:0;}to{transform:translateY(0);opacity:1;}}

/* ── Leaflet custom markers ── */
.victim-pin{position:relative;display:flex;align-items:center;justify-content:center;}
.victim-pulse{position:absolute;width:56px;height:56px;border-radius:50%;animation:vp 1.6s ease-out infinite;}
@keyframes vp{0%{transform:scale(.6);opacity:.8;}100%{transform:scale(1.8);opacity:0;}}
.victim-inner{width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;box-shadow:0 3px 10px rgba(0,0,0,.25);position:relative;z-index:2;}
.rescue-dot{width:20px;height:20px;background:#2563eb;border-radius:50%;border:3px solid #fff;box-shadow:0 2px 8px rgba(37,99,235,.4);}
</style>
</head>
<body>

<!-- Header -->
<header>
  <div class="brand">
    <div class="shield-icon">
      <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
      </svg>
    </div>
    <div>
      <div class="brand-name">Rescue Team</div>
      <div class="brand-sub"><span class="live-dot"></span> Live Alerts</div>
    </div>
  </div>
  <div class="header-right">
    <div class="online-badge">
      <span style="width:8px;height:8px;background:#22c55e;border-radius:50%;display:inline-block;"></span>
      Online
    </div>
    <div class="clock">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
      <span id="clock-display"></span>
    </div>
  </div>
</header>

<!-- Layout -->
<div class="layout">

  <!-- Left panel -->
  <div class="left-panel">
    <div class="panel-header">
      <div class="panel-title">
        Active People at Risk
        <span class="count-badge" id="count-badge">0</span>
      </div>
      <button class="refresh-btn" onclick="fetchAlerts()">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
        Auto Refresh (10s)
      </button>
    </div>
    <div class="cards-list" id="cards-list">
      <div style="text-align:center;padding:40px 20px;color:#94a3b8;font-size:14px;">Loading alerts…</div>
    </div>
  </div>

  <!-- Right panel -->
  <div class="right-panel" id="right-panel">

    <div class="detail-bar" id="detail-bar" style="display:none;">
      <div class="detail-left">
        <div class="detail-avatar" id="d-avatar"></div>
        <div>
          <div class="detail-name">
            <span id="d-name"></span>
            <span id="d-badge"></span>
          </div>
          <div class="detail-meta">
            <div class="detail-meta-row">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
              <span id="d-address"></span>
            </div>
            <div class="detail-meta-row">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              Live Location: <span id="d-coords" style="font-weight:600;color:#0f172a;margin-left:3px;"></span>
            </div>
            <div class="detail-meta-row">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              Last Updated: <span id="d-time" style="margin-left:3px;"></span>
            </div>
          </div>
        </div>
      </div>
      <button class="call-now-btn" id="call-now-btn" onclick="callNow()">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="white"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 12 19.79 19.79 0 0 1 1.61 3.36 2 2 0 0 1 3.6 1.18h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L7.91 8.78a16 16 0 0 0 6.29 6.29l.95-.95a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
        Call Now (<span id="call-now-phone"></span>)
      </button>
    </div>

    <div id="map" style="flex:1;"></div>

    <div class="warning-bar" id="warning-bar" style="display:none;">
      <div class="warning-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      </div>
      <div class="warning-text" id="warning-text"></div>
    </div>

    <div class="empty-state" id="empty-state">
      <div class="empty-icon">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.5"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
      </div>
      <div style="font-size:15px;font-weight:600;color:#64748b;">No alert selected</div>
      <div style="font-size:13px;color:#94a3b8;">Click an alert card to view on map</div>
    </div>

  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
// ── State ────────────────────────────────────────────────────────────────────
let alerts        = [];
let selected      = null;
let map           = null;
let victimMarker  = null;
let rescueMarker  = null;
let routePolyline = null;
let routeControl  = null;
let rescueLoc     = null;  // {lat, lon} of rescue team (browser geolocation)

// ── Clock ────────────────────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  document.getElementById('clock-display').textContent =
    now.toLocaleTimeString('en-US', { hour:'2-digit', minute:'2-digit' });
}
updateClock();
setInterval(updateClock, 30000);

// ── Emergency type config ────────────────────────────────────────────────────
function getTypeConfig(message, severity) {
  // severity field stores the category: "In Danger", "Stranded", "Injured"
  // message field is legacy / may not exist
  const raw = (severity || message || '').toLowerCase();
  if (raw.includes('stranded'))
    return { label:'Stranded / Need Help',      color:'#f97316', bg:'#fff7ed', badgeBg:'#fed7aa', avatarBg:'#fff7ed', warn:'Person is stranded and needs assistance. Respond immediately.' };
  if (raw.includes('injured') || raw.includes('assistance'))
    return { label:'Injured / Need Assistance', color:'#8b5cf6', bg:'#f5f3ff', badgeBg:'#ddd6fe', avatarBg:'#f5f3ff', warn:'Person is injured and needs medical assistance urgently.' };
  return   { label:'In Danger',                color:'#ef4444', bg:'#fef2f2', badgeBg:'#fecaca', avatarBg:'#fef2f2', warn:'Person is in danger. Immediate response required. Use the route to reach the location quickly.' };
}

function avatarSVG(color) {
  return `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
    <circle cx="12" cy="7" r="4"/>
    <path d="M2 18c1-2 3-4 5-5m10 5c-1-2-3-4-5-5" stroke-width="1.4" opacity=".6"/>
  </svg>`;
}

function formatTime(iso) {
  if (!iso) return 'Just now';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return 'Just now';
    return d.toLocaleTimeString('en-US', { hour:'2-digit', minute:'2-digit' });
  } catch { return 'Just now'; }
}

function formatDuration(secs) {
  if (secs < 3600) return Math.round(secs / 60) + ' min';
  return Math.floor(secs/3600) + ' h ' + Math.round((secs%3600)/60) + ' min';
}

function formatDist(m) {
  return m >= 1000 ? (m/1000).toFixed(1) + ' km' : Math.round(m) + ' m';
}

// ── Fetch alerts ─────────────────────────────────────────────────────────────
async function fetchAlerts() {
  try {
    const res  = await fetch('/api/sos/dashboard/data');
    const data = await res.json();
    alerts = (data.alerts || []).filter(a => a.status === 'active');
    renderCards();

    // Re-select current alert with updated data (or auto-select first)
    if (selected) {
      const updated = alerts.find(a => a.id === selected.id);
      if (updated) selectAlert(updated, false);
    } else if (alerts.length > 0) {
      selectAlert(alerts[0]);
    } else {
      showEmpty();
    }
  } catch(e) {
    console.error('Fetch error:', e);
  }
}

// ── Render card list ─────────────────────────────────────────────────────────
function renderCards() {
  const container = document.getElementById('cards-list');
  document.getElementById('count-badge').textContent = alerts.length;

  if (alerts.length === 0) {
    container.innerHTML = `<div style="text-align:center;padding:48px 20px;color:#94a3b8">
      <div style="font-size:32px;margin-bottom:8px">✅</div>
      <div style="font-size:14px;font-weight:600">No active alerts</div>
      <div style="font-size:12px;margin-top:4px">All clear — refreshing every 10s</div>
    </div>`;
    return;
  }

  container.innerHTML = alerts.map(a => {
    const cfg     = getTypeConfig(a.message, a.severity);
    const isActive = selected && selected.id === a.id;
    const lat     = parseFloat(a.latitude  || 0).toFixed(4);
    const lon     = parseFloat(a.longitude || 0).toFixed(4);
    const time    = formatTime(a.created_at);

    return `
    <div class="alert-card ${isActive ? 'active' : ''}"
         style="border-left-color:${cfg.color};${isActive ? `background:${cfg.bg};` : ''}"
         onclick="selectAlert(${JSON.stringify(a).replace(/"/g,"&quot;")})">
      <div class="card-top">
        <div class="avatar" style="background:${cfg.avatarBg}">${avatarSVG(cfg.color)}</div>
        <div class="card-info">
          <div class="card-name">${a.name || 'Unknown'}</div>
          <div class="status-badge" style="background:${cfg.badgeBg};color:${cfg.color};">
            ${statusIcon(cfg.label)} ${cfg.label}
          </div>
          <div class="card-loc">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2" style="flex-shrink:0;margin-top:1px"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
            ${a.address || `${lat}, ${lon}`}
          </div>
          <div class="card-time">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            ${time} <span style="margin:0 3px;color:#e2e8f0">•</span>
            <span class="live-label">
              <span class="live-dot" style="display:inline-block;width:6px;height:6px;background:#22c55e;border-radius:50%;margin-right:3px;"></span>
              Live
            </span>
          </div>
        </div>
        <button class="card-call-btn" style="background:${cfg.color};"
                data-phone="${a.phone || ''}"
                onclick="event.stopPropagation(); dialPhone(this.dataset.phone)"
                title="Call ${a.name || 'victim'}">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="white"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 12 19.79 19.79 0 0 1 1.61 3.36 2 2 0 0 1 3.6 1.18h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 8.78a16 16 0 0 0 6.29 6.29l.95-.95a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
          Call
        </button>
      </div>
      <div class="card-bottom">
        <button class="maps-btn" onclick="event.stopPropagation(); window.open('${a.google_maps_url || `https://maps.google.com/?q=${a.latitude},${a.longitude}`}', '_blank')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
          Open in Maps
        </button>
        <button class="rescued-btn" id="rescued-btn-${a.id}"
                onclick="event.stopPropagation(); markRescued('${a.id}')">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#16a34a" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
          Rescued
        </button>
      </div>
    </div>`;
  }).join('');
}

function statusIcon(label) {
  if (label.includes('Stranded'))   return '&#9888;';
  if (label.includes('Injured'))    return '&#10010;';
  return '&#127754;'; // wave emoji for In Danger
}

// ── Select alert → show detail + map ─────────────────────────────────────────
function selectAlert(alert, scroll=true) {
  selected = alert;
  renderCards(); // re-render to update active state

  const cfg  = getTypeConfig(alert.message, alert.severity);
  const lat  = parseFloat(alert.latitude);
  const lon  = parseFloat(alert.longitude);
  const time = formatTime(alert.created_at);

  // Detail bar
  document.getElementById('d-avatar').innerHTML = `<div style="background:${cfg.avatarBg};width:48px;height:48px;border-radius:12px;display:flex;align-items:center;justify-content:center;">${avatarSVG(cfg.color)}</div>`;
  document.getElementById('d-name').textContent  = alert.name || 'Unknown';
  document.getElementById('d-badge').innerHTML   = `<span class="status-badge" style="background:${cfg.badgeBg};color:${cfg.color};font-size:11px;">${statusIcon(cfg.label)} ${cfg.label}</span>`;
  document.getElementById('d-address').textContent = alert.address || `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
  document.getElementById('d-coords').textContent    = `${lat.toFixed(4)}° N, ${lon.toFixed(4)}° E`;
  document.getElementById('d-time').textContent      = time;
  document.getElementById('call-now-phone').textContent = alert.phone || '';

  // Warning bar
  document.getElementById('warning-text').innerHTML = `<strong>${alert.name || 'Person'}</strong> — ${cfg.warn}`;
  document.getElementById('warning-bar').style.display = 'flex';
  document.getElementById('detail-bar').style.display  = 'flex';
  document.getElementById('empty-state').style.display = 'none';

  // Map
  initOrUpdateMap(lat, lon, alert, cfg);
}

function showEmpty() {
  selected = null;
  document.getElementById('detail-bar').style.display  = 'none';
  document.getElementById('warning-bar').style.display = 'none';
  document.getElementById('empty-state').style.display = 'flex';
  document.getElementById('map').style.flex = '0';
}

// ── Leaflet map ───────────────────────────────────────────────────────────────
function initOrUpdateMap(lat, lon, alert, cfg) {
  document.getElementById('map').style.flex = '1';

  if (!map) {
    map = L.map('map', { zoomControl: false }).setView([lat, lon], 14);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
      maxZoom: 19,
    }).addTo(map);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
  } else {
    map.setView([lat, lon], 14);
  }

  // Remove old layers
  if (victimMarker)  { map.removeLayer(victimMarker);  victimMarker  = null; }
  if (rescueMarker)  { map.removeLayer(rescueMarker);  rescueMarker  = null; }
  if (routePolyline) { map.removeLayer(routePolyline); routePolyline = null; }
  if (routeControl)  { map.removeControl(routeControl); routeControl = null; }

  // Victim marker (red pulsing)
  const victimIcon = L.divIcon({
    className: '',
    html: `<div class="victim-pin">
      <div class="victim-pulse" style="background:${cfg.color}22;"></div>
      <div class="victim-inner" style="background:${cfg.color};">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="white"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
      </div>
    </div>`,
    iconSize: [48, 48],
    iconAnchor: [24, 40],
  });
  victimMarker = L.marker([lat, lon], { icon: victimIcon })
    .addTo(map)
    .bindPopup(`<b>${alert.name || 'Victim'}</b><br>${alert.address || ''}`, { offset: [0, -30] })
    .openPopup();

  // Rescue team marker (blue dot) + routing
  if (rescueLoc) {
    const rescueIcon = L.divIcon({
      className: '',
      html: '<div class="rescue-dot"></div>',
      iconSize: [20, 20],
      iconAnchor: [10, 10],
    });
    rescueMarker = L.marker([rescueLoc.lat, rescueLoc.lon], { icon: rescueIcon }).addTo(map);
    drawRoute(rescueLoc.lat, rescueLoc.lon, lat, lon, alert, cfg);

    // Fit bounds to show both
    const bounds = L.latLngBounds([[lat, lon], [rescueLoc.lat, rescueLoc.lon]]);
    map.fitBounds(bounds, { padding: [60, 60] });
  }
}

// ── OSRM routing ──────────────────────────────────────────────────────────────
async function drawRoute(fromLat, fromLon, toLat, toLon, alert, cfg) {
  try {
    const url  = `https://router.project-osrm.org/route/v1/driving/${fromLon},${fromLat};${toLon},${toLat}?overview=full&geometries=geojson`;
    const res  = await fetch(url);
    const data = await res.json();
    if (data.code !== 'Ok') return;

    const route = data.routes[0];
    const dist  = formatDist(route.distance);
    const time  = formatDuration(route.duration);

    // Draw route polyline
    routePolyline = L.geoJSON(route.geometry, {
      style: { color:'#2563eb', weight:5, opacity:.85 }
    }).addTo(map);

    // Route info popup on map (top-left corner)
    const mapsUrl = `https://www.google.com/maps/dir/${fromLat},${fromLon}/${toLat},${toLon}`;
    const info = L.control({ position: 'topleft' });
    info.onAdd = function() {
      const div = L.DomUtil.create('div', 'route-info-box');
      div.innerHTML = `
        <div class="route-mins"><b>${time}</b> <span style="font-size:14px;font-weight:500;color:#64748b;">(${dist})</span></div>
        <div class="route-via">Fastest route to ${alert.name || 'victim'}</div>
        <a class="route-maps-link" href="${mapsUrl}" target="_blank">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
          Open in Google Maps ↗
        </a>`;
      return div;
    };
    info.addTo(map);
    routeControl = info;
  } catch(e) {
    console.warn('Routing error:', e);
  }
}

// ── Geolocation (rescue team) ────────────────────────────────────────────────
if (navigator.geolocation) {
  navigator.geolocation.getCurrentPosition(pos => {
    rescueLoc = { lat: pos.coords.latitude, lon: pos.coords.longitude };
    if (selected) selectAlert(selected, false); // re-render map with route
  }, () => {});
}

// ── Phone dialer ──────────────────────────────────────────────────────────────
function dialPhone(phone) {
  if (!phone || phone.trim() === '') {
    showToast('❌ No phone number stored for this person', true);
    return;
  }
  // Strip spaces, dashes, parentheses — keep + and digits only
  const clean = phone.replace(/[\s\-\(\)]/g, '');
  console.log('[Dial]', clean);
  const a = document.createElement('a');
  a.href = 'tel:' + clean;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  showToast('📞 Calling ' + phone);
}

function callNow() {
  if (selected && selected.phone) dialPhone(selected.phone);
}

// ── Mark as Rescued ───────────────────────────────────────────────────────────
async function markRescued(id) {
  const btn = document.getElementById('rescued-btn-' + id);
  if (btn) {
    btn.classList.add('loading');
    btn.innerHTML = `
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#16a34a" stroke-width="2.5">
        <polyline points="20 6 9 17 4 12"/>
      </svg> Saving…`;
  }
  try {
    const res = await fetch(`/api/sos/${id}/resolve`, { method: 'PUT' });
    if (!res.ok) throw new Error('Server error');

    // Remove from local list immediately — no wait for next poll
    alerts = alerts.filter(a => a.id !== id);

    // If this was the selected alert, clear the right panel
    if (selected && selected.id === id) {
      selected = null;
      if (victimMarker)  { map.removeLayer(victimMarker);  victimMarker  = null; }
      if (rescueMarker)  { map.removeLayer(rescueMarker);  rescueMarker  = null; }
      if (routePolyline) { map.removeLayer(routePolyline); routePolyline = null; }
      if (routeControl)  { map.removeControl(routeControl); routeControl = null; }
      if (alerts.length > 0) {
        selectAlert(alerts[0]);
      } else {
        showEmpty();
      }
    }
    renderCards();

    // Brief success toast
    showToast(`✅ Marked as Rescued`);
  } catch(e) {
    showToast('❌ Failed to update. Please retry.', true);
    if (btn) {
      btn.classList.remove('loading');
      btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#16a34a" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> Rescued`;
    }
  }
}

// ── Toast notification ────────────────────────────────────────────────────────
function showToast(msg, isError = false) {
  const existing = document.getElementById('toast');
  if (existing) existing.remove();
  const toast = document.createElement('div');
  toast.id = 'toast';
  toast.style.cssText = `
    position:fixed;bottom:24px;right:24px;z-index:9999;
    background:${isError ? '#fef2f2' : '#f0fdf4'};
    border:1.5px solid ${isError ? '#fca5a5' : '#86efac'};
    color:${isError ? '#991b1b' : '#166534'};
    padding:12px 20px;border-radius:12px;font-size:14px;font-weight:600;
    box-shadow:0 4px 16px rgba(0,0,0,.12);
    animation:slideInToast .25s ease;
  `;
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

// ── Auto-refresh ─────────────────────────────────────────────────────────────
fetchAlerts();
setInterval(fetchAlerts, 10000);
</script>
</body>
</html>"""
