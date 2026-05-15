# JeevanSetu — AI-Powered Disaster Response System

<div align="center">

![JeevanSetu](https://img.shields.io/badge/JeevanSetu-Disaster%20AI-2563eb?style=for-the-badge&logo=shield&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Expo](https://img.shields.io/badge/Expo-SDK%2054-000020?style=for-the-badge&logo=expo&logoColor=white)
![ML](https://img.shields.io/badge/3%20ML%20Models-Flood%20%7C%20Cyclone%20%7C%20Earthquake-f7931e?style=for-the-badge)
![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ecf8e?style=for-the-badge&logo=supabase&logoColor=white)

**Before Disaster Strikes — JeevanSetu Acts.**

A full-stack emergency response platform with real-time multi-hazard intelligence (flood, cyclone, earthquake), AI-powered predictions, emergency SOS coordination, and push-notification alerts — built for India's disaster preparedness needs.

</div>

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [API Reference](#api-reference)
- [ML Models](#ml-models)
  - [Flood Model](#flood-prediction-model)
  - [Cyclone Model](#cyclone-prediction-model)
  - [Earthquake Model](#earthquake-prediction-model)
- [Admin Dashboard](#admin-dashboard)
- [Push Notifications](#push-notifications)
- [Database Schema](#database-schema)
- [Setup & Installation](#setup--installation)
- [Deployment](#deployment)
- [Environment Variables](#environment-variables)
- [Screens & UI](#screens--ui)
- [Security](#security)
- [Background Location Tracking](#background-location-tracking)
- [Offline Support](#offline-support)

---

## Overview

JeevanSetu is a disaster-preparedness system built for real-world deployment in India. It provides citizens with real-time multi-hazard forecasts, emergency SOS dispatch, AI-powered safety guidance, and push-notification disaster alerts — all from a single mobile app backed by a production-grade FastAPI server.

The system integrates:
- **3 independent ML models** — flood (Open-Meteo + OSM), cyclone (ERA5 + GDACS), earthquake (USGS 20-year catalog)
- **Live external APIs** — Open-Meteo, OpenWeatherMap, GDACS RSS, USGS Earthquake Catalog
- **Groq LLM + Whisper** — voice-enabled AI assistance
- **Supabase** — real-time PostgreSQL database and user store
- **SMS OTP authentication** via 2Factor.in
- **Expo push notifications** — foreground and background alerts for all hazard types
- **Expo background location** — persistent GPS tracking for rescue coordination

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         MOBILE APP (Expo)                           │
│  Auth Flow → Weather/Home → Alerts → AI Chat                        │
│  Push Notification Modals: Flood · Cyclone · Earthquake · SOS       │
│  Background Location Task (persists across app restarts)            │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTP / REST
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        FASTAPI BACKEND                              │
│  /api/weather   /api/alerts   /api/chat    /api/sos                 │
│  /api/auth      /predict      /api/cyclone /api/earthquake          │
│  /admin/*                                                           │
│                                                                     │
│  Services: weather · alert · risk · AI · auth · SMS                 │
│            cyclone · earthquake · scheduler                         │
└──────┬──────────────┬──────────────┬────────────────────────────────┘
       │              │              │
       ▼              ▼              ▼
  Supabase        External APIs   ML Models
  PostgreSQL      Open-Meteo      model.pkl          (flood)
  (users, sos,    OpenWeather     cyclone_model.pkl  (cyclone)
   alerts,        GDACS RSS       earthquake_model.pkl (earthquake)
   shelters)      USGS Catalog
                  Expo Push API
                  Groq (LLM)
```

---

## Features

### Multi-Hazard Intelligence

#### Flood Prediction
- Voting ensemble ML model (XGBoost + GradientBoosting + RandomForest) trained on 210+ real Indian flood events across 30 cities
- 12 features fetched live: rainfall, humidity, soil moisture, terrain elevation, slope, drainage density, and 3 engineered interaction features
- 12-hour prediction window, risk levels: Very Low / Low / Moderate / High
- Data sources: Open-Meteo (weather + DEM), OpenStreetMap Overpass API (drainage)

#### Cyclone Prediction
- ERA5-trained VotingEnsemble trained on 38 documented Indian Ocean cyclone landfalls (Bay of Bengal + Arabian Sea, 2007–2024)
- Live atmospheric features: surface wind, wind gusts, pressure, CAPE — fetched from Open-Meteo
- GDACS RSS feed integration — active tropical cyclone within 1,500 km raises minimum probability floor to 0.60
- Indian coastline proximity multiplier + IMD seasonal risk calendar
- IMD categories: Depression → Deep Depression → Cyclonic Storm → Severe → Very Severe → Extremely Severe → Super Cyclone

#### Earthquake Prediction
- VotingEnsemble (XGBoost + GBM + RandomForest) trained on 14,775 samples from USGS 20-year catalog (2005–2024, M≥2.0)
- 12 seismological features computed from live USGS data: b-value (Aki MLE), inter-event CV, quake acceleration, shallow depth fraction, max magnitude, and more
- Predicts probability of M≥4.5 within 100 km in the next 7 days
- BIS 1893 seismic zone classification for all Indian states
- Temporal AUC: 88% | CV ROC-AUC: 90.7%

### Emergency SOS
- One-tap SOS with emergency category selection (Flooding / Stranded / Injured / Cyclone Emergency / Earthquake Emergency)
- Automatic reverse geocoding to attach a human-readable address
- SOS stored in database and surfaced on rescue dashboard immediately
- **Call Nearby People** — sends Expo push notifications to all registered users within radius; returns nearest person for direct dial
- Nearest-person finder with direct-dial option via `GET /api/sos/find-nearest`
- Configurable rescue contact number (default: 112, stored per-device)

### Push Notification Alert Modals
All four hazard modals are full-screen bottom sheets that appear automatically when a push notification arrives (foreground or tapped from background):

| Modal | Color | Trigger | Actions |
|-------|-------|---------|---------|
| **SOSAlertModal** | Red | SOS from nearby user | Call Victim · Navigate |
| **FloodAlertModal** | Blue | `flood_alert` notification | Navigate to Shelter · I Am Safe |
| **CycloneAlertModal** | Purple | `cyclone_alert` notification | Find Cyclone Shelter · I Am Safe |
| **EarthquakeAlertModal** | Amber | `earthquake_alert` notification | Assembly Point Navigation · I Am Safe · SOS |

### Weather Intelligence
- Real-time conditions: temperature, humidity, wind, UV index, visibility, air quality, pressure
- 24-hour hourly forecast with rain probability per slot
- 7-day daily forecast with high/low temperatures
- Multi-source fusion (OWM + Open-Meteo) for reliability

### AI Chat Assistant
- Natural language Q&A via Groq `llama-3.3-70b-versatile`
- Location-aware context injection (lat/lon with every message)
- Voice input via Groq Whisper transcription
- Conversation history (last 10 messages) for multi-turn dialogue
- Follow-up suggestion chips updated by the model

### Authentication
- Phone-based OTP login (no passwords)
- SMS delivery via 2Factor.in API
- 60-second resend timer with shake animation on wrong code
- Profile setup: full name, age, gender (used for emergency response prioritisation)

### Admin Dashboard
- Three hazard intelligence tabs: Flood · Cyclone · Earthquake
- Each tab has live stat cards, reference tables, ML feature panels
- Demo alert buttons for testing push notifications: Demo Flood Alert · Demo Cyclone Alert · Demo Earthquake Alert
- Live SOS feed, user map, analytics
- API-key gated

---

## Project Structure

```
flood-ai-system/
│
├── backend/                         # FastAPI server
│   ├── main.py                      # Entry point, CORS, route registration, scheduler
│   ├── config.py                    # Environment variable loading
│   ├── requirements.txt             # Python dependencies
│   ├── Procfile                     # Railway deployment start command
│   │
│   ├── routes/
│   │   ├── weather.py               # GET /api/weather
│   │   ├── alerts.py                # GET /api/alerts, save, list, delete
│   │   ├── chat.py                  # POST /api/chat + /api/chat/transcribe
│   │   ├── sos.py                   # SOS dispatch, nearby notify, shelters
│   │   ├── predict.py               # GET /predict  (flood ML model)
│   │   ├── cyclone.py               # GET /api/cyclone (cyclone ML model)
│   │   ├── earthquake.py            # GET /api/earthquake (earthquake ML model)
│   │   ├── auth.py                  # OTP send/verify, profile, location
│   │   └── admin.py                 # Admin dashboard HTML + API (key-protected)
│   │
│   ├── services/
│   │   ├── weather_service.py       # OWM + Open-Meteo fusion
│   │   ├── alert_service.py         # Alert engine (multi-source)
│   │   ├── risk_service.py          # Weather risk score
│   │   ├── cyclone_service.py       # Cyclone prediction (ERA5 + GDACS + ML)
│   │   ├── earthquake_service.py    # Earthquake prediction (USGS + ML)
│   │   ├── ai_service.py            # Groq LLM integration
│   │   ├── auth_service.py          # OTP logic, user CRUD
│   │   ├── sms_service.py           # 2Factor.in SMS delivery
│   │   ├── supabase_service.py      # DB client, shelter queries
│   │   └── scheduler.py             # Background task runner (alert polling)
│   │
│   ├── model.pkl                    # Flood voting ensemble (trained)
│   ├── cyclone_model.pkl            # Cyclone voting ensemble (trained)
│   ├── earthquake_model.pkl         # Earthquake voting ensemble (trained)
│   ├── collect_and_train.py         # Flood model training script (ERA5 + OSM)
│   └── earthquake_training.py       # Earthquake model training script (USGS)
│
├── mobile-app/                      # Expo / React Native app
│   ├── app/
│   │   ├── (auth)/
│   │   │   ├── login.tsx            # Phone number entry
│   │   │   ├── verify.tsx           # OTP verification
│   │   │   └── profile-setup.tsx    # Name / age / gender
│   │   │
│   │   ├── (tabs)/
│   │   │   ├── index.tsx            # Home: weather, flood prediction, SOS
│   │   │   ├── alerts.tsx           # Real-time alerts with offline cache
│   │   │   └── ai.tsx               # AI chat + voice input
│   │   │
│   │   └── _layout.tsx              # Root layout: AuthProvider, push token
│   │                                #   registration, all 4 alert modals
│   │
│   ├── components/
│   │   ├── SOSAlertModal.tsx        # Incoming SOS notification modal (red)
│   │   ├── FloodAlertModal.tsx      # Flood alert modal (blue)
│   │   ├── CycloneAlertModal.tsx    # Cyclone alert modal (purple)
│   │   └── EarthquakeAlertModal.tsx # Earthquake alert modal (amber)
│   │
│   ├── services/
│   │   └── api.ts                   # All backend API calls + TypeScript types
│   │
│   ├── tasks/
│   │   └── locationTask.ts          # Expo TaskManager background GPS handler
│   │
│   ├── context/
│   │   └── AuthContext.tsx          # Global user state + AsyncStorage
│   │
│   ├── constants/
│   │   └── api.ts                   # BACKEND_URL (update for production)
│   │
│   └── app.json                     # Expo config: permissions, bundle ID,
│                                    #   EAS project ID, notification channels
│
├── dashboard/                       # Next.js admin frontend (optional)
│   └── app/
│
├── database/
│   └── schema.sql                   # Supabase table definitions
│
└── supabase_migration.sql           # Migration script
```

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Mobile Framework | Expo / React Native | SDK 54 / 0.81.5 |
| Language (mobile) | TypeScript | 5.9 |
| Navigation | Expo Router | 4.x |
| Push Notifications | Expo Notifications | SDK 54 |
| Background Tasks | Expo TaskManager + expo-location | SDK 54 |
| Backend Framework | FastAPI | 0.136 |
| Language (backend) | Python | 3.11+ |
| Flood ML Model | VotingEnsemble (XGBoost + GBM + RF) | XGBoost 3.2, scikit-learn 1.8 |
| Cyclone ML Model | VotingEnsemble (XGBoost + GBM + RF) | ERA5-trained |
| Earthquake ML Model | VotingEnsemble (XGBoost + GBM + RF) | USGS 20yr catalog |
| Database | Supabase (PostgreSQL) | — |
| AI / LLM | Groq (llama-3.3-70b) | — |
| Voice STT | Groq Whisper | — |
| Weather APIs | OpenWeatherMap, Open-Meteo | — |
| Cyclone Data | GDACS RSS Feed | Live |
| Seismic Data | USGS Earthquake Catalog API | Live |
| SMS | 2Factor.in | — |
| Storage (mobile) | AsyncStorage | 2.x |

---

## API Reference

### Weather

| Method | Endpoint | Params | Description |
|--------|----------|--------|-------------|
| `GET` | `/api/weather` | `lat`, `lon` | Current conditions, 24h hourly, 7d daily, risk assessment |

### Flood Prediction

| Method | Endpoint | Params | Description |
|--------|----------|--------|-------------|
| `GET` | `/predict` | `lat`, `lon` | Voting ensemble flood probability for next 12 hours |

```json
{
  "flood_predicted": true,
  "probability": 0.73,
  "risk_level": "High",
  "forecast_window": "12 hours",
  "features": { "rainfall_1h": 12.4, "rainfall_24h": 48.0, "humidity": 88.0, ... },
  "advice": ["Move valuables to higher ground", "Avoid low-lying roads"]
}
```

### Cyclone Prediction

| Method | Endpoint | Params | Description |
|--------|----------|--------|-------------|
| `GET` | `/api/cyclone` | `lat`, `lon` | Cyclone probability, category, GDACS status, safety tips |

```json
{
  "probability": 0.42,
  "risk_level": "Moderate",
  "category": "Cyclonic Storm",
  "gdacs_active": false,
  "gdacs_distance_km": 9999.0,
  "advice": ["Monitor IMD bulletins", "Prepare emergency kit"],
  "ml_model_active": true,
  "data_sources": ["ML Model (ERA5-trained)", "Open-Meteo", "GDACS"]
}
```

### Earthquake Prediction

| Method | Endpoint | Params | Description |
|--------|----------|--------|-------------|
| `GET` | `/api/earthquake` | `lat`, `lon` | M≥4.5 probability in 7 days, seismic zone, features |

```json
{
  "probability": 0.18,
  "risk_level": "Low",
  "seismic_zone": "Zone IV",
  "ml_model_active": true,
  "features": { "b_value": 0.94, "inter_event_cv": 0.71, "quakes_7d": 3, ... },
  "advice": ["Standard earthquake preparedness recommended"]
}
```

### Alerts

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/alerts?lat=&lon=` | Active alerts for location |
| `POST` | `/api/alerts/save` | Save alert to user list |
| `GET` | `/api/alerts/saved?phone=` | Fetch saved alerts |
| `DELETE` | `/api/alerts/clear` | Delete a saved alert |

### Chat / AI

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/chat` | LLM chat response + follow-up suggestions |
| `POST` | `/api/chat/transcribe` | Groq Whisper audio → text |

### SOS & Emergency

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/sos` | File SOS alert (stores to DB with reverse-geocoded address) |
| `POST` | `/api/sos/notify-nearby` | Push notifications to nearby users; returns nearest person |
| `POST` | `/api/sos/push-token` | Register / update Expo push token |
| `GET` | `/api/sos/find-nearest?lat=&lon=` | Return nearest registered user |
| `GET` | `/api/sos/shelters?lat=&lon=` | Nearest emergency shelters |
| `PUT` | `/api/sos/{id}/resolve` | Mark SOS as resolved |

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/auth/send-otp` | Send OTP SMS |
| `POST` | `/api/auth/verify-otp` | Verify OTP, create/return user |
| `POST` | `/api/auth/update-profile` | Save profile (name, age, gender) |
| `GET` | `/api/auth/profile/{phone}` | Fetch user profile |
| `POST` | `/api/auth/update-location` | Update live location |

### Admin (API-key required)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/admin` | Full admin dashboard (HTML) |
| `GET` | `/admin/data?admin_key=` | Live JSON data feed |
| `POST` | `/admin/demo-flood` | Simulate flood alert → push notifications |
| `POST` | `/admin/demo-cyclone` | Simulate cyclone alert → push notifications |
| `POST` | `/admin/demo-earthquake` | Simulate earthquake alert → push notifications |

---

## ML Models

### Flood Prediction Model

**Architecture:** Soft-voting ensemble (XGBoost + GradientBoosting + RandomForest) wrapped in StandardScaler pipeline.

**Training data:** 210+ real historical flood events across 30 Indian cities, ERA5 historical reanalysis via Open-Meteo, real terrain DEM, real OSM drainage density.

**12 features:**

| # | Feature | Source |
|---|---------|--------|
| 1 | `rainfall_1h` | Open-Meteo forecast |
| 2 | `rainfall_24h` | Open-Meteo archive + forecast |
| 3 | `humidity` | Open-Meteo |
| 4 | `temperature` | Open-Meteo |
| 5 | `elevation` | Open-Meteo DEM |
| 6 | `soil_moisture` | Open-Meteo |
| 7 | `drainage` | OpenStreetMap Overpass API |
| 8 | `slope` | Open-Meteo 5-point DEM gradient |
| 9 | `pressure` | Open-Meteo |
| 10 | `sat_index` | `soil_moisture × rainfall_24h` |
| 11 | `rain_burst` | `rainfall_1h ÷ rainfall_24h` |
| 12 | `drain_eff` | `drainage × (slope + 0.5) ÷ 10` |

**Risk thresholds:** ≥75% → High · 45–74% → Moderate · 20–44% → Low · <20% → Very Low

**Retrain:**
```bash
cd backend && python collect_and_train.py
# ~10–15 min (network-bound). Outputs: model.pkl
```

---

### Cyclone Prediction Model

**Architecture:** VotingClassifier (XGBoost + GBM + RandomForest)

**Training data:** 38 documented Indian Ocean cyclone landfalls (Bay of Bengal + Arabian Sea, 2007–2024) + 62 control clear-weather days. ERA5 historical reanalysis via Open-Meteo.

**Live data at prediction time:**
- Open-Meteo — surface wind speed, wind gusts (10m), pressure, CAPE
- GDACS RSS Feed — active tropical cyclones worldwide (TC events only)

**Special logic:**
- Active GDACS TC within 1,500 km → probability floor raised to 0.60
- Seasonal multipliers applied (IMD calendar): May/Nov peak (+30%), Jul/Aug trough (−55%)
- Coastal proximity multiplier (within 300 km of Indian coastline)

**IMD Categories:** Depression (31–51 km/h) → Deep Depression → Cyclonic Storm → Severe → Very Severe → Extremely Severe → Super Cyclone (≥222 km/h)

---

### Earthquake Prediction Model

**Architecture:** VotingClassifier (XGBoost + GBM + RandomForest)

**Training data:** 14,775 samples, USGS catalog 2005–2024, M≥2.0 events

**Performance:** CV ROC-AUC: 90.7% · Temporal AUC (2023–24): 88.0%

**12 features computed from live USGS data (last 90 days, 100 km radius):**

| Feature | Description |
|---------|-------------|
| `b_value` | Aki MLE b-value — low b = high tectonic stress |
| `inter_event_cv` | Coefficient of variation of inter-event times |
| `quake_acceleration` | 7d rate / 30d rate — foreshock swarm signal |
| `shallow_depth_frac` | Fraction of quakes at depth < 30 km |
| `quakes_7d` / `quakes_30d` | Recent event counts |
| `max_mag_7d` / `max_mag_30d` | Peak magnitude windows |
| `mean_depth` | Average focal depth |
| `depth_std` | Depth variability |
| `dist_to_fault_km` | Distance to nearest known fault |
| `bis_zone_numeric` | BIS 1893 zone (II=1, III=2, IV=3, V=4) |

**BIS 1893 Seismic Zones:**

| Zone | Region | Risk |
|------|--------|------|
| Zone II | Most of South India, Rajasthan | Low |
| Zone III | Kerala, Goa, Maharashtra coast | Moderate |
| Zone IV | Delhi, J&K, Himachal, Sikkim | High |
| Zone V | NE India, Uttarakhand, Kashmir Valley | Very High |

---

## Admin Dashboard

The dashboard lives at `/admin` and is accessible from any browser. It is protected by an API key prompted on first load.

### Hazard Tabs

**Flood Intelligence**
- Stat cards: Flood Alerts Sent, ML Model status, Data Sources (Open-Meteo + Terrain), Features (11 hydro + terrain signals)
- IMD Rainfall Thresholds reference table
- ML Model Features panel (9 base + 3 engineered features)
- Demo Flood Alert button with radius and target phone parameters

**Cyclone Intelligence**
- Stat cards: Cyclone Alerts Sent, ML Model status (ERA5-trained ensemble), Data Sources (Open-Meteo + GDACS), Training Events (38, 2007–2024)
- IMD Cyclone Scale reference table (Depression → Super Cyclone)
- Cyclone Season Calendar with monthly IMD risk multipliers
- Demo Cyclone Alert button

**Earthquake Intelligence**
- Stat cards: Earthquake Alerts Sent, ML Model status (USGS-trained ensemble), Data Sources (USGS + BIS 1893), Training Period (20 yr, 2005–2024)
- BIS 1893 Seismic Zones reference table
- Seismological Features panel (b-value, inter-event CV, quake acceleration, shallow depth fraction)
- ML Model Features breakdown (12 features, VotingClassifier AUC 88%)
- Demo Earthquake Alert button

### Demo Alert System

Each demo endpoint accepts:
```json
{
  "radius_km": 50,
  "target_phone": "+919xxxxxxxxx",  // optional: test with specific user
  "probability": 0.8,
  "risk_level": "High"
}
```

The demo pushes a real Expo notification to all users within the specified radius (or just the target phone). The mobile app catches it and renders the appropriate alert modal.

---

## Push Notifications

### Notification Types

| `data.type` | Modal Shown | Color Theme |
|-------------|-------------|-------------|
| `sos_alert` | SOSAlertModal | Red |
| `flood_alert` | FloodAlertModal | Blue |
| `cyclone_alert` | CycloneAlertModal | Purple |
| `earthquake_alert` | EarthquakeAlertModal | Amber |

### How It Works

1. On login, the app calls `getExpoPushTokenAsync` and saves the token to the backend via `POST /api/sos/push-token`
2. When a demo alert is triggered (or a real alert fires from the scheduler), the backend fetches users within radius from Supabase, filters those with push tokens, and sends via the Expo push API (`https://exp.host/--/api/v2/push/send`)
3. The notification arrives with a `data` payload containing `type` and hazard details
4. `_layout.tsx` listens via `addNotificationReceivedListener` (foreground) and `addNotificationResponseReceivedListener` (background tap) and sets the appropriate modal state

### Android Notification Channels

| Channel | Importance | Use |
|---------|-----------|-----|
| `sos` | MAX (bypasses DnD) | SOS alerts, flood/cyclone/earthquake emergencies |
| `weather` | DEFAULT | Weather tip notifications |

> **Note:** Expo Go SDK 53+ does not deliver remote push notifications on Android. Use an EAS development build for full notification testing.

---

## Database Schema

Tables defined in `database/schema.sql`. Create in your Supabase project before running the backend.

```sql
-- Users
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone       TEXT UNIQUE,
    full_name   TEXT,
    age         INTEGER,
    gender      TEXT,
    latitude    FLOAT,
    longitude   FLOAT,
    push_token  TEXT,
    status      TEXT
);

-- SOS requests
CREATE TABLE sos_requests (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone       TEXT,
    name        TEXT,
    latitude    FLOAT,
    longitude   FLOAT,
    category    TEXT,
    address     TEXT,
    status      TEXT DEFAULT 'pending',
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Alerts log
CREATE TABLE alerts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source      TEXT,
    severity    TEXT,
    title       TEXT,
    description TEXT,
    latitude    FLOAT,
    longitude   FLOAT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Saved alerts (per user)
CREATE TABLE user_alerts (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone        TEXT,
    alert_id     TEXT,
    title        TEXT,
    description  TEXT,
    severity     TEXT,
    source       TEXT,
    created_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (phone, alert_id)
);

-- Emergency shelters
CREATE TABLE shelters (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shelter_name TEXT,
    latitude     FLOAT,
    longitude    FLOAT,
    capacity     INTEGER
);
```

---

## Setup & Installation

### Prerequisites

- Python 3.11+
- Node.js 18+
- Expo CLI: `npm install -g expo-cli`
- EAS CLI: `npm install -g eas-cli`
- A Supabase project (free tier works)
- API keys (see [Environment Variables](#environment-variables))

---

### Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate           # Windows
source venv/bin/activate        # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Create .env file
# (See Environment Variables section — copy keys into backend/.env)

# Apply database schema
# → Supabase dashboard → SQL editor → paste database/schema.sql

# Start server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- API docs: `http://localhost:8000/docs`
- Admin dashboard: `http://localhost:8000/admin`

---

### Mobile App Setup

```bash
cd mobile-app

npm install

# Set backend URL
# Edit constants/api.ts:
#   For physical device on same WiFi: 'http://<YOUR_WIFI_IP>:8000'
#   For production:                   'https://your-railway-url.up.railway.app'

npx expo start
# Scan QR with Expo Go
# Press 'a' for Android emulator  |  'w' for web
```

> Push notifications and background location require a custom EAS build — they do not work in Expo Go.

---

## Deployment

### Backend → Railway

1. Go to **railway.app** → New Project → Deploy from GitHub
2. Select repo `nikileshs194-hash/AV26-107`, set root directory to `backend`
3. Add environment variables in the Railway Variables panel (see below)
4. Railway auto-detects the `Procfile` and deploys
5. You'll get a URL like `https://av26-107-production.up.railway.app`

**Verify:**
- `https://your-url.up.railway.app/docs` — FastAPI interactive docs
- `https://your-url.up.railway.app/admin` — Admin dashboard

**Cost:** ~$5/month (Railway Hobby plan)

---

### Mobile App → EAS Build (APK)

After getting the Railway URL, update `mobile-app/constants/api.ts`:

```ts
const BACKEND_URL = 'https://your-railway-url.up.railway.app';
```

Then build:

```bash
cd mobile-app
eas login        # login with Expo account: nikiklesh38
eas build --platform android --profile preview
# Takes ~10–15 min. Returns a direct APK download link.
```

Install the `.apk` directly on the Android device. This build supports full push notifications (unlike Expo Go).

---

## Environment Variables

Create `backend/.env`:

```env
# Weather
OPENWEATHER_API_KEY=your_openweathermap_api_key

# AI (Groq)  — https://console.groq.com  (free tier)
GROQ_API_KEY=your_groq_api_key

# AI (Google Gemini optional fallback)
GEMINI_API_KEY=your_gemini_api_key

# Database (Supabase)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
SUPABASE_SERVICE_KEY=your_supabase_service_role_key

# SMS OTP — https://2factor.in  (free 10k SMS/month, India)
TWOFACTOR_KEY=your_2factor_api_key
```

### API Key Sources

| Key | Where to Get |
|-----|-------------|
| `OPENWEATHER_API_KEY` | openweathermap.org/api — Free tier: 1,000 calls/day |
| `GROQ_API_KEY` | console.groq.com — Free tier |
| `GEMINI_API_KEY` | aistudio.google.com — Free tier |
| `SUPABASE_URL/KEY` | Supabase project → Settings → API |
| `SUPABASE_SERVICE_KEY` | Supabase project → Settings → API → service_role |
| `TWOFACTOR_KEY` | 2factor.in — Indian SMS OTP service |

No key needed for: Open-Meteo, GDACS, USGS (all free/public), or Expo Push.

---

## Screens & UI

### Auth Flow

| Screen | Description |
|--------|-------------|
| **Login** | Dark glass card on navy gradient, animated logo glow, country code selector |
| **Verify OTP** | 6-box OTP input, shake animation on wrong code, countdown resend timer |
| **Profile Setup** | 3-step progress dots, name / age / gender |

### Main App

| Screen | Description |
|--------|-------------|
| **Home (Weather)** | Deep blue gradient weather card, 6-metric pill layout, 24h hourly scroll, 7-day forecast, flood prediction card, pulsing SOS button |
| **Alerts** | Staggered card entrance animation, severity strip, offline banner when cached |
| **AI Chat** | Gradient hero, suggestion cards, premium chat bubbles, animated typing indicator, voice input overlay |

### Alert Modals

Each modal is a slide-up bottom sheet with `Animated.spring`, scroll view, colored info rows, navigation button, and SOS + I AM SAFE emergency buttons:

| Modal | Icon | Key Info Shown |
|-------|------|---------------|
| SOSAlertModal | 🆘 | User name, distance, category, call/navigate actions |
| FloodAlertModal | 🌊 | Flood probability, rainfall, nearest shelter navigation |
| CycloneAlertModal | 🌀 | IMD category, risk level, cyclone shelter navigation |
| EarthquakeAlertModal | 🪨 | BIS seismic zone, risk level, assembly point navigation |

---

## Security

### Admin Endpoints
All `/admin/*` endpoints require an API key:

```
# Query parameter
GET /admin/data?admin_key=your_key

# HTTP header
X-Admin-Key: your_key
```

Returns `403 Forbidden` on mismatch.

### OTP Security
- OTPs expire after 5 minutes
- Delivered via SMS (not stored client-side)
- Phone number verified server-side before user creation

---

## Background Location Tracking

JeevanSetu uses **Expo TaskManager + expo-location** to track user location in the background, enabling SOS dispatch and nearby-person features even when the app is closed.

1. On login: requests foreground permission → sends initial location → requests background permission → starts `startLocationUpdatesAsync`
2. `tasks/locationTask.ts`: OS-level task registered globally at module load. On every GPS event, reads phone from AsyncStorage and POSTs to `/api/auth/update-location`

> Background location requires a custom EAS build — does not work in Expo Go.

---

## Offline Support

### Alert Cache
When the backend is unreachable, the Alerts screen loads the most recent alerts from AsyncStorage. An amber banner shows to indicate cached data.

### AsyncStorage Keys

| Key | Content |
|-----|---------|
| `jeevansetu_user` | Serialised user object — restores session across restarts |
| `jeevansetu_offline_alerts` | Last fetched alerts array — offline fallback |
| `jeevansetu_rescue_phone` | Configurable emergency contact (default: 112) |

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit: `git commit -m "feat: add my feature"`
4. Push: `git push origin feature/my-feature`
5. Open a Pull Request

---

## License

This project is licensed under the MIT License.

---

<div align="center">

Built with ❤️ for disaster-resilient communities.

**JeevanSetu** — *Setu* means bridge. A bridge between citizens and safety.

</div>
