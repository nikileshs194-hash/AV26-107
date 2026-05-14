import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.weather import router as weather_router
from routes.alerts  import router as alerts_router
from routes.chat    import router as chat_router
from routes.sos     import router as sos_router
from routes.predict import router as predict_router
from routes.auth    import router as auth_router
from routes.admin   import router as admin_router

from services.scheduler import run_scheduler


# ── Lifespan — start/stop background scheduler ────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the periodic scheduler as a background task
    task = asyncio.create_task(run_scheduler())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Flood AI System API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(weather_router)
app.include_router(alerts_router)
app.include_router(chat_router)
app.include_router(sos_router)
app.include_router(predict_router)
app.include_router(auth_router)
app.include_router(admin_router)


@app.get("/")
def home():
    return {
        "status": "running",
        "service": "Flood AI System API v2",
        "endpoints": {
            "weather": "GET /api/weather?lat=&lon=",
            "alerts":  "GET /api/alerts?lat=&lon=",
            "chat":    "POST /api/chat",
            "sos":     "POST /api/sos",
            "shelters":"GET /api/sos/shelters?lat=&lon=",
            "predict": "GET /predict?lat=&lon=",
        },
    }


@app.get("/health")
def health():
    return {"status": "ok"}
