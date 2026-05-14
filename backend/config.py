import os
from dotenv import load_dotenv

load_dotenv()

OPENWEATHER_API_KEY  = os.getenv("OPENWEATHER_API_KEY", "")
GEMINI_API_KEY       = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY         = os.getenv("GROQ_API_KEY", "")
SUPABASE_URL         = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY         = os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# Admin dashboard API key — set ADMIN_API_KEY in .env for production.
# Default value is intentionally non-trivial so it's not accidentally left open.
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "js-admin-secure-2024")

OWM_BASE = "https://api.openweathermap.org/data/2.5"
NOAA_BASE = "https://api.weather.gov"
OPEN_METEO_BASE = "https://api.open-meteo.com/v1"
