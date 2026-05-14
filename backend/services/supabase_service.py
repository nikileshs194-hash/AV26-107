from config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_KEY

_client = None
_service_client = None


def _get_client():
    """Anon client — for public read operations."""
    global _client
    if _client is None and SUPABASE_URL and SUPABASE_KEY:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def _get_service_client():
    """Service-role client — bypasses RLS for backend writes."""
    global _service_client
    key = SUPABASE_SERVICE_KEY or SUPABASE_KEY
    if _service_client is None and SUPABASE_URL and key:
        from supabase import create_client
        _service_client = create_client(SUPABASE_URL, key)
    return _service_client


def get_nearby_shelters(lat: float, lon: float, radius_km: float = 20) -> list:
    db = _get_client()
    if not db:
        return []
    try:
        res = db.table("shelters").select("*").execute()
        result = []
        for s in (res.data or []):
            d = _haversine(lat, lon, s.get("latitude", 0), s.get("longitude", 0))
            if d <= radius_km:
                s["distance_km"] = round(d, 1)
                result.append(s)
        return sorted(result, key=lambda x: x["distance_km"])[:5]
    except Exception:
        return []


def _haversine(lat1, lon1, lat2, lon2) -> float:
    from math import radians, cos, sin, asin, sqrt
    R = 6371
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))
