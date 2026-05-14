"""
JeevanSetu Admin Dashboard
GET  /admin              — full HTML dashboard
GET  /admin/data         — live JSON feed (auto-refresh 30s)
POST /admin/demo-flood   — demo: manually override parameters, run ML, send flood alert once
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from services.supabase_service import _get_service_client
from config import ADMIN_API_KEY
from datetime import datetime, timezone, timedelta
import requests as _req

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Admin auth guard ─────────────────────────────────────────────────────────
def _require_admin(request: Request):
    """
    Accepts the admin key via:
      - Query param:  ?admin_key=<key>
      - Header:       X-Admin-Key: <key>
    Raises 403 if missing or wrong.
    """
    key = (
        request.query_params.get("admin_key")
        or request.headers.get("x-admin-key")
        or request.headers.get("X-Admin-Key")
    )
    if key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing admin key")

# ── Geocode cache (keyed by 3-dp coords ≈ 100 m grid, TTL 24 h) ──────────────
_geocode_cache: dict[tuple, tuple] = {}  # (lat3, lon3) → (address_str, cached_at)
_GEOCODE_TTL = 86400  # seconds


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reverse_geocode(lat: float, lon: float) -> str:
    import time
    key = (round(lat, 3), round(lon, 3))
    cached = _geocode_cache.get(key)
    if cached and (time.time() - cached[1]) < _GEOCODE_TTL:
        return cached[0]
    try:
        r = _req.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 14},
            headers={"User-Agent": "JeevanSetu-Admin/1.0"},
            timeout=5,
        )
        d    = r.json()
        addr = d.get("address", {})
        road = addr.get("road") or addr.get("pedestrian") or addr.get("neighbourhood") or ""
        city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("suburb") or ""
        state= addr.get("state") or ""
        parts = [p for p in [road, city, state] if p]
        result = ", ".join(parts[:3]) if parts else f"{round(lat,4)}°N, {round(lon,4)}°E"
    except Exception:
        result = f"{round(lat,4)}°N, {round(lon,4)}°E"
    _geocode_cache[key] = (result, time.time())
    return result


# ── Data API ──────────────────────────────────────────────────────────────────

@router.get("/data")
def admin_data(_: None = Depends(_require_admin)):
    db = _get_service_client()
    if not db:
        return JSONResponse({"error": "DB not available"}, status_code=503)

    # ── SOS requests ──────────────────────────────────────────────────────────
    try:
        all_sos_res = db.table("sos_requests").select("*").order("created_at", desc=True).execute()
        all_sos     = all_sos_res.data or []
    except Exception:
        all_sos = []

    total_sos      = len(all_sos)
    active_sos     = sum(1 for s in all_sos if s.get("status") == "active")
    resolved_sos   = sum(1 for s in all_sos if s.get("status") != "active")
    total_notified = sum(int(s.get("notified_count") or 0) for s in all_sos)

    cat_counts: dict = {}
    for s in all_sos:
        raw = (s.get("severity") or "In Danger").strip()
        cat = raw if raw in ("In Danger", "Stranded", "Injured") else "In Danger"
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    sos_by_type = [{"label": k, "count": v} for k, v in cat_counts.items()]

    now   = datetime.now(timezone.utc)
    trend = []
    for i in range(6, -1, -1):
        day   = now - timedelta(days=i)
        label = day.strftime("%b %d")
        count = sum(1 for s in all_sos if (s.get("created_at") or "")[:10] == day.strftime("%Y-%m-%d"))
        trend.append({"day": label, "count": count})

    recent_sos = []
    for s in all_sos[:10]:
        recent_sos.append({
            "id":         s.get("id", ""),
            "name":       s.get("name", "Unknown"),
            "phone":      s.get("phone", "—"),
            "address":    s.get("address", "—"),
            "category":   s.get("severity", "In Danger"),
            "status":     s.get("status", "active"),
            "notified":   s.get("notified_count", 0),
            "created_at": (s.get("created_at") or "")[:16].replace("T", " "),
            "lat":        s.get("latitude"),
            "lon":        s.get("longitude"),
            "maps_url":   s.get("google_maps_url", ""),
        })

    area_counts: dict = {}
    for s in all_sos:
        addr  = s.get("address", "")
        parts = [p.strip() for p in addr.split(",") if p.strip()]
        city  = parts[1] if len(parts) >= 2 else (parts[0] if parts else "Unknown")
        area_counts[city] = area_counts.get(city, 0) + 1
    top_areas = [{"area": k, "count": v}
                 for k, v in sorted(area_counts.items(), key=lambda x: x[1], reverse=True)[:6]]

    # Map pins — every SOS with lat/lon
    map_pins = [
        {
            "lat":      s.get("latitude"),
            "lon":      s.get("longitude"),
            "name":     s.get("name", "Unknown"),
            "phone":    s.get("phone", ""),
            "category": s.get("severity", "In Danger"),
            "status":   s.get("status", "active"),
            "address":  s.get("address", ""),
            "notified": s.get("notified_count", 0),
            "time":     (s.get("created_at") or "")[:16].replace("T", " "),
            "maps_url": s.get("google_maps_url", ""),
        }
        for s in all_sos if s.get("latitude") and s.get("longitude")
    ]

    # ── Users ─────────────────────────────────────────────────────────────────
    try:
        users_res = db.table("users").select("full_name,phone,push_token,latitude,longitude").execute()
        users     = users_res.data or []
    except Exception:
        users = []

    total_users      = len(users)
    users_with_token = sum(1 for u in users if u.get("push_token"))
    users_with_loc   = sum(1 for u in users if u.get("latitude"))

    users_table = []
    for u in users:
        lat = u.get("latitude")
        lon = u.get("longitude")
        location_str = ""
        if lat and lon:
            location_str = _reverse_geocode(float(lat), float(lon))
        users_table.append({
            "name":      u.get("full_name", "Unknown"),
            "phone":     u.get("phone", "—"),
            "has_token": bool(u.get("push_token")),
            "has_loc":   bool(lat),
            "lat":       lat,
            "lon":       lon,
            "location":  location_str,
            "maps_url":  f"https://maps.google.com/?q={lat},{lon}" if lat and lon else "",
        })

    # ── Alerts ────────────────────────────────────────────────────────────────
    try:
        alerts_rows = db.table("user_alerts").select("id,severity,source,created_at").execute().data or []
    except Exception:
        alerts_rows = []

    total_alerts    = len(alerts_rows)
    flood_alerts    = sum(1 for a in alerts_rows
                         if "flood" in (a.get("source") or "").lower()
                         or a.get("severity") == "Extreme")
    cyclone_alerts  = sum(1 for a in alerts_rows
                         if "cyclone" in (a.get("source") or "").lower())
    weather_alerts  = total_alerts - flood_alerts - cyclone_alerts

    # ── Cyclone ML model status ───────────────────────────────────────────────
    cyclone_ml_active = False
    try:
        from services.cyclone_service import _CYCLONE_MODEL
        cyclone_ml_active = _CYCLONE_MODEL is not None
    except Exception:
        pass

    return {
        "total_sos": total_sos, "active_sos": active_sos,
        "resolved_sos": resolved_sos, "total_notified": total_notified,
        "total_users": total_users, "users_with_token": users_with_token,
        "users_with_loc": users_with_loc,
        "total_alerts": total_alerts, "flood_alerts": flood_alerts,
        "cyclone_alerts": cyclone_alerts, "weather_alerts": weather_alerts,
        "sos_by_type": sos_by_type, "trend": trend,
        "top_areas": top_areas, "recent_sos": recent_sos,
        "users": users_table, "map_pins": map_pins,
        "cyclone_ml_active": cyclone_ml_active,
    }


# ── Demo flood endpoint ───────────────────────────────────────────────────────

class DemoFloodParams(BaseModel):
    rainfall_1h:   float = 35.0
    rainfall_24h:  float = 120.0
    humidity:      float = 92.0
    temperature:   float = 27.0
    soil_moisture: float = 0.85
    elevation:     float = 18.0
    drainage:      float = 2.0
    slope:         float = 0.4
    pressure:      float = 1004.0
    # Demo location — only users within radius_km of this point get notified
    demo_lat:      float = 12.9716   # Bangalore default; override with actual demo location
    demo_lon:      float = 77.5946
    radius_km:     float = 5.0       # notify users within this radius of demo location
    target_phone:  str   = ""        # optional: override radius — send to ONE specific phone


@router.post("/demo-flood")
def demo_flood(params: DemoFloodParams, _: None = Depends(_require_admin)):
    """
    Demo mode: run the ML model with manually supplied parameters.
    Sends a real flood_alert push notification regardless of probability
    (so you can demo it even when real weather is calm).
    After this call the scheduler continues using real data — no state is changed.
    """
    # Build feature dict (same keys as _fetch_features)
    features = {
        "rainfall_1h":   params.rainfall_1h,
        "rainfall_24h":  params.rainfall_24h,
        "humidity":      params.humidity,
        "temperature":   params.temperature,
        "elevation":     params.elevation,
        "soil_moisture": params.soil_moisture,
        "drainage":      params.drainage,
        "slope":         params.slope,
        "pressure":      params.pressure,
        "sat_index":     round(params.soil_moisture * params.rainfall_24h, 3),
        "rain_burst":    round(params.rainfall_1h / max(params.rainfall_24h, 1.0), 4),
        "drain_eff":     round(params.drainage * (params.slope + 0.5) / 10.0, 3),
    }

    # Run model
    prob = 0.91  # fallback if model unavailable
    try:
        from routes.predict import _model
        import pandas as pd
        if _model:
            df   = pd.DataFrame([features])
            prob = float(_model.predict_proba(df)[0][1])
    except Exception:
        pass

    pct = round(prob * 100)

    # Get shelter based on the DEMO location (not a random user's location)
    shelter = {
        "name": "Nearest Government Shelter", "distance_str": "~500 m",
        "maps_url": f"https://www.google.com/maps/search/emergency+shelter/@{params.demo_lat},{params.demo_lon},15z",
        "lat": params.demo_lat, "lon": params.demo_lon,
    }
    try:
        from services.scheduler import _get_shelter_for_user
        shelter = _get_shelter_for_user(params.demo_lat, params.demo_lon)
    except Exception:
        pass

    # Collect push targets — only users within radius_km of the demo location
    # (unless target_phone is set, in which case send to that one person only)
    push_msgs   = []
    skipped_far = 0
    try:
        from services.supabase_service import _haversine
        db = _get_service_client()
        if db:
            users_res = db.table("users").select("full_name,phone,push_token,latitude,longitude").execute()
            for u in (users_res.data or []):
                if not u.get("push_token"):
                    continue

                # ── specific phone override ──────────────────────────────────
                if params.target_phone:
                    if u.get("phone") != params.target_phone:
                        continue
                else:
                    # ── radius filter ────────────────────────────────────────
                    if u.get("latitude") and u.get("longitude"):
                        dist_km = _haversine(
                            params.demo_lat, params.demo_lon,
                            float(u["latitude"]), float(u["longitude"]),
                        )
                        if dist_km > params.radius_km:
                            skipped_far += 1
                            continue
                    # user with no saved location — skip (can't verify they're in the zone)
                    else:
                        skipped_far += 1
                        continue

                push_msgs.append({
                    "to":        u["push_token"],
                    "title":     "🚨 URBAN FLOOD ALERT",
                    "body":      f"⚠️ DEMO — High flood risk ({pct}%) near your area. Nearest shelter: {shelter['name']} — {shelter['distance_str']}.",
                    "sound":     "default",
                    "priority":  "high",
                    "badge":     1,
                    "channelId": "sos",
                    "data": {
                        "type":             "flood_alert",
                        "probability":      round(prob, 3),
                        "risk_level":       "High",
                        "shelter_name":     shelter["name"],
                        "shelter_distance": shelter["distance_str"],
                        "shelter_maps_url": shelter["maps_url"],
                        "shelter_lat":      shelter["lat"],
                        "shelter_lon":      shelter["lon"],
                        # Use the DEMO location as the flood epicentre shown in the modal
                        "user_lat":         params.demo_lat,
                        "user_lon":         params.demo_lon,
                    },
                })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    # Send
    sent = 0
    if push_msgs:
        try:
            resp = _req.post(
                "https://exp.host/--/api/v2/push/send",
                json=push_msgs,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=15,
            )
            data = resp.json().get("data", [])
            sent = sum(1 for d in data if isinstance(d, dict) and d.get("status") == "ok") \
                   if isinstance(data, list) else len(push_msgs)
        except Exception as e:
            return JSONResponse({"success": False, "error": f"Push failed: {e}"}, status_code=500)

    return {
        "success":       True,
        "probability":   round(prob, 3),
        "pct":           pct,
        "sent_to":       sent,
        "total_targets": len(push_msgs),
        "skipped_far":   skipped_far,
        "demo_location": {"lat": params.demo_lat, "lon": params.demo_lon, "radius_km": params.radius_km},
        "shelter":       shelter["name"],
        "features":      features,
        "note":          "Demo complete. Scheduler continues with real data — no state changed.",
    }


# ── Demo cyclone endpoint ─────────────────────────────────────────────────────

class DemoCycloneParams(BaseModel):
    wind_gusts_kmh:       float = 95.0
    surface_pressure_hpa: float = 975.0
    pressure_drop_6h:     float = 6.0
    cape_jkg:             float = 1500.0
    demo_lat:             float = 13.0827   # Chennai default
    demo_lon:             float = 80.2707
    radius_km:            float = 200.0
    target_phone:         str   = ""


@router.post("/demo-cyclone")
def demo_cyclone(params: DemoCycloneParams, _: None = Depends(_require_admin)):
    """
    Demo mode: run the cyclone ML/physics model with supplied parameters.
    Sends a real cyclone_alert push notification regardless of probability.
    """
    from services.cyclone_service import (
        _CYCLONE_MODEL, CYCLONE_FEATURES, _coast_distance_km, _season_factor,
        _imd_category, _risk_label, compute_probability,
    )
    from datetime import datetime, timezone as _tz

    coast_km = round(_coast_distance_km(params.demo_lat, params.demo_lon), 1)
    month    = datetime.now(_tz.utc).month
    s_factor = _season_factor(month)

    features = {
        "wind_gusts_kmh":        params.wind_gusts_kmh,
        "surface_pressure_hpa":  params.surface_pressure_hpa,
        "pressure_drop_6h":      params.pressure_drop_6h,
        "cape_jkg":              params.cape_jkg,
        "precipitation_mm":      10.0,
        "humidity":              85.0,
        "coastal_proximity_km":  coast_km,
        "season_factor":         s_factor,
        "lat_abs":               abs(params.demo_lat),
        "gdacs_active":          False,
        "gdacs_name":            "",
        "gdacs_distance_km":     9999.0,
        "gdacs_alert_level":     "",
    }

    prob     = compute_probability(features)
    pct      = round(prob * 100)
    risk     = _risk_label(prob)
    category = _imd_category(params.wind_gusts_kmh)

    # Collect push targets
    push_msgs   = []
    skipped_far = 0
    try:
        from services.supabase_service import _haversine
        db = _get_service_client()
        if db:
            users_res = db.table("users").select("full_name,phone,push_token,latitude,longitude").execute()
            for u in (users_res.data or []):
                if not u.get("push_token"):
                    continue
                if params.target_phone:
                    if u.get("phone") != params.target_phone:
                        continue
                else:
                    if u.get("latitude") and u.get("longitude"):
                        dist_km = _haversine(
                            params.demo_lat, params.demo_lon,
                            float(u["latitude"]), float(u["longitude"]),
                        )
                        if dist_km > params.radius_km:
                            skipped_far += 1
                            continue
                    else:
                        skipped_far += 1
                        continue
                push_msgs.append({
                    "to":        u["push_token"],
                    "title":     "🌀 CYCLONE ALERT",
                    "body":      f"⚠️ DEMO — {risk} cyclone risk ({pct}%) · {category} · "
                                 f"Gusts {params.wind_gusts_kmh:.0f} km/h. Stay indoors, follow IMD bulletins.",
                    "sound":     "default",
                    "priority":  "high",
                    "badge":     1,
                    "channelId": "sos",
                    "data": {
                        "type":        "cyclone_alert",
                        "probability": round(prob, 3),
                        "risk_level":  risk,
                        "category":    category,
                        "user_lat":    params.demo_lat,
                        "user_lon":    params.demo_lon,
                    },
                })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    sent = 0
    if push_msgs:
        try:
            resp = _req.post(
                "https://exp.host/--/api/v2/push/send",
                json=push_msgs,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=15,
            )
            data = resp.json().get("data", [])
            sent = sum(1 for d in data if isinstance(d, dict) and d.get("status") == "ok") \
                   if isinstance(data, list) else len(push_msgs)
        except Exception as e:
            return JSONResponse({"success": False, "error": f"Push failed: {e}"}, status_code=500)

    return {
        "success":       True,
        "probability":   round(prob, 3),
        "pct":           pct,
        "risk_level":    risk,
        "category":      category,
        "sent_to":       sent,
        "total_targets": len(push_msgs),
        "skipped_far":   skipped_far,
        "ml_model_used": _CYCLONE_MODEL is not None,
        "features":      features,
        "note":          "Demo complete. Scheduler continues with real data — no state changed.",
    }


# ── Dashboard HTML ─────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
def admin_dashboard():
    return HTMLResponse(content=ADMIN_HTML)


ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>JeevanSetu — Admin Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
:root{
  --bg:#f0f4f8;--sidebar:#ffffff;--card:#ffffff;
  --border:#e4eaf2;--border2:#d1dce8;
  --text:#0d1b2a;--text2:#374151;--muted:#6b7280;--muted2:#9ca3af;
  --primary:#2563eb;--primary-light:#eff6ff;--primary-mid:#bfdbfe;
  --red:#dc2626;--red-light:#fef2f2;--red-mid:#fecaca;
  --green:#16a34a;--green-light:#f0fdf4;--green-mid:#bbf7d0;
  --orange:#ea580c;--orange-light:#fff7ed;--orange-mid:#fed7aa;
  --purple:#7c3aed;--purple-light:#f5f3ff;--purple-mid:#ddd6fe;
  --shadow:0 1px 4px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04);
  --shadow-md:0 4px 20px rgba(0,0,0,.08),0 2px 8px rgba(0,0,0,.04);
  --r:14px;--r-sm:8px;--r-lg:20px;
}
body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);display:flex;height:100vh;overflow:hidden;-webkit-font-smoothing:antialiased;}

/* ── Sidebar ── */
.sidebar{width:256px;background:var(--sidebar);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0;overflow-y:auto;}
.sidebar::-webkit-scrollbar{width:0;}
.brand{display:flex;align-items:center;gap:12px;padding:20px 18px 16px;border-bottom:1px solid var(--border);}
.brand-icon{width:42px;height:42px;background:linear-gradient(135deg,#2563eb,#7c3aed);border-radius:13px;display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0;box-shadow:0 4px 14px rgba(37,99,235,.28);}
.brand-name{font-size:15px;font-weight:800;color:var(--text);letter-spacing:-.3px;}
.brand-sub{font-size:11px;color:var(--primary);margin-top:1px;font-weight:500;}
.nav{padding:12px 10px;flex:1;}
.nlabel{font-size:9.5px;font-weight:700;color:var(--muted2);letter-spacing:1px;text-transform:uppercase;padding:14px 10px 6px;}
.nitem{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:10px;cursor:pointer;font-size:13px;font-weight:500;color:var(--muted);transition:all .15s;margin-bottom:2px;text-decoration:none;position:relative;}
.nitem:hover{background:#f1f5fb;color:var(--text);}
.nitem.active{background:var(--primary-light);color:var(--primary);font-weight:600;}
.nitem.active::before{content:'';position:absolute;left:0;top:50%;transform:translateY(-50%);width:3px;height:22px;background:var(--primary);border-radius:0 3px 3px 0;}
.nbadge{margin-left:auto;background:var(--red);color:#fff;font-size:10px;font-weight:700;padding:2px 7px;border-radius:99px;}
.nbadge.z{background:#e5e7eb;color:var(--muted);}
.sfooter{padding:14px 10px;border-top:1px solid var(--border);}
.sfooter .nlabel{padding-top:0;}
.qbtn{display:flex;align-items:center;gap:8px;padding:9px 12px;border-radius:10px;font-size:12px;font-weight:600;cursor:pointer;border:1.5px solid var(--border2);background:#fff;width:100%;margin-bottom:8px;color:var(--text2);transition:all .15s;}
.qbtn:hover{border-color:var(--primary-mid);background:var(--primary-light);color:var(--primary);}

/* demo button */
.demo-btn{display:flex;align-items:center;gap:8px;padding:11px 14px;border-radius:12px;font-size:13px;font-weight:700;cursor:pointer;border:none;width:100%;color:#fff;background:linear-gradient(135deg,#dc2626,#ea580c);box-shadow:0 4px 14px rgba(220,38,38,.3);transition:all .18s;margin-bottom:8px;}
.demo-btn:hover{box-shadow:0 6px 20px rgba(220,38,38,.4);transform:translateY(-1px);}
.demo-btn svg{flex-shrink:0;}

/* ── Topbar ── */
.main{flex:1;display:flex;flex-direction:column;overflow:hidden;}
.topbar{height:60px;background:var(--sidebar);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;padding:0 26px;flex-shrink:0;}
.topbar-l{display:flex;align-items:center;gap:12px;}
.ptitle{font-size:16px;font-weight:700;color:var(--text);letter-spacing:-.2px;}
.live-pill{display:flex;align-items:center;gap:5px;background:var(--green-light);border:1.5px solid var(--green-mid);border-radius:99px;padding:4px 11px;font-size:11px;font-weight:600;color:var(--green);}
.ldot{width:7px;height:7px;background:var(--green);border-radius:50%;animation:blink 1.4s infinite;}
@keyframes blink{0%,100%{opacity:1;}50%{opacity:.2;}}
.topbar-r{display:flex;align-items:center;gap:10px;}
.clock{font-size:12px;font-weight:500;color:var(--muted);background:#f8fafc;border:1px solid var(--border);border-radius:8px;padding:5px 12px;}
.rbtn{display:flex;align-items:center;gap:6px;background:var(--primary);color:#fff;border:none;border-radius:9px;padding:7px 16px;font-size:12px;font-weight:600;cursor:pointer;font-family:'Inter',sans-serif;box-shadow:0 2px 8px rgba(37,99,235,.25);transition:all .15s;}
.rbtn:hover{background:#1d4ed8;box-shadow:0 4px 14px rgba(37,99,235,.35);}

/* ── Scrollable body ── */
.body{flex:1;overflow-y:auto;padding:22px 26px;}
.body::-webkit-scrollbar{width:6px;}
.body::-webkit-scrollbar-track{background:transparent;}
.body::-webkit-scrollbar-thumb{background:#dde3ed;border-radius:99px;}
.tsec{display:none;}.tsec.active{display:block;}

/* ── Stat cards ── */
.sgrid{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:20px;}
.scard{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:18px 20px;box-shadow:var(--shadow);transition:box-shadow .2s,transform .18s;cursor:default;}
.scard:hover{box-shadow:var(--shadow-md);transform:translateY(-2px);}
.sico{width:44px;height:44px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:20px;margin-bottom:12px;}
.slbl{font-size:11px;font-weight:500;color:var(--muted);margin-bottom:5px;}
.sval{font-size:30px;font-weight:800;color:var(--text);letter-spacing:-.8px;line-height:1;margin-bottom:5px;}
.smeta{font-size:11px;font-weight:500;}

/* ── Grid ── */
.g2{display:grid;grid-template-columns:1.45fr 1fr;gap:16px;margin-bottom:16px;}
.g2e{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;}
.g3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:16px;}

/* ── Panel ── */
.panel{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:20px;box-shadow:var(--shadow);}
.ph{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;}
.pt{font-size:14px;font-weight:700;color:var(--text);letter-spacing:-.1px;}
.ps{font-size:12px;color:var(--muted);}
.va{font-size:12px;font-weight:600;color:var(--primary);cursor:pointer;background:var(--primary-light);border:1px solid var(--primary-mid);border-radius:7px;padding:4px 11px;transition:all .14s;}
.va:hover{background:var(--primary-mid);}

/* ── Map ── */
#minimap,#fullmap{border-radius:12px;overflow:hidden;}
#minimap{height:310px;}
#fullmap{height:calc(100vh - 148px);}

/* ── Charts ── */
.cbox{position:relative;height:220px;}
.cboxlg{position:relative;height:260px;}
.dbox{position:relative;height:190px;display:flex;align-items:center;justify-content:center;}
.legrow{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:14px;}
.legitem{display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--text2);font-weight:500;}
.legdot{width:10px;height:10px;border-radius:3px;flex-shrink:0;}

/* ── Table ── */
.tw{overflow-x:auto;border-radius:10px;border:1px solid var(--border);}
table{width:100%;border-collapse:collapse;font-size:12.5px;}
thead{background:#f8fafc;}
th{padding:11px 14px;text-align:left;font-size:10px;font-weight:700;color:var(--muted);letter-spacing:.7px;text-transform:uppercase;border-bottom:1px solid var(--border);white-space:nowrap;}
td{padding:11px 14px;color:var(--text2);border-bottom:1px solid #f1f5f9;vertical-align:middle;}
tr:last-child td{border-bottom:none;}
tbody tr:hover td{background:#fafbfd;}
.tdn{font-weight:600;color:var(--text);}
.badge{display:inline-flex;align-items:center;gap:3px;padding:3px 9px;border-radius:6px;font-size:10.5px;font-weight:700;letter-spacing:.3px;white-space:nowrap;}
.ba{background:var(--red-light);color:var(--red);border:1px solid var(--red-mid);}
.br{background:var(--green-light);color:var(--green);border:1px solid var(--green-mid);}
.bd{background:var(--red-light);color:var(--red);border:1px solid var(--red-mid);}
.bs{background:var(--orange-light);color:var(--orange);border:1px solid var(--orange-mid);}
.bi{background:var(--purple-light);color:var(--purple);border:1px solid var(--purple-mid);}
.mapbtn{display:inline-flex;align-items:center;gap:4px;background:var(--primary-light);color:var(--primary);border:1.5px solid var(--primary-mid);border-radius:7px;padding:4px 10px;font-size:11px;font-weight:600;cursor:pointer;text-decoration:none;transition:all .14s;}
.mapbtn:hover{background:var(--primary-mid);}

/* ── Areas bars ── */
.brow{display:flex;align-items:center;gap:10px;margin-bottom:13px;}
.blbl{font-size:12px;font-weight:500;color:var(--text2);width:130px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.btrack{flex:1;height:8px;background:#f1f5f9;border-radius:99px;overflow:hidden;}
.bfill{height:100%;border-radius:99px;transition:width .7s cubic-bezier(.4,0,.2,1);}
.bnum{font-size:12px;font-weight:700;color:var(--text);width:24px;text-align:right;}

/* ── User CARDS ── */
.ucards{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px;}
.ucard{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:18px;box-shadow:var(--shadow);transition:box-shadow .2s,transform .18s;display:flex;flex-direction:column;gap:12px;}
.ucard:hover{box-shadow:var(--shadow-md);transform:translateY(-2px);}
.ucard-top{display:flex;align-items:center;gap:12px;}
.uav{width:46px;height:46px;border-radius:14px;background:linear-gradient(135deg,var(--primary-light),var(--primary-mid));display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:800;color:var(--primary);flex-shrink:0;}
.uname{font-size:14px;font-weight:700;color:var(--text);}
.uphone{font-size:12px;color:var(--muted);margin-top:2px;font-weight:500;}
.utags{display:flex;gap:6px;flex-wrap:wrap;}
.utag{font-size:10px;font-weight:700;padding:3px 9px;border-radius:6px;display:flex;align-items:center;gap:3px;}
.ton{background:var(--green-light);color:var(--green);border:1px solid var(--green-mid);}
.toff{background:#f8fafc;color:var(--muted2);border:1px solid var(--border);}
.uloc{display:flex;align-items:flex-start;gap:7px;background:#f8fafc;border-radius:9px;padding:9px 11px;}
.uloc-icon{font-size:14px;flex-shrink:0;margin-top:1px;}
.uloc-text{font-size:11.5px;color:var(--text2);line-height:1.5;font-weight:500;}
.uloc-coords{font-size:10.5px;color:var(--muted);margin-top:2px;font-family:monospace;}
.uloc-link{font-size:11px;color:var(--primary);font-weight:600;text-decoration:none;margin-top:4px;display:inline-flex;align-items:center;gap:3px;}
.uloc-link:hover{text-decoration:underline;}

/* ── Analytics ── */
.acard{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:20px;box-shadow:var(--shadow);}
.acard .albl{font-size:10px;font-weight:700;color:var(--muted);letter-spacing:.8px;text-transform:uppercase;margin-bottom:14px;}
.drow{display:flex;align-items:center;gap:10px;margin-bottom:11px;}
.dlbl{font-size:12px;font-weight:500;color:var(--text2);width:100px;flex-shrink:0;}
.dtrack{flex:1;height:7px;background:#f1f5f9;border-radius:99px;overflow:hidden;}
.dfill{height:100%;border-radius:99px;}
.dval{font-size:12px;font-weight:700;color:var(--text);width:28px;text-align:right;}
.rblock{display:flex;align-items:center;gap:12px;padding:14px;border-radius:12px;margin-bottom:10px;}
.rnum{font-size:26px;font-weight:800;line-height:1;}
.rlbl{font-size:11px;font-weight:500;margin-top:3px;}

/* ── Empty ── */
.empty{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px;color:var(--muted);gap:8px;font-size:13px;text-align:center;}
.eico{font-size:32px;margin-bottom:4px;}

/* ══════════════════════════════════════════
   DEMO MODAL
══════════════════════════════════════════ */
.modal-overlay{
  position:fixed;inset:0;background:rgba(0,0,0,.45);
  display:flex;align-items:center;justify-content:center;
  z-index:9999;opacity:0;pointer-events:none;transition:opacity .2s;
  backdrop-filter:blur(3px);
}
.modal-overlay.open{opacity:1;pointer-events:all;}
.modal{
  background:#fff;border-radius:20px;width:600px;max-width:95vw;
  max-height:90vh;overflow-y:auto;box-shadow:0 24px 64px rgba(0,0,0,.18);
  transform:scale(.96) translateY(10px);transition:transform .22s;
}
.modal-overlay.open .modal{transform:scale(1) translateY(0);}
.modal-head{
  display:flex;align-items:center;justify-content:space-between;
  padding:22px 24px 0;
}
.modal-title{font-size:17px;font-weight:800;color:var(--text);}
.modal-sub{font-size:12px;color:var(--muted);margin-top:3px;}
.mclose{width:32px;height:32px;border-radius:8px;border:1.5px solid var(--border);background:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:16px;color:var(--muted);transition:all .14s;}
.mclose:hover{background:#fef2f2;border-color:var(--red-mid);color:var(--red);}
.modal-body{padding:20px 24px;}
.mparam-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px;}
.mfield{display:flex;flex-direction:column;gap:5px;}
.mfield label{font-size:11px;font-weight:700;color:var(--muted);letter-spacing:.5px;text-transform:uppercase;}
.mfield input{
  padding:9px 12px;border-radius:9px;border:1.5px solid var(--border);
  font-size:13px;font-family:'Inter',sans-serif;color:var(--text);
  background:#fafbfd;transition:border-color .15s;
}
.mfield input:focus{outline:none;border-color:var(--primary);background:#fff;}
.mfield .hint{font-size:10.5px;color:var(--muted2);}
.mtarget{margin-bottom:16px;}
.msend-btn{
  width:100%;padding:13px;border-radius:12px;border:none;cursor:pointer;
  font-family:'Inter',sans-serif;font-size:14px;font-weight:700;color:#fff;
  background:linear-gradient(135deg,#dc2626,#ea580c);
  box-shadow:0 4px 16px rgba(220,38,38,.35);
  transition:all .18s;display:flex;align-items:center;justify-content:center;gap:10px;
}
.msend-btn:hover{box-shadow:0 6px 22px rgba(220,38,38,.45);transform:translateY(-1px);}
.msend-btn:disabled{opacity:.6;pointer-events:none;}
.mresult{
  margin-top:16px;padding:14px 16px;border-radius:12px;
  font-size:13px;font-weight:500;line-height:1.6;display:none;
}
.mresult.ok{background:var(--green-light);border:1px solid var(--green-mid);color:#14532d;}
.mresult.err{background:var(--red-light);border:1px solid var(--red-mid);color:#7f1d1d;}
.prob-bar-wrap{background:#f1f5f9;border-radius:8px;padding:12px 14px;margin-bottom:16px;display:none;}
.prob-label{font-size:11px;font-weight:700;color:var(--muted);margin-bottom:7px;letter-spacing:.5px;}
.prob-track{height:10px;background:#e5e7eb;border-radius:99px;overflow:hidden;}
.prob-fill{height:100%;border-radius:99px;background:linear-gradient(90deg,#22c55e,#eab308,#ef4444);transition:width .6s cubic-bezier(.4,0,.2,1);}
.prob-val{font-size:22px;font-weight:800;margin-top:8px;}
</style>
</head>
<body>

<!-- ══════════════ SIDEBAR ══════════════ -->
<aside class="sidebar">
  <div class="brand">
    <div class="brand-icon">🌊</div>
    <div>
      <div class="brand-name">JeevanSetu</div>
      <div class="brand-sub">Admin Dashboard</div>
    </div>
  </div>

  <nav class="nav">
    <div class="nlabel">Main</div>
    <a class="nitem active" onclick="gotoTab('overview',this)">
      <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
      Overview
    </a>
    <a class="nitem" onclick="gotoTab('sos',this)">
      <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      SOS Requests
      <span class="nbadge z" id="nbadge">0</span>
    </a>
    <a class="nitem" onclick="gotoTab('map',this)">
      <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/></svg>
      Live Map
    </a>
    <div class="nlabel">People</div>
    <a class="nitem" onclick="gotoTab('users',this)">
      <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
      Users
    </a>
    <div class="nlabel">Insights</div>
    <a class="nitem" onclick="gotoTab('analytics',this)">
      <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
      Analytics
    </a>
    <div class="nlabel">Hazards</div>
    <a class="nitem" onclick="gotoTab('cyclone',this)">
      <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 8c-2.2 0-4 1.8-4 4s1.8 4 4 4"/><path d="M12 8c1.1 0 2 .4 2.8 1"/><path d="M16 12c0 1.1-.4 2.1-1 2.8"/></svg>
      Cyclone
    </a>
  </nav>

  <div class="sfooter">
    <div class="nlabel">Quick Actions</div>
    <button class="demo-btn" onclick="openDemo()">
      <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
      Demo Flood Alert
    </button>
    <button class="demo-btn" style="background:linear-gradient(135deg,#7c3aed,#4f46e5);box-shadow:0 4px 14px rgba(124,58,237,.3)" onclick="openCycloneDemo()">
      <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 8c-2.2 0-4 1.8-4 4s1.8 4 4 4"/></svg>
      Demo Cyclone Alert
    </button>
    <button class="qbtn" onclick="window.open('/api/sos/dashboard','_blank')">
      <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/></svg>
      Rescue Dashboard ↗
    </button>
    <button class="qbtn" onclick="window.open('/docs','_blank')">
      <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      API Docs ↗
    </button>
  </div>
</aside>

<!-- ══════════════ MAIN ══════════════ -->
<div class="main">
  <header class="topbar">
    <div class="topbar-l">
      <span class="ptitle" id="ptitle">Overview</span>
      <div class="live-pill"><span class="ldot"></span>Live</div>
    </div>
    <div class="topbar-r">
      <div class="clock" id="clock">—</div>
      <button class="rbtn" onclick="loadData()">
        <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
        Refresh
      </button>
    </div>
  </header>

  <div class="body">

    <!-- ══ OVERVIEW ══ -->
    <div class="tsec active" id="tab-overview">
      <div class="sgrid">
        <div class="scard"><div class="sico" style="background:var(--red-light)">🚨</div><div class="slbl">Total SOS Requests</div><div class="sval" id="s-total">—</div><div class="smeta" style="color:var(--muted)">All time</div></div>
        <div class="scard"><div class="sico" style="background:var(--orange-light)">🔴</div><div class="slbl">Active SOS</div><div class="sval" id="s-active">—</div><div class="smeta" id="s-active-m" style="color:var(--red)">Needs response</div></div>
        <div class="scard"><div class="sico" style="background:var(--green-light)">✅</div><div class="slbl">Resolved SOS</div><div class="sval" id="s-resolved">—</div><div class="smeta" style="color:var(--green)">Successfully closed</div></div>
        <div class="scard"><div class="sico" style="background:var(--primary-light)">👥</div><div class="slbl">Registered Users</div><div class="sval" id="s-users">—</div><div class="smeta" id="s-token-m" style="color:var(--muted)">— push-enabled</div></div>
        <div class="scard"><div class="sico" style="background:var(--purple-light)">🔔</div><div class="slbl">Alerts Sent</div><div class="sval" id="s-alerts">—</div><div class="smeta" id="s-alerts-m" style="color:var(--muted)">—</div></div>
      </div>
      <div class="g2">
        <div class="panel"><div class="ph"><span class="pt">Live SOS Map</span><span class="ps" id="pincount">0 pins</span></div><div id="minimap"></div></div>
        <div class="panel"><div class="ph"><span class="pt">SOS by Category</span></div><div class="dbox"><canvas id="donutChart"></canvas></div><div class="legrow" id="donut-leg"></div></div>
      </div>
      <div class="g2">
        <div class="panel"><div class="ph"><span class="pt">SOS Requests — Last 7 Days</span></div><div class="cbox"><canvas id="trendChart"></canvas></div></div>
        <div class="panel"><div class="ph"><span class="pt">Top Affected Areas</span></div><div id="areas"></div></div>
      </div>
      <div class="panel" style="margin-bottom:0">
        <div class="ph"><span class="pt">Recent SOS Requests</span><a class="va" onclick="gotoTab('sos',null)">View all →</a></div>
        <div class="tw"><table><thead><tr><th>Name</th><th>Category</th><th>Location</th><th>Status</th><th>Notified</th><th>Time</th><th></th></tr></thead><tbody id="tb-recent"></tbody></table></div>
      </div>
    </div>

    <!-- ══ SOS ══ -->
    <div class="tsec" id="tab-sos">
      <div class="panel" style="margin-bottom:0">
        <div class="ph"><span class="pt">All SOS Requests</span><span class="ps" id="sos-lbl">—</span></div>
        <div class="tw"><table><thead><tr><th>#</th><th>Name</th><th>Phone</th><th>Category</th><th>Location</th><th>Status</th><th>Notified</th><th>Time</th><th></th></tr></thead><tbody id="tb-all"></tbody></table></div>
      </div>
    </div>

    <!-- ══ MAP ══ -->
    <div class="tsec" id="tab-map">
      <div class="panel" style="margin-bottom:0;padding:16px">
        <div class="ph"><span class="pt">Live SOS Location Map</span><span class="ps">🔴 Active &nbsp;&nbsp;🟢 Resolved</span></div>
        <div id="fullmap"></div>
      </div>
    </div>

    <!-- ══ USERS ══ -->
    <div class="tsec" id="tab-users">
      <div class="sgrid" style="grid-template-columns:repeat(3,1fr);margin-bottom:20px">
        <div class="scard"><div class="sico" style="background:var(--primary-light)">👤</div><div class="slbl">Total Registered</div><div class="sval" id="u-total">—</div></div>
        <div class="scard"><div class="sico" style="background:var(--green-light)">🔔</div><div class="slbl">Push Token Active</div><div class="sval" id="u-token">—</div><div class="smeta" style="color:var(--green)">Can receive alerts</div></div>
        <div class="scard"><div class="sico" style="background:var(--orange-light)">📍</div><div class="slbl">Location Saved</div><div class="sval" id="u-loc">—</div><div class="smeta" style="color:var(--green)">Flood monitoring on</div></div>
      </div>
      <div id="ucards-wrap"><div class="empty"><div class="eico">⏳</div>Loading users…</div></div>
    </div>

    <!-- ══ ANALYTICS ══ -->
    <div class="tsec" id="tab-analytics">
      <div class="g3">
        <div class="acard">
          <div class="albl">Alert Distribution</div>
          <div style="font-size:36px;font-weight:800;letter-spacing:-1px;line-height:1" id="a-total">—</div>
          <div style="font-size:11px;color:var(--muted);margin-bottom:16px">Total alerts sent</div>
          <div class="drow"><div class="dlbl">🚨 Flood</div><div class="dtrack"><div class="dfill" id="bar-flood" style="background:var(--red);width:0%"></div></div><div class="dval" id="a-flood">—</div></div>
          <div class="drow"><div class="dlbl">🌤️ Weather</div><div class="dtrack"><div class="dfill" id="bar-weather" style="background:var(--primary);width:0%"></div></div><div class="dval" id="a-weather">—</div></div>
        </div>
        <div class="acard" style="text-align:center">
          <div class="albl">User Reach</div>
          <div style="font-size:54px;font-weight:800;color:var(--primary);letter-spacing:-2px;line-height:1;margin:8px 0 4px" id="reach-pct">—</div>
          <div style="font-size:12px;color:var(--muted);margin-bottom:16px">of users receive flood alerts</div>
          <div style="display:flex;gap:10px">
            <div style="flex:1;background:var(--primary-light);border:1px solid var(--primary-mid);border-radius:10px;padding:12px"><div style="font-size:22px;font-weight:800;color:var(--primary)" id="reach-token">—</div><div style="font-size:10px;color:var(--muted);margin-top:2px">With Token</div></div>
            <div style="flex:1;background:var(--orange-light);border:1px solid var(--orange-mid);border-radius:10px;padding:12px"><div style="font-size:22px;font-weight:800;color:var(--orange)" id="reach-notified">—</div><div style="font-size:10px;color:var(--muted);margin-top:2px">Total Notified</div></div>
          </div>
        </div>
        <div class="acard">
          <div class="albl">SOS Response Rate</div>
          <div class="rblock" style="background:var(--green-light);border:1px solid var(--green-mid)"><div><div class="rnum" style="color:var(--green)" id="rate-res">—</div><div class="rlbl" style="color:var(--green)">Resolved</div></div><div style="font-size:28px;margin-left:auto">✅</div></div>
          <div class="rblock" style="background:var(--red-light);border:1px solid var(--red-mid)"><div><div class="rnum" style="color:var(--red)" id="rate-act">—</div><div class="rlbl" style="color:var(--red)">Still Active</div></div><div style="font-size:28px;margin-left:auto">🚨</div></div>
          <div style="text-align:center;font-size:12px;color:var(--muted);font-weight:500" id="rate-pct">—</div>
        </div>
      </div>
      <div class="panel" style="margin-bottom:0"><div class="ph"><span class="pt">7-Day SOS Trend</span></div><div class="cboxlg"><canvas id="analyticsChart"></canvas></div></div>
    </div>

    <!-- ══ CYCLONE ══ -->
    <div class="tsec" id="tab-cyclone">
      <div class="sgrid" style="grid-template-columns:repeat(4,1fr);margin-bottom:20px">
        <div class="scard"><div class="sico" style="background:var(--purple-light)">🌀</div><div class="slbl">Cyclone Alerts Sent</div><div class="sval" id="cy-alerts">—</div><div class="smeta" style="color:var(--muted)">All time</div></div>
        <div class="scard"><div class="sico" style="background:var(--primary-light)">🤖</div><div class="slbl">ML Model</div><div class="sval" id="cy-ml" style="font-size:18px;margin-top:4px">—</div><div class="smeta" id="cy-ml-m" style="color:var(--muted)">ERA5 trained</div></div>
        <div class="scard"><div class="sico" style="background:var(--orange-light)">📡</div><div class="slbl">Data Sources</div><div class="sval" style="font-size:15px;font-weight:700;margin-top:4px;line-height:1.3">Open-Meteo<br>+ GDACS</div></div>
        <div class="scard"><div class="sico" style="background:var(--green-light)">🗓️</div><div class="slbl">Training Events</div><div class="sval">38</div><div class="smeta" style="color:var(--muted)">2007–2024 landfalls</div></div>
      </div>

      <!-- IMD scale reference panel -->
      <div class="g2e" style="margin-bottom:16px">
        <div class="panel">
          <div class="ph"><span class="pt">🌀 IMD Cyclone Scale</span><span class="ps">India Meteorological Department</span></div>
          <table style="font-size:12px">
            <thead><tr><th>Category</th><th>Wind Speed (km/h)</th><th>Risk</th></tr></thead>
            <tbody>
              <tr><td class="tdn">Depression</td><td>31 – 51</td><td><span class="badge" style="background:#f0fdf4;color:#166534;border:1px solid #86efac">Very Low</span></td></tr>
              <tr><td class="tdn">Deep Depression</td><td>52 – 62</td><td><span class="badge" style="background:#f0fdf4;color:#166534;border:1px solid #86efac">Low</span></td></tr>
              <tr><td class="tdn">Cyclonic Storm</td><td>63 – 88</td><td><span class="badge" style="background:#fffbeb;color:#92400e;border:1px solid #fcd34d">Moderate</span></td></tr>
              <tr><td class="tdn">Severe Cyclonic Storm</td><td>89 – 117</td><td><span class="badge" style="background:#fff1f2;color:#991b1b;border:1px solid #fca5a5">High</span></td></tr>
              <tr><td class="tdn">Very Severe Cyclonic Storm</td><td>118 – 167</td><td><span class="badge" style="background:#fff1f2;color:#991b1b;border:1px solid #fca5a5">High</span></td></tr>
              <tr><td class="tdn">Extremely Severe</td><td>168 – 221</td><td><span class="badge" style="background:#fdf4ff;color:#4a044e;border:1px solid #e879f9">Extreme</span></td></tr>
              <tr><td class="tdn">Super Cyclone</td><td>≥ 222</td><td><span class="badge" style="background:#fdf4ff;color:#4a044e;border:1px solid #e879f9">Extreme</span></td></tr>
            </tbody>
          </table>
        </div>
        <div class="panel">
          <div class="ph"><span class="pt">📅 Cyclone Season Calendar</span><span class="ps">IMD seasonal risk multipliers</span></div>
          <div id="season-chart-wrap" style="display:grid;grid-template-columns:repeat(6,1fr);gap:6px;margin-top:4px">
            <!-- Rendered by JS -->
          </div>
          <div style="margin-top:14px;font-size:11px;color:var(--muted);line-height:1.6">
            <strong>Bay of Bengal:</strong> Peak Apr–Jun &amp; Oct–Dec<br>
            <strong>Arabian Sea:</strong> Peak May–Jun &amp; Oct–Nov
          </div>
        </div>
      </div>

      <!-- Recent cyclone alerts -->
      <div class="panel" style="margin-bottom:16px">
        <div class="ph"><span class="pt">Recent Cyclone Alerts</span><span class="ps" id="cy-alerts-lbl">from database</span></div>
        <div id="cy-alerts-empty" class="empty"><div class="eico">🌀</div>No cyclone alerts sent yet</div>
      </div>

      <!-- Model features info -->
      <div class="panel" style="margin-bottom:0">
        <div class="ph"><span class="pt">🤖 ML Model Features</span><span class="ps">VotingClassifier: XGBoost + GradientBoosting + RandomForest</span></div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:4px">
          <div style="background:#f8fafc;border-radius:10px;padding:12px">
            <div style="font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;margin-bottom:8px">Primary Signals</div>
            <div style="font-size:12px;color:var(--text2);line-height:2">💨 Wind Gusts (km/h)<br>📉 Surface Pressure (hPa)<br>⬇️ Pressure Drop / 6h</div>
          </div>
          <div style="background:#f8fafc;border-radius:10px;padding:12px">
            <div style="font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;margin-bottom:8px">Atmospheric</div>
            <div style="font-size:12px;color:var(--text2);line-height:2">⚡ CAPE (J/kg)<br>🌧️ Precipitation (mm)<br>💧 Relative Humidity (%)</div>
          </div>
          <div style="background:#f8fafc;border-radius:10px;padding:12px">
            <div style="font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;margin-bottom:8px">Geospatial</div>
            <div style="font-size:12px;color:var(--text2);line-height:2">🌊 Coastal Distance (km)<br>📅 Season Factor<br>🌐 Latitude</div>
          </div>
        </div>
        <div style="margin-top:12px;padding:10px 14px;background:var(--purple-light);border-radius:10px;border:1px solid var(--purple-mid);font-size:12px;color:#4c1d95">
          <strong>Training data:</strong> 38 documented Indian Ocean cyclone landfalls (Bay of Bengal + Arabian Sea, 2007–2024) + 62 control clear-weather days · ERA5 historical reanalysis via Open-Meteo
        </div>
      </div>
    </div>

  </div><!-- /body -->
</div><!-- /main -->

<!-- ══════════════ DEMO MODAL ══════════════ -->
<div class="modal-overlay" id="demoOverlay" onclick="if(event.target===this)closeDemo()">
  <div class="modal">
    <div class="modal-head">
      <div>
        <div class="modal-title">🎯 Demo Flood Alert</div>
        <div class="modal-sub">Manually enter flood parameters → runs ML model → sends real push notification once → scheduler resumes real data</div>
      </div>
      <button class="mclose" onclick="closeDemo()">✕</button>
    </div>
    <div class="modal-body">

      <!-- Live probability preview bar -->
      <div class="prob-bar-wrap" id="probWrap">
        <div class="prob-label">ML FLOOD PROBABILITY</div>
        <div class="prob-track"><div class="prob-fill" id="probFill" style="width:0%"></div></div>
        <div class="prob-val" id="probVal">—</div>
      </div>

      <div class="mparam-grid">
        <div class="mfield">
          <label>Rainfall 1h (mm/h)</label>
          <input type="number" id="p-r1" value="35" step="0.1" oninput="previewProb()">
          <div class="hint">Peak hourly rain. &gt;20 = heavy</div>
        </div>
        <div class="mfield">
          <label>Rainfall 24h (mm)</label>
          <input type="number" id="p-r24" value="120" step="1" oninput="previewProb()">
          <div class="hint">Total in last 24h. &gt;80 = saturated</div>
        </div>
        <div class="mfield">
          <label>Humidity (%)</label>
          <input type="number" id="p-hum" value="92" step="1" min="0" max="100" oninput="previewProb()">
          <div class="hint">&gt;88% = very high</div>
        </div>
        <div class="mfield">
          <label>Temperature (°C)</label>
          <input type="number" id="p-tmp" value="27" step="0.1" oninput="previewProb()">
        </div>
        <div class="mfield">
          <label>Soil Moisture (0–1)</label>
          <input type="number" id="p-sm" value="0.85" step="0.01" min="0" max="1" oninput="previewProb()">
          <div class="hint">&gt;0.75 = near saturated</div>
        </div>
        <div class="mfield">
          <label>Elevation (m)</label>
          <input type="number" id="p-elev" value="18" step="1" oninput="previewProb()">
          <div class="hint">&lt;30m = flood-prone zone</div>
        </div>
        <div class="mfield">
          <label>Drainage Score (0–10)</label>
          <input type="number" id="p-drain" value="2" step="0.1" min="0" max="10" oninput="previewProb()">
          <div class="hint">&lt;3 = poor drainage</div>
        </div>
        <div class="mfield">
          <label>Slope (degrees)</label>
          <input type="number" id="p-slope" value="0.4" step="0.1" oninput="previewProb()">
          <div class="hint">&lt;1° = flat terrain</div>
        </div>
        <div class="mfield">
          <label>Pressure (hPa)</label>
          <input type="number" id="p-pres" value="1004" step="0.1" oninput="previewProb()">
        </div>
        <div class="mfield">
          <label>📍 Demo Latitude</label>
          <input type="number" id="p-lat" value="12.9716" step="0.0001" placeholder="e.g. 12.9716">
          <div class="hint">Flood epicentre lat — only nearby users notified</div>
        </div>
        <div class="mfield">
          <label>📍 Demo Longitude</label>
          <input type="number" id="p-lon" value="77.5946" step="0.0001" placeholder="e.g. 77.5946">
          <div class="hint">Flood epicentre lon</div>
        </div>
        <div class="mfield">
          <label>📡 Radius (km)</label>
          <input type="number" id="p-radius" value="5" step="0.5" min="0.5" max="50">
          <div class="hint">Notify users within this distance of demo location</div>
        </div>
        <div class="mfield mtarget">
          <label>🎯 Target Phone (optional)</label>
          <input type="text" id="p-phone" placeholder="Leave empty = use radius above">
          <div class="hint">+91XXXXXXXXXX — overrides radius, sends to this person only</div>
        </div>
      </div>

      <button class="msend-btn" id="sendBtn" onclick="sendDemo()">
        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
        Send Demo Flood Alert Now
      </button>

      <div class="mresult" id="mresult"></div>
    </div>
  </div>
</div>

<!-- ══════════════ CYCLONE DEMO MODAL ══════════════ -->
<div class="modal-overlay" id="cycloneDemoOverlay" onclick="if(event.target===this)closeCycloneDemo()">
  <div class="modal">
    <div class="modal-head">
      <div>
        <div class="modal-title">🌀 Demo Cyclone Alert</div>
        <div class="modal-sub">Enter cyclone parameters → runs ML model → sends real push notification once → scheduler resumes real data</div>
      </div>
      <button class="mclose" onclick="closeCycloneDemo()">✕</button>
    </div>
    <div class="modal-body">
      <div class="prob-bar-wrap" id="cy-probWrap">
        <div class="prob-label">CYCLONE PROBABILITY</div>
        <div class="prob-track"><div class="prob-fill" id="cy-probFill" style="width:0%;background:linear-gradient(90deg,#7c3aed,#dc2626)"></div></div>
        <div class="prob-val" id="cy-probVal">—</div>
      </div>
      <div class="mparam-grid">
        <div class="mfield">
          <label>Wind Gusts (km/h)</label>
          <input type="number" id="cy-gusts" value="95" step="1">
          <div class="hint">63+ = Cyclonic Storm, 89+ = Severe</div>
        </div>
        <div class="mfield">
          <label>Surface Pressure (hPa)</label>
          <input type="number" id="cy-pres" value="975" step="0.5">
          <div class="hint">&lt;980 = severe cyclone eye</div>
        </div>
        <div class="mfield">
          <label>Pressure Drop / 6h (hPa)</label>
          <input type="number" id="cy-drop" value="6" step="0.5">
          <div class="hint">≥4 = rapid deepening</div>
        </div>
        <div class="mfield">
          <label>CAPE (J/kg)</label>
          <input type="number" id="cy-cape" value="1500" step="100">
          <div class="hint">1000+ = high convective instability</div>
        </div>
        <div class="mfield">
          <label>📍 Demo Latitude</label>
          <input type="number" id="cy-lat" value="13.0827" step="0.0001">
          <div class="hint">Only users within radius_km notified</div>
        </div>
        <div class="mfield">
          <label>📍 Demo Longitude</label>
          <input type="number" id="cy-lon" value="80.2707" step="0.0001">
        </div>
        <div class="mfield">
          <label>📡 Radius (km)</label>
          <input type="number" id="cy-radius" value="200" step="10" min="1" max="1000">
          <div class="hint">Cyclone radius is much larger than flood</div>
        </div>
        <div class="mfield">
          <label>🎯 Target Phone (optional)</label>
          <input type="text" id="cy-phone" placeholder="Leave empty = use radius above">
          <div class="hint">+91XXXXXXXXXX — overrides radius</div>
        </div>
      </div>
      <button class="msend-btn" id="cy-sendBtn" style="background:linear-gradient(135deg,#7c3aed,#4f46e5);box-shadow:0 4px 16px rgba(124,58,237,.35)" onclick="sendCycloneDemo()">
        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 8c-2.2 0-4 1.8-4 4s1.8 4 4 4"/></svg>
        Send Demo Cyclone Alert Now
      </button>
      <div class="mresult" id="cy-mresult"></div>
    </div>
  </div>
</div>

<script>
// ── State ─────────────────────────────────────────────────────────────────────
let D = null, mapMini = null, mapFull = null;
let chDonut = null, chTrend = null, chAna = null;
const CC = {'In Danger':'#dc2626','Stranded':'#ea580c','Injured':'#7c3aed'};
const AC = ['#2563eb','#7c3aed','#ea580c','#16a34a','#ca8a04','#0891b2'];

// ── Clock ─────────────────────────────────────────────────────────────────────
function tick(){ document.getElementById('clock').textContent = new Date().toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:true}); }
tick(); setInterval(tick,1000);

// ── Tabs ──────────────────────────────────────────────────────────────────────
const TITLES={overview:'Overview',sos:'SOS Requests',map:'Live Map',users:'Users',analytics:'Analytics',cyclone:'Cyclone Intelligence'};
function gotoTab(id,el){
  document.querySelectorAll('.tsec').forEach(s=>s.classList.remove('active'));
  document.querySelectorAll('.nitem').forEach(n=>n.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  document.getElementById('ptitle').textContent = TITLES[id]||id;
  if(el) el.classList.add('active');
  if(id==='map'&&!mapFull&&D) setTimeout(()=>{mapFull=buildMap('fullmap',true);},80);
}

// ── Admin key (stored in localStorage) ───────────────────────────────────────
function getKey(){ return localStorage.getItem('js_admin_key')||''; }
function requireAuth(){
  const k=getKey();
  if(!k){
    const entered=prompt('Enter Admin Key to access the dashboard:');
    if(!entered){document.body.innerHTML='<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:Inter,sans-serif;font-size:18px;color:#64748b;">Access denied.</div>';return false;}
    localStorage.setItem('js_admin_key',entered);
  }
  return true;
}

// ── Data load ─────────────────────────────────────────────────────────────────
async function loadData(){
  if(!requireAuth())return;
  try{
    const r=await fetch('/admin/data?admin_key='+encodeURIComponent(getKey())); D=await r.json();
    if(r.status===403){localStorage.removeItem('js_admin_key');alert('Invalid admin key. Please refresh and try again.');return;}

    if(D.error){console.error(D.error);return;}
    renderAll();
  }catch(e){console.error(e);}
}
function renderAll(){
  renderStats(); renderMiniMap(); renderDonut(); renderTrend();
  renderAreas(); renderRecentTbl(); renderAllTbl(); renderUsers(); renderAnalytics();
  renderCyclone();
  const b=document.getElementById('nbadge');
  b.textContent=D.active_sos||0;
  b.className='nbadge'+(D.active_sos>0?'':' z');
}

// ── Stats ─────────────────────────────────────────────────────────────────────
function renderStats(){
  $('s-total',D.total_sos); $('s-active',D.active_sos); $('s-resolved',D.resolved_sos);
  $('s-users',D.total_users); $('s-alerts',D.total_alerts);
  const am=document.getElementById('s-active-m');
  am.textContent=D.active_sos>0?`${D.active_sos} need response`:'All clear ✅';
  am.style.color=D.active_sos>0?'var(--red)':'var(--green)';
  $('s-token-m',`${D.users_with_token} push-enabled`);
  $('s-alerts-m',`${D.flood_alerts} flood · ${D.weather_alerts} weather`);
  $('u-total',D.total_users); $('u-token',D.users_with_token); $('u-loc',D.users_with_loc);
  $('a-total',D.total_alerts); $('a-flood',D.flood_alerts); $('a-weather',D.weather_alerts);
  $('rate-res',D.resolved_sos); $('rate-act',D.active_sos);
  $('reach-token',D.users_with_token); $('reach-notified',D.total_notified);
  const rP=D.total_sos>0?Math.round((D.resolved_sos/D.total_sos)*100):0;
  $('rate-pct',`${rP}% resolution rate`);
  const uP=D.total_users>0?Math.round((D.users_with_token/D.total_users)*100):0;
  $('reach-pct',uP+'%');
  const t=D.total_alerts||1;
  document.getElementById('bar-flood').style.width=Math.round((D.flood_alerts/t)*100)+'%';
  document.getElementById('bar-weather').style.width=Math.round((D.weather_alerts/t)*100)+'%';
}

// ── Maps ──────────────────────────────────────────────────────────────────────
function buildMap(elId, scroll){
  const pins=D.map_pins||[];
  const m=L.map(elId,{zoomControl:true,scrollWheelZoom:scroll}).setView([20.5,78.9],4);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap'}).addTo(m);
  const v=pins.filter(p=>p.lat&&p.lon);
  const pc=document.getElementById('pincount');
  if(pc) pc.textContent=v.length+' pins';
  v.forEach(p=>{
    const active=p.status==='active';
    const c=active?'#dc2626':'#16a34a';
    const icon=L.divIcon({
      className:'',
      html:`<div style="position:relative;width:22px;height:22px">
              <div style="position:absolute;inset:0;border-radius:50%;background:${c};opacity:.2;animation:ripple 1.8s infinite;"></div>
              <div style="position:absolute;inset:3px;border-radius:50%;background:${c};border:2.5px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.25);"></div>
            </div>
            <style>@keyframes ripple{0%{transform:scale(1);opacity:.3}100%{transform:scale(2.2);opacity:0}}</style>`,
      iconSize:[22,22],iconAnchor:[11,11],
    });
    L.marker([p.lat,p.lon],{icon}).addTo(m).bindPopup(`
      <div style="font-family:Inter,sans-serif;min-width:200px;padding:2px">
        <div style="font-weight:700;font-size:14px;color:#0d1b2a;margin-bottom:6px">${p.name}</div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">
          <span style="background:${active?'#fef2f2':'#f0fdf4'};color:${c};border:1px solid ${active?'#fecaca':'#bbf7d0'};padding:2px 8px;border-radius:5px;font-size:10px;font-weight:700">${active?'🔴':'✅'} ${p.status.toUpperCase()}</span>
          <span style="background:#f1f5f9;color:#6b7280;padding:2px 8px;border-radius:5px;font-size:10px;font-weight:600">${p.category}</span>
        </div>
        <div style="font-size:12px;color:#374151;margin-bottom:4px">📍 ${p.address||'—'}</div>
        <div style="font-size:11px;color:#9ca3af;margin-bottom:6px">📞 ${p.phone||'—'} &nbsp;·&nbsp; 👥 ${p.notified||0} notified</div>
        <div style="font-size:11px;color:#9ca3af;margin-bottom:8px">🕐 ${p.time||'—'}</div>
        ${p.maps_url?`<a href="${p.maps_url}" target="_blank" style="display:inline-flex;align-items:center;gap:4px;background:#eff6ff;color:#2563eb;border:1px solid #bfdbfe;border-radius:6px;padding:5px 10px;font-size:11px;font-weight:600;text-decoration:none">🗺 Open in Google Maps</a>`:''}
      </div>
    `,{maxWidth:260});
  });
  if(v.length>0){
    const lats=v.map(p=>p.lat),lons=v.map(p=>p.lon);
    m.fitBounds([[Math.min(...lats)-.5,Math.min(...lons)-.5],[Math.max(...lats)+.5,Math.max(...lons)+.5]],{padding:[30,30]});
  }
  return m;
}
function renderMiniMap(){ if(!mapMini) mapMini=buildMap('minimap',false); }

// ── Donut ─────────────────────────────────────────────────────────────────────
function renderDonut(){
  const cats=D.sos_by_type||[];
  const labels=cats.map(c=>c.label),data=cats.map(c=>c.count);
  const colors=labels.map(l=>CC[l]||'#2563eb');
  if(chDonut) chDonut.destroy();
  chDonut=new Chart(document.getElementById('donutChart'),{
    type:'doughnut',
    data:{labels,datasets:[{data,backgroundColor:colors,borderWidth:3,borderColor:'#fff',hoverOffset:8}]},
    options:{cutout:'70%',plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>`  ${c.label}: ${c.raw}`},bodyFont:{family:'Inter',size:12},padding:10,boxPadding:4}},animation:{duration:700,easing:'easeOutQuart'}}
  });
  const leg=document.getElementById('donut-leg');
  if(!cats.length){leg.innerHTML='<div style="color:var(--muted);font-size:12px">No SOS data yet</div>';return;}
  leg.innerHTML=labels.map((l,i)=>`<div class="legitem"><div class="legdot" style="background:${colors[i]}"></div>${l} <b style="color:var(--text)">${data[i]}</b></div>`).join('');
}

// ── Trend line ────────────────────────────────────────────────────────────────
function renderTrend(){
  const t=D.trend||[];
  if(chTrend) chTrend.destroy();
  chTrend=new Chart(document.getElementById('trendChart'),{
    type:'line',
    data:{labels:t.map(x=>x.day),datasets:[{label:'SOS',data:t.map(x=>x.count),borderColor:'#2563eb',backgroundColor:'rgba(37,99,235,.08)',borderWidth:2.5,pointBackgroundColor:'#2563eb',pointBorderColor:'#fff',pointBorderWidth:2,pointRadius:5,pointHoverRadius:7,fill:true,tension:.4}]},
    options:{scales:{x:{grid:{color:'#f1f5f9'},ticks:{color:'#9ca3af',font:{family:'Inter',size:11}}},y:{grid:{color:'#f1f5f9'},ticks:{color:'#9ca3af',font:{family:'Inter',size:11},stepSize:1},beginAtZero:true}},plugins:{legend:{display:false}},animation:{duration:700}}
  });
}

// ── Analytics bar chart ───────────────────────────────────────────────────────
function renderAnalytics(){
  const t=D.trend||[];
  if(chAna) chAna.destroy();
  chAna=new Chart(document.getElementById('analyticsChart'),{
    type:'bar',
    data:{labels:t.map(x=>x.day),datasets:[{label:'SOS',data:t.map(x=>x.count),backgroundColor:'rgba(37,99,235,.14)',borderColor:'#2563eb',borderWidth:1.5,borderRadius:8,borderSkipped:false,hoverBackgroundColor:'rgba(37,99,235,.26)'}]},
    options:{scales:{x:{grid:{display:false},ticks:{color:'#9ca3af',font:{family:'Inter',size:11}}},y:{grid:{color:'#f1f5f9'},ticks:{color:'#9ca3af',font:{family:'Inter',size:11},stepSize:1},beginAtZero:true}},plugins:{legend:{display:false}},animation:{duration:700}}
  });
}

// ── Areas ─────────────────────────────────────────────────────────────────────
function renderAreas(){
  const areas=D.top_areas||[],el=document.getElementById('areas');
  if(!areas.length){el.innerHTML='<div class="empty"><div class="eico">📍</div>No area data yet</div>';return;}
  const max=Math.max(...areas.map(a=>a.count),1);
  el.innerHTML=areas.map((a,i)=>`<div class="brow"><div class="blbl" title="${a.area}">${a.area}</div><div class="btrack"><div class="bfill" style="width:${Math.round((a.count/max)*100)}%;background:${AC[i%AC.length]}"></div></div><div class="bnum">${a.count}</div></div>`).join('');
}

// ── Tables ────────────────────────────────────────────────────────────────────
function cb(c){const m={'In Danger':'bd','Stranded':'bs','Injured':'bi'};const i={'In Danger':'🚨','Stranded':'⚠️','Injured':'🏥'};return `<span class="badge ${m[c]||'bd'}">${i[c]||''}${c}</span>`;}
function sb(s){return `<span class="badge ${s==='active'?'ba':'br'}">${s==='active'?'🔴 active':'✅ resolved'}</span>`;}
function renderRecentTbl(){
  const rows=D.recent_sos||[],tb=document.getElementById('tb-recent');
  if(!rows.length){tb.innerHTML='<tr><td colspan="7"><div class="empty"><div class="eico">🌊</div>No SOS requests yet</div></td></tr>';return;}
  tb.innerHTML=rows.map(r=>`<tr><td class="tdn">${r.name}</td><td>${cb(r.category)}</td><td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted)">${r.address||'—'}</td><td>${sb(r.status)}</td><td style="font-weight:600">${r.notified||0}</td><td style="color:var(--muted);white-space:nowrap">${r.created_at||'—'}</td><td>${r.maps_url?`<a href="${r.maps_url}" target="_blank" class="mapbtn">📍 Map</a>`:''}</td></tr>`).join('');
}
function renderAllTbl(){
  const rows=D.recent_sos||[];
  $('sos-lbl',rows.length+' records');
  const tb=document.getElementById('tb-all');
  if(!rows.length){tb.innerHTML='<tr><td colspan="9"><div class="empty"><div class="eico">🌊</div>No SOS requests yet</div></td></tr>';return;}
  tb.innerHTML=rows.map((r,i)=>`<tr><td style="color:var(--muted);font-weight:600">${i+1}</td><td class="tdn">${r.name}</td><td style="color:var(--muted)">${r.phone||'—'}</td><td>${cb(r.category)}</td><td style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted)">${r.address||'—'}</td><td>${sb(r.status)}</td><td style="font-weight:600">${r.notified||0}</td><td style="color:var(--muted);white-space:nowrap">${r.created_at||'—'}</td><td>${r.maps_url?`<a href="${r.maps_url}" target="_blank" class="mapbtn">📍</a>`:''}</td></tr>`).join('');
}

// ── Users CARDS ───────────────────────────────────────────────────────────────
function renderUsers(){
  const users=D.users||[],el=document.getElementById('ucards-wrap');
  if(!users.length){el.innerHTML='<div class="empty"><div class="eico">👤</div>No users registered yet</div>';return;}
  el.innerHTML=`<div class="ucards">${users.map(u=>{
    const init=(u.name||'?')[0].toUpperCase();
    const locHtml=u.has_loc
      ?`<div class="uloc">
          <div class="uloc-icon">📍</div>
          <div>
            <div class="uloc-text">${u.location||'Location saved'}</div>
            <div class="uloc-coords">${u.lat?Number(u.lat).toFixed(4)+'°N':''} ${u.lon?Number(u.lon).toFixed(4)+'°E':''}</div>
            ${u.maps_url?`<a class="uloc-link" href="${u.maps_url}" target="_blank">View on Map ↗</a>`:''}
          </div>
        </div>`
      :`<div class="uloc" style="background:#fff7ed;border:1px solid var(--orange-mid)"><div class="uloc-icon">⚠️</div><div class="uloc-text" style="color:var(--orange)">No location saved yet</div></div>`;
    return `<div class="ucard">
      <div class="ucard-top">
        <div class="uav">${init}</div>
        <div>
          <div class="uname">${u.name||'Unknown'}</div>
          <div class="uphone">${u.phone||'—'}</div>
        </div>
      </div>
      <div class="utags">
        <span class="utag ${u.has_token?'ton':'toff'}">${u.has_token?'🔔 Push ON':'🔕 No Token'}</span>
        <span class="utag ${u.has_loc?'ton':'toff'}">${u.has_loc?'📡 Monitoring':'📵 No Location'}</span>
      </div>
      ${locHtml}
    </div>`;
  }).join('')}</div>`;
}

// ── Demo modal ────────────────────────────────────────────────────────────────
function openDemo(){
  document.getElementById('demoOverlay').classList.add('open');
  document.getElementById('mresult').style.display='none';
  document.getElementById('probWrap').style.display='none';
  document.getElementById('sendBtn').disabled=false;
  document.getElementById('sendBtn').innerHTML='<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>Send Demo Flood Alert Now';
}
function closeDemo(){ document.getElementById('demoOverlay').classList.remove('open'); }

function previewProb(){
  // client-side rough estimate so user sees live feedback while typing
  const r1=+gv('p-r1'),r24=+gv('p-r24'),hum=+gv('p-hum'),sm=+gv('p-sm'),elev=+gv('p-elev'),drain=+gv('p-drain');
  let score=0;
  if(r1>20) score+=.30; else if(r1>5) score+=.15;
  if(r24>80) score+=.25; else if(r24>30) score+=.12;
  if(hum>88) score+=.15; else if(hum>75) score+=.07;
  if(sm>0.75) score+=.15; else if(sm>0.5) score+=.07;
  if(elev<30) score+=.10;
  if(drain<3) score+=.05;
  score=Math.min(score,0.99);
  const pct=Math.round(score*100);
  document.getElementById('probWrap').style.display='block';
  document.getElementById('probFill').style.width=pct+'%';
  const pv=document.getElementById('probVal');
  pv.textContent=pct+'% flood probability (estimate)';
  pv.style.color=pct>=75?'#dc2626':pct>=45?'#ea580c':'#16a34a';
}

async function sendDemo(){
  const btn=document.getElementById('sendBtn');
  btn.disabled=true;
  btn.innerHTML='<svg style="animation:spin .8s linear infinite" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>Sending…';

  const body={
    rainfall_1h:   +gv('p-r1'),
    rainfall_24h:  +gv('p-r24'),
    humidity:      +gv('p-hum'),
    temperature:   +gv('p-tmp'),
    soil_moisture: +gv('p-sm'),
    elevation:     +gv('p-elev'),
    drainage:      +gv('p-drain'),
    slope:         +gv('p-slope'),
    pressure:      +gv('p-pres'),
    demo_lat:      +gv('p-lat'),
    demo_lon:      +gv('p-lon'),
    radius_km:     +gv('p-radius') || 5,
    target_phone:  gv('p-phone').trim(),
  };

  const res=document.getElementById('mresult');
  try{
    const r=await fetch('/admin/demo-flood?admin_key='+encodeURIComponent(getKey()),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    if(d.success){
      res.className='mresult ok';
      const loc=d.demo_location;
      const skipNote=d.skipped_far>0?`<br><span style="color:#92400e">⚠️ ${d.skipped_far} user(s) outside ${loc.radius_km} km radius — not notified</span>`:'';
      res.innerHTML=`<b>✅ Demo flood alert sent!</b><br>
        ML Probability: <b>${d.pct}%</b> flood risk<br>
        Demo location: <b>${loc.lat}, ${loc.lon}</b> (radius ${loc.radius_km} km)<br>
        Notifications sent to: <b>${d.sent_to} / ${d.total_targets} user(s) in zone</b>${skipNote}<br>
        Nearest shelter shown: <b>${d.shelter}</b><br>
        <span style="color:#166534;font-size:11px">📡 Scheduler is back on real data — this was a one-time override.</span>`;
    } else {
      res.className='mresult err';
      res.innerHTML=`<b>❌ Failed:</b> ${d.error||'Unknown error'}`;
    }
  }catch(e){
    res.className='mresult err';
    res.innerHTML=`<b>❌ Network error:</b> ${e.message}`;
  }
  res.style.display='block';
  btn.disabled=false;
  btn.innerHTML='<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>Send Again';
  style_spin();
}
function style_spin(){
  if(!document.getElementById('_spin_style')){
    const s=document.createElement('style');s.id='_spin_style';
    s.textContent='@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}';
    document.head.appendChild(s);
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function $(id,v){const e=document.getElementById(id);if(e)e.textContent=v??'—';}
function gv(id){return document.getElementById(id)?.value??'';}

// ── Cyclone tab render ────────────────────────────────────────────────────────
function renderCyclone(){
  if(!D) return;
  $('cy-alerts', D.cyclone_alerts ?? 0);
  const mlEl = document.getElementById('cy-ml');
  const mlMeta = document.getElementById('cy-ml-m');
  if(mlEl){
    if(D.cyclone_ml_active){
      mlEl.textContent = '✅ Active';
      mlEl.style.color = 'var(--green)';
      if(mlMeta) mlMeta.textContent = 'ERA5-trained ensemble';
    } else {
      mlEl.textContent = '⚠ Physics';
      mlEl.style.color = 'var(--orange)';
      if(mlMeta) mlMeta.textContent = 'Run train_cyclone.py to activate ML';
    }
  }

  // Season calendar
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const factors = [0.55,0.55,0.65,0.90,1.30,0.95,0.45,0.45,0.60,1.20,1.30,0.90];
  const wrap = document.getElementById('season-chart-wrap');
  if(wrap){
    wrap.innerHTML = months.map((m,i)=>{
      const f = factors[i];
      const pct = Math.round(f * 100);
      const col = f >= 1.2 ? '#dc2626' : f >= 0.9 ? '#ea580c' : f >= 0.6 ? '#ca8a04' : '#16a34a';
      const bg  = f >= 1.2 ? '#fef2f2' : f >= 0.9 ? '#fff7ed' : f >= 0.6 ? '#fefce8' : '#f0fdf4';
      return `<div style="background:${bg};border-radius:8px;padding:8px 4px;text-align:center">
        <div style="font-size:10px;font-weight:700;color:${col}">${m}</div>
        <div style="font-size:11px;font-weight:800;color:${col};margin-top:3px">${pct}%</div>
      </div>`;
    }).join('');
  }
}

// ── Cyclone demo modal ────────────────────────────────────────────────────────
function openCycloneDemo(){
  document.getElementById('cycloneDemoOverlay').classList.add('open');
  document.getElementById('cy-mresult').style.display='none';
}
function closeCycloneDemo(){
  document.getElementById('cycloneDemoOverlay').classList.remove('open');
}
async function sendCycloneDemo(){
  const btn = document.getElementById('cy-sendBtn');
  btn.disabled = true;
  btn.innerHTML = '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/></svg>Sending…';
  const res = document.getElementById('cy-mresult');
  res.style.display='none';
  try{
    const r = await fetch('/admin/demo-cyclone?admin_key='+encodeURIComponent(getKey()),{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        wind_gusts_kmh:       parseFloat(gv('cy-gusts')),
        surface_pressure_hpa: parseFloat(gv('cy-pres')),
        pressure_drop_6h:     parseFloat(gv('cy-drop')),
        cape_jkg:             parseFloat(gv('cy-cape')),
        demo_lat:             parseFloat(gv('cy-lat')),
        demo_lon:             parseFloat(gv('cy-lon')),
        radius_km:            parseFloat(gv('cy-radius')),
        target_phone:         gv('cy-phone').trim(),
      })
    });
    const d = await r.json();
    if(d.success){
      const ml = d.ml_model_used ? '🤖 ML model' : '⚡ Physics model';
      res.className='mresult ok'; res.style.display='block';
      res.innerHTML=`✅ Demo sent! &nbsp;·&nbsp; Probability: <strong>${d.pct}%</strong> (${d.risk_level}) &nbsp;·&nbsp; Category: <strong>${d.category}</strong><br>
        Push delivered to <strong>${d.sent_to}</strong> of ${d.total_targets} targets (${d.skipped_far} outside radius)<br>
        <span style="font-size:11px;opacity:.8">${ml} · ${d.note}</span>`;
    } else {
      res.className='mresult err'; res.style.display='block';
      res.textContent='❌ '+d.error;
    }
  }catch(e){
    res.className='mresult err'; res.style.display='block';
    res.textContent='Network error: '+e.message;
  }finally{
    btn.disabled=false;
    btn.innerHTML='<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 8c-2.2 0-4 1.8-4 4s1.8 4 4 4"/></svg>Send Demo Cyclone Alert Now';
  }
}

// ── Boot ──────────────────────────────────────────────────────────────────────
loadData();
setInterval(loadData,30000);
</script>
</body>
</html>"""
