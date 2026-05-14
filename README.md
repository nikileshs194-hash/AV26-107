# JeevanSetu — AI-Powered Flood & Disaster Response System

<div align="center">

![JeevanSetu](https://img.shields.io/badge/JeevanSetu-Flood%20AI-2563eb?style=for-the-badge&logo=shield&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Expo](https://img.shields.io/badge/Expo-54.0-000020?style=for-the-badge&logo=expo&logoColor=white)
![ML Model](https://img.shields.io/badge/VotingEnsemble-ML%20Model-f7931e?style=for-the-badge)
![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ecf8e?style=for-the-badge&logo=supabase&logoColor=white)

**Before Disaster Strikes — JeevanSetu Acts.**

A full-stack emergency response platform combining real-time weather intelligence, AI-powered flood prediction, emergency SOS coordination, and a premium mobile experience — built for India's disaster preparedness needs.

</div>

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [API Reference](#api-reference)
- [ML Model](#ml-model)
- [Database Schema](#database-schema)
- [Setup & Installation](#setup--installation)
  - [Backend](#backend-setup)
  - [Mobile App](#mobile-app-setup)
  - [Admin Dashboard](#admin-dashboard-setup)
- [Environment Variables](#environment-variables)
- [Screens & UI](#screens--ui)
- [Security](#security)
- [Background Location Tracking](#background-location-tracking)
- [Offline Support](#offline-support)

---

## Overview

JeevanSetu is a disaster-preparedness system built for real-world deployment. It gives citizens real-time flood risk forecasts, emergency SOS dispatch, AI-powered safety guidance, and offline-resilient alerts — all from a single mobile app.

The system integrates:
- **3 live weather APIs** (OpenWeatherMap, NOAA, Open-Meteo)
- **Voting ensemble ML model** (XGBoost + GradientBoosting + RandomForest) for 12-hour flood probability prediction
- **Groq LLM + Whisper** for voice-enabled AI assistance
- **Supabase** as the real-time database and user store
- **SMS OTP authentication** via 2Factor.in
- **Expo background location** for persistent user tracking

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        MOBILE APP (Expo)                        │
│  Auth Flow → Weather Tab → Alerts Tab → AI Chat Tab             │
│  Background Location Task (persists across app restarts)        │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP / REST (Axios)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FASTAPI BACKEND                               │
│  /api/weather   /api/alerts   /api/chat   /api/sos              │
│  /api/auth      /predict      /admin/*                          │
│                                                                  │
│  Services: weather · alert · risk · AI · auth · SMS · scheduler │
└──────┬──────────────┬─────────────────┬────────────────────────┘
       │              │                 │
       ▼              ▼                 ▼
  Supabase      OpenWeather         Groq API
  PostgreSQL    NOAA / Open-Meteo   (LLM + Whisper)
  (users,       (live weather)      (chat + voice)
  sos, shelters)
       │
       ▼
  Voting Ensemble
  (flood_probability)
```

---

## Features

### 🌦️ Weather Intelligence
- Real-time current conditions: temperature, humidity, wind, UV index, visibility, air quality, pressure
- 24-hour hourly forecast with rain probability per slot
- 7-day daily forecast with high/low temperatures
- Multi-source fusion (OWM + NOAA + Open-Meteo) for reliability

### 🤖 AI Flood Prediction
- Voting ensemble (XGBoost + GradientBoosting + RandomForest) trained on real Indian flood events across 30 cities
- Returns risk level (Very Low / Low / Moderate / High), flood probability %, and actionable advice
- 12-hour prediction window updated on every screen refresh

### 🚨 Emergency SOS
- One-tap SOS with emergency category selection (Flooding / Stranded / Injured)
- Automatic reverse geocoding to attach a human-readable address
- SOS stored in database and surfaced on the rescue team dashboard immediately
- **"Call Nearby People"** action (separate from SOS tap) — sends Expo push notifications to all registered users within radius and returns the nearest person for direct dial
- Nearest-person finder with direct-dial option via `GET /api/sos/find-nearest`
- Configurable rescue contact number (stored per-device, defaults to 112)
- Rescue team HTML dashboard at `/api/sos/dashboard` (API-key protected)

### 🔔 Real-Time Alerts
- NOAA official weather alerts (US coverage)
- OpenWeatherMap severe conditions detection
- Severity classification: Extreme / Severe / Moderate / Minor
- Offline alert cache — last known alerts served when network is unavailable

### 💬 AI Chat Assistant
- Natural language Q&A powered by Groq's `llama-3.3-70b-versatile`
- Location-aware context injection (lat/lon sent with every message)
- Voice input via Groq Whisper transcription (native) or Web Speech API (browser)
- Conversation history (last 10 messages) for coherent multi-turn dialogue
- Follow-up suggestion chips updated dynamically by the model

### 🔐 Authentication
- Phone-based OTP login (no passwords)
- SMS delivery via 2Factor.in API
- 60-second resend timer with shake animation on wrong code
- Profile setup: full name, age, gender (used for emergency response prioritisation)
- Token stored locally in AsyncStorage

### 🗺️ Location & Shelter Finder
- Foreground + background GPS tracking (50 m / 60 s intervals)
- Location sent to backend on every significant movement
- Haversine-based nearest shelter calculation from Supabase

### 🛡️ Admin Dashboard
- Live SOS request feed with user location, category, status
- Demo flood simulation tool for testing push notifications
- API-key gated (query param `?admin_key=` or `X-Admin-Key` header)
- Browser-side key stored in `localStorage`

---

## Project Structure

```
flood-ai-system/
│
├── backend/                    # FastAPI server
│   ├── main.py                 # App entry point, CORS, route registration
│   ├── config.py               # Environment variable loading
│   ├── requirements.txt        # Python dependencies
│   ├── Dockerfile              # Container build
│   │
│   ├── routes/
│   │   ├── weather.py          # GET /api/weather
│   │   ├── alerts.py           # GET /api/alerts, POST /api/alerts/save
│   │   ├── chat.py             # POST /api/chat (LLM + audio transcription)
│   │   ├── sos.py              # SOS dispatch, nearby notify, shelters
│   │   ├── predict.py          # GET /predict  (ML flood model)
│   │   ├── auth.py             # OTP send/verify, profile, location
│   │   └── admin.py            # Admin dashboard + API (key-protected)
│   │
│   ├── services/
│   │   ├── weather_service.py  # OWM + NOAA + Open-Meteo fusion
│   │   ├── alert_service.py    # Alert engine (multi-source)
│   │   ├── risk_service.py     # ML-based risk score
│   │   ├── ai_service.py       # Groq LLM integration
│   │   ├── auth_service.py     # OTP logic, user CRUD
│   │   ├── sms_service.py      # 2Factor.in SMS delivery
│   │   ├── supabase_service.py # DB client, shelter queries
│   │   └── scheduler.py        # Background task runner
│   │
│   ├── train_model.py          # Legacy script — 9 features, synthetic data (do not use for prod)
│   ├── collect_and_train.py    # Production training — 12 features, real ERA5+OSM data
│   └── model.pkl               # Serialised trained model
│
├── mobile-app/                 # Expo / React Native app
│   ├── app/
│   │   ├── (auth)/
│   │   │   ├── _layout.tsx     # Auth stack layout
│   │   │   ├── login.tsx       # Phone number entry
│   │   │   ├── verify.tsx      # OTP verification
│   │   │   └── profile-setup.tsx # Name / age / gender
│   │   │
│   │   ├── (tabs)/
│   │   │   ├── _layout.tsx     # Tab navigator + background location init
│   │   │   ├── index.tsx       # Home: weather card, flood prediction, SOS
│   │   │   ├── alerts.tsx      # Real-time alerts with offline cache
│   │   │   └── ai.tsx          # AI chat + voice input
│   │   │
│   │   ├── _layout.tsx         # Root layout (AuthProvider, fonts)
│   │   └── modal.tsx           # Generic modal
│   │
│   ├── components/
│   │   ├── Header.tsx          # Location display + profile dropdown
│   │   ├── FloodAlertModal.tsx # Alert detail modal
│   │   ├── SOSAlertModal.tsx   # Incoming SOS notification modal
│   │   └── ui/                 # Shared primitives
│   │
│   ├── services/
│   │   ├── api.ts              # All backend API calls + TypeScript types
│   │   └── auth.ts             # Auth-specific API calls
│   │
│   ├── hooks/
│   │   ├── useLocation.ts      # GPS hook (expo-location)
│   │   └── use-color-scheme.ts # Light/dark theme detection
│   │
│   ├── tasks/
│   │   └── locationTask.ts     # Expo TaskManager background handler
│   │
│   ├── context/
│   │   └── AuthContext.tsx     # Global user state + AsyncStorage
│   │
│   ├── constants/
│   │   ├── api.ts              # BACKEND_URL
│   │   └── theme.ts            # Design tokens (colors, spacing)
│   │
│   ├── app.json                # Expo config (permissions, bundle ID)
│   ├── package.json
│   └── tsconfig.json
│
├── dashboard/                  # Next.js admin map dashboard
│   ├── app/
│   │   ├── page.tsx            # Home (FloodMap component)
│   │   └── layout.tsx
│   ├── components/
│   │   └── FloodMap.tsx        # React Leaflet flood risk map
│   └── package.json
│
├── ai-model/                   # Standalone ML training
│   ├── train_model.py
│   ├── model.pkl
│   └── dataset.csv
│
├── database/
│   └── schema.sql              # Supabase table definitions
│
└── supabase_migration.sql      # Migration script
```

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Mobile Framework | Expo / React Native | 54.0 / 0.81.5 |
| Language (mobile) | TypeScript | 5.9 |
| Navigation | Expo Router | 6.0 |
| Backend Framework | FastAPI | 0.136 |
| Language (backend) | Python | 3.11+ |
| ML Model | VotingEnsemble (XGBoost + GradientBoosting + RandomForest) | XGBoost 3.2, scikit-learn 1.8 |
| Database | Supabase (PostgreSQL) | — |
| AI / LLM | Groq (llama-3.3-70b) | — |
| Voice STT | Groq Whisper | — |
| Weather APIs | OpenWeatherMap, NOAA, Open-Meteo | — |
| SMS | 2Factor.in | — |
| Admin Dashboard | Next.js + Leaflet | 16 / 5.0 |
| Styling | Expo LinearGradient + StyleSheet | — |
| Storage (mobile) | AsyncStorage | 2.2 |
| HTTP Client | Axios | 1.16 |

---

## API Reference

### Weather

| Method | Endpoint | Query Params | Description |
|--------|----------|-------------|-------------|
| `GET` | `/api/weather` | `lat`, `lon` | Full weather: current, hourly (24h), daily (7d), risk assessment |

**Response shape (condensed):**
```json
{
  "current": { "temp": 28, "humidity": 72, "wind_speed": 14, "uv_label": "High", "air_quality": { "label": "Moderate", "aqi": 82 }, ... },
  "hourly": [ { "time": "14:00", "temp": 29, "icon": "rainy-outline", "rain_prob": 40 } ],
  "daily":  [ { "day": "Mon", "temp_min": 22, "temp_max": 31, "rain_prob": 55, "icon": "thunderstorm-outline" } ],
  "risk":   { "risk_level": "Moderate", "risk_color": "#F59E0B", "breakdown": [...] }
}
```

---

### Flood Prediction

| Method | Endpoint | Query Params | Description |
|--------|----------|-------------|-------------|
| `GET` | `/predict` | `lat`, `lon` | Voting ensemble flood probability for next 12 hours |

**Response:**
```json
{
  "flood_predicted": true,
  "probability": 0.73,
  "risk_level": "High",
  "forecast_window": "12 hours",
  "features": {
    "rainfall_1h": 12.4, "rainfall_24h": 48.0, "humidity": 88.0,
    "temperature": 27.5, "elevation": 14.0, "soil_moisture": 0.81,
    "drainage": 3.2, "slope": 0.45, "pressure": 1001.2,
    "sat_index": 38.88, "rain_burst": 0.2583, "drain_eff": 0.304
  },
  "advice": ["Move valuables to higher ground", "Avoid low-lying roads"]
}
```

---

### Alerts

| Method | Endpoint | Query Params / Body | Description |
|--------|----------|---------------------|-------------|
| `GET` | `/api/alerts` | `lat`, `lon` | Fetch active alerts for location (OWM + NOAA) |
| `POST` | `/api/alerts/save` | `{ phone, alert_id, ... }` | Save alert to user's saved list |
| `GET` | `/api/alerts/saved` | `phone` | Fetch all alerts saved by a user |
| `DELETE` | `/api/alerts/clear` | `phone`, `db_id` | Delete a saved alert by its DB row ID |

---

### Chat / AI

| Method | Endpoint | Body | Description |
|--------|----------|------|-------------|
| `POST` | `/api/chat` | `{ message, history[], lat?, lon? }` | LLM chat response + follow-up suggestions |
| `POST` | `/api/chat/transcribe` | `form-data: audio` | Groq Whisper audio → text |

---

### SOS & Emergency

| Method | Endpoint | Body / Params | Description |
|--------|----------|---------------|-------------|
| `POST` | `/api/sos` | `{ phone, category, latitude, longitude }` | File SOS alert — stores to DB (with reverse-geocoded address), deduplicates by phone |
| `POST` | `/api/sos/notify-nearby` | `{ lat, lon, message? }` | Push Expo notifications to all nearby users; returns nearest person |
| `POST` | `/api/sos/push-token` | `{ phone, token }` | Register / update Expo push token for a user |
| `GET` | `/api/sos/find-nearest` | `lat`, `lon` | Return nearest registered user (name + phone + distance) |
| `GET` | `/api/sos/shelters` | `lat`, `lon` | Nearest shelters sorted by Haversine distance |
| `PUT` | `/api/sos/{id}/resolve` | — | Mark SOS request as resolved |
| `GET` | `/api/sos/dashboard` | — | Rescue team HTML dashboard (browser, JS-prompted key) |
| `GET` | `/api/sos/dashboard/data` | `?admin_key=` | JSON data feed for the rescue dashboard |

---

### Authentication

| Method | Endpoint | Body | Description |
|--------|----------|------|-------------|
| `POST` | `/api/auth/send-otp` | `{ phone, country_code }` | Send OTP SMS |
| `POST` | `/api/auth/verify-otp` | `{ phone, otp }` | Verify OTP, create/return user |
| `POST` | `/api/auth/update-profile` | `{ phone, full_name, age, gender }` | Save profile |
| `GET` | `/api/auth/profile/{phone}` | — | Fetch user profile |
| `POST` | `/api/auth/update-location` | `{ phone, latitude, longitude }` | Update live location |

---

### Admin (API-key required)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/admin/data` | `?admin_key=` or `X-Admin-Key` | Live SOS + user data |
| `POST` | `/admin/demo-flood` | `?admin_key=` | Simulate flood event for testing |
| `GET` | `/admin/dashboard` | — (HTML with JS prompt) | Browser-based rescue dashboard |

---

## ML Model

The production flood prediction model is a **soft-voting ensemble** of three classifiers — XGBoost, GradientBoostingClassifier, and RandomForest — all wrapped in a `StandardScaler` pipeline. It is trained on **real historical flood events** from 30 Indian cities (ERA5 archive data) and validated with 5-fold stratified cross-validation.

> ⚠️ **Two training scripts exist — use the right one:**
> - `train_model.py` — basic script, 9 features, **synthetic** data. Does **not** match the prediction endpoint.
> - `collect_and_train.py` — production script, **12 features**, real ERA5 + OSM data. **This is the one to use.**

---

### Model Architecture (`collect_and_train.py`)

| Sub-model | Key Hyperparameters |
|-----------|-------------------|
| **XGBoost** | n_estimators=500, max_depth=5, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8, gamma=0.1, scale_pos_weight=auto |
| **GradientBoosting** | n_estimators=400, max_depth=4, learning_rate=0.06, subsample=0.85, max_features=sqrt |
| **RandomForest** | n_estimators=300, max_depth=8, class_weight=balanced |
| **Ensemble** | VotingClassifier (soft vote), StandardScaler pre-processing |
| **Validation** | 5-fold stratified cross-validation (AUC, F1, Precision, Recall) |
| **Data** | 210+ real flood + dry events, 30 Indian cities, ERA5 historical archive |

---

### All 12 Features Used

**9 Base Features**

| # | Feature | Source | Unit | Description |
|---|---------|--------|------|-------------|
| 1 | `rainfall_1h` | Open-Meteo forecast | mm | Peak hourly rainfall in the 12h forecast window |
| 2 | `rainfall_24h` | Open-Meteo forecast + archive | mm | Past 12h observed + next 12h forecast total |
| 3 | `humidity` | Open-Meteo forecast | % | Relative humidity at +12h forecast slot |
| 4 | `temperature` | Open-Meteo forecast | °C | Temperature at +12h forecast slot |
| 5 | `elevation` | Open-Meteo Elevation API (DEM) | m | Real terrain elevation at the coordinate |
| 6 | `soil_moisture` | Open-Meteo (current) | 0–1 | Surface soil moisture fraction (0–1 cm depth) |
| 7 | `drainage` | OpenStreetMap Overpass API | 0–10 | Count of drains/manholes/canals/ditches within 1 km → normalised to 1–9 scale |
| 8 | `slope` | Open-Meteo Elevation API (5-point DEM) | degrees | Terrain slope computed from N/S/E/W elevation gradient (~500 m offset) |
| 9 | `pressure` | Open-Meteo forecast | hPa | Surface pressure at +12h forecast slot |

**3 Engineered (Interaction) Features**

| # | Feature | Formula | Description |
|---|---------|---------|-------------|
| 10 | `sat_index` | `soil_moisture × rainfall_24h` | Ground saturation load — how much water a near-saturated soil must absorb |
| 11 | `rain_burst` | `rainfall_1h ÷ max(rainfall_24h, 1)` | Intensity ratio — distinguishes flash floods (high) from sustained rain (low) |
| 12 | `drain_eff` | `drainage × (slope + 0.5) ÷ 10` | Combined drainage efficiency — steep + well-drained = high score = safer |

---

### How the Prediction Endpoint Fetches Features at Runtime

When `GET /predict?lat=X&lon=Y` is called, **all 12 values are auto-fetched** — no manual input needed beyond coordinates:

| Feature(s) | Live Data Source |
|-----------|-----------------|
| `rainfall_1h`, `rainfall_24h`, `humidity`, `temperature`, `pressure` | **Open-Meteo forecast API** — past 12h archive + next 12h forecast |
| `soil_moisture` | **Open-Meteo current** — real-time 0–1 cm surface soil moisture |
| `elevation`, `slope` | **Open-Meteo Elevation API** — real DEM, computed from 5-point gradient |
| `drainage` | **OpenStreetMap Overpass API** — live infrastructure query within 1 km |
| `sat_index`, `rain_burst`, `drain_eff` | **Computed** server-side from above values |

---

### Flood Risk Thresholds

| Probability | Risk Level |
|------------|-----------|
| ≥ 75% | 🔴 **High** |
| 45–74% | 🟡 **Moderate** |
| 20–44% | 🟢 **Low** |
| < 20% | ⚪ **Very Low** |

---

### Training the Production Model

```bash
cd backend
python collect_and_train.py
# Fetches ERA5 data for 210+ real flood events across 30 Indian cities
# Fetches real slope + elevation from Open-Meteo DEM for each location
# Fetches real drainage density from OpenStreetMap for each location
# Runs 5-fold stratified cross-validation
# Outputs: model.pkl + flood_dataset_real.csv
# Takes ~10–15 minutes (network-bound)
```

> Do **not** use `train_model.py` for production — it trains on synthetic data with only 9 features and will cause a feature-count mismatch error in `predict.py` which expects all 12 features.

The model is loaded at server startup from `model.pkl` and used by `GET /predict`.

---

## Database Schema

The following tables are defined in `database/schema.sql` and must be created in your Supabase project before running the backend.

```sql
-- Users (registered app users)
CREATE TABLE users (
    id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name      TEXT,
    phone     TEXT,
    latitude  FLOAT,
    longitude FLOAT,
    status    TEXT
);

-- Flood zones (risk zone polygons)
CREATE TABLE flood_zones (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    area_name   TEXT,
    risk_level  TEXT,        -- 'Low' | 'Moderate' | 'High'
    coordinates JSONB        -- GeoJSON polygon
);

-- SOS requests
CREATE TABLE sos_requests (
    id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id   UUID,
    latitude  FLOAT,
    longitude FLOAT,
    severity  TEXT,          -- 'Flooding' | 'Stranded' | 'Injured'
    status    TEXT           -- 'pending' | 'resolved'
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

> **Note:** The `user_alerts` table is used by the `/api/alerts/save`, `/api/alerts/saved`, and `/api/alerts/clear` routes. It is **not** in `schema.sql` — create it manually in Supabase:
>
> ```sql
> CREATE TABLE user_alerts (
>     id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
>     phone        TEXT,
>     alert_id     TEXT,
>     title        TEXT,
>     description  TEXT,
>     severity     TEXT,
>     source       TEXT,
>     location     TEXT,
>     icon         TEXT,
>     icon_bg      TEXT,
>     icon_color   TEXT,
>     border_color TEXT,
>     when_text    TEXT,
>     when_color   TEXT,
>     created_at   TIMESTAMPTZ DEFAULT now(),
>     UNIQUE (phone, alert_id)
> );
> ```

---

## Setup & Installation

### Prerequisites

- Python 3.11+
- Node.js 18+
- Expo CLI (`npm install -g expo-cli`)
- A Supabase project
- API keys (see [Environment Variables](#environment-variables))

---

### Backend Setup

```bash
# 1. Navigate to backend
cd backend

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file (see Environment Variables section)
cp .env.example .env
# Edit .env with your keys

# 5. Run the database migration
# In your Supabase dashboard → SQL editor → paste contents of database/schema.sql

# 6. Start the server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

#### Docker (optional)

```bash
cd backend
docker build -t jeevansetu-backend .
docker run -p 8000:8000 --env-file .env jeevansetu-backend
```

---

### Mobile App Setup

```bash
# 1. Navigate to mobile app
cd mobile-app

# 2. Install dependencies
npm install

# 3. Set your backend URL
# Edit constants/api.ts:
#   BACKEND_URL = 'http://<YOUR_LOCAL_IP>:8000'   ← for physical device
#   BACKEND_URL = 'http://localhost:8000'           ← for web/emulator

# 4. Start Expo development server
npx expo start

# Scan the QR code with Expo Go (Android/iOS)
# Press 'w' for web browser
# Press 'a' for Android emulator
# Press 'i' for iOS simulator
```

> **Note:** Background location and push notifications require a **custom development build** (`npx expo run:android` / `npx expo run:ios`). They will not work in Expo Go.

#### Build for production

```bash
# Install EAS CLI
npm install -g eas-cli

# Configure EAS project
eas build:configure

# Build for Android
eas build --platform android

# Build for iOS
eas build --platform ios
```

---

### Admin Dashboard Setup

```bash
# 1. Navigate to dashboard
cd dashboard

# 2. Install dependencies
npm install

# 3. Start development server
npm run dev
# → http://localhost:3000
```

---

## Environment Variables

Create `backend/.env` with the following:

```env
# ── Weather ────────────────────────────────────────────────────────
OPENWEATHER_API_KEY=your_openweathermap_api_key

# ── AI (Groq) ──────────────────────────────────────────────────────
GROQ_API_KEY=your_groq_api_key
# Get free key at: https://console.groq.com

# ── AI (optional — Google Gemini fallback) ─────────────────────────
GEMINI_API_KEY=your_gemini_api_key

# ── Database (Supabase) ────────────────────────────────────────────
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
SUPABASE_SERVICE_KEY=your_supabase_service_role_key

# ── SMS (2Factor.in) ───────────────────────────────────────────────
TWOFACTOR_KEY=your_2factor_api_key
# Get key at: https://2factor.in

# ── Admin Dashboard ────────────────────────────────────────────────
ADMIN_API_KEY=your_secure_admin_key_here
# Set a strong random value for production. Default: js-admin-secure-2024
```

### API Key Sources

| Key | Where to Get |
|-----|-------------|
| `OPENWEATHER_API_KEY` | [openweathermap.org/api](https://openweathermap.org/api) — Free tier: 1,000 calls/day |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) — Free tier |
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com) — Free tier |
| `SUPABASE_URL/KEY` | Supabase project → Settings → API |
| `SUPABASE_SERVICE_KEY` | Supabase project → Settings → API → service_role |
| `TWOFACTOR_KEY` | [2factor.in](https://2factor.in) — SMS OTP service |

---

## Screens & UI

### Auth Flow

| Screen | Description |
|--------|-------------|
| **Login** | Dark glass card on navy gradient, animated logo glow, country code selector, gradient OTP button |
| **Verify OTP** | 6-box OTP input with progress bar, shake animation on wrong code, countdown resend timer |
| **Profile Setup** | 3-step progress dots, name / age / gender, privacy note |

### Main App

| Screen | Description |
|--------|-------------|
| **Weather (Home)** | Deep blue gradient weather card with 6-metric pill layout, 24h hourly scroll, 7-day forecast, risk gauge, AI flood prediction card, pulsing SOS button |
| **Alerts** | Staggered card entrance animation, left severity strip, summary chips (Extreme/Severe/Moderate count), offline banner when cached |
| **AI Chat** | Gradient hero, suggestion cards, premium chat bubbles (gradient user / bordered AI), animated 3-dot typing indicator, voice overlay with waveform |

### Emergency Features

| Feature | Behaviour |
|---------|-----------|
| **SOS Button** | Pulsing red rings, tap → category picker modal (Flooding / Stranded / Injured) → dispatches SOS + shows address confirmation |
| **Call Rescue** | Dials configurable rescue number (default 112), editable via gear icon → number saved to AsyncStorage |
| **Nearby People** | Calls `POST /api/sos/notify-nearby` — pushes Expo notifications to all users within radius and offers direct dial to nearest person returned by `GET /api/sos/find-nearest` |

---

## Security

### Backend Admin Endpoints

All `/admin/*` endpoints require an API key:

```
# Via query parameter
GET /admin/data?admin_key=your_key

# Via HTTP header
GET /admin/data
X-Admin-Key: your_key
```

The key is validated against `ADMIN_API_KEY` in `.env`. Returns `403 Forbidden` on mismatch.

### Admin Dashboard (Browser)

The HTML rescue dashboard prompts for the admin key on first load and stores it in `localStorage`. All subsequent API calls append `?admin_key=` automatically. Invalid key clears the stored value and re-prompts.

### OTP Security

- OTPs expire after 5 minutes
- Delivered via SMS (not in-app)
- Phone number verified server-side before user creation

---

## Background Location Tracking

JeevanSetu uses **Expo TaskManager + expo-location** to track user location in the background, enabling the SOS and nearby-person features even when the app is closed.

### How It Works

1. **`(tabs)/_layout.tsx`** — On user login, requests foreground permission first, sends an initial location update, then requests background permission and starts `startLocationUpdatesAsync`.
2. **`tasks/locationTask.ts`** — The OS-level task handler registered globally at module load time. On every location event it reads the stored phone number from AsyncStorage and POSTs to `/api/auth/update-location`.

### Permissions Required

**iOS (`app.json` → `ios.infoPlist`):**
```json
"infoPlist": {
  "NSLocationWhenInUseUsageDescription": "...",
  "NSLocationAlwaysAndWhenInUseUsageDescription": "...",
  "NSLocationAlwaysUsageDescription": "...",
  "UIBackgroundModes": ["location", "fetch", "remote-notification"]
}
```

**Android (`app.json` → `android.permissions`):**
```json
"permissions": [
  "ACCESS_FINE_LOCATION",
  "ACCESS_COARSE_LOCATION",
  "ACCESS_BACKGROUND_LOCATION",
  "POST_NOTIFICATIONS",
  "RECEIVE_BOOT_COMPLETED",
  "VIBRATE",
  "WAKE_LOCK",
  "RECORD_AUDIO",
  "android.permission.ACCESS_COARSE_LOCATION",
  "android.permission.ACCESS_FINE_LOCATION"
]
```

> Background location requires a **custom dev build** — it does not work in Expo Go.

---

## Offline Support

### Alert Cache

When the backend is unreachable, the Alerts screen loads the most recently fetched alerts from AsyncStorage (`jeevansetu_offline_alerts`). An amber banner is shown to indicate cached data.

```
Fetch alerts → success  → save to AsyncStorage → display
            → failure  → load from AsyncStorage → display with offline banner
```

### Rescue Contact

The configurable rescue phone number is stored in AsyncStorage (`jeevansetu_rescue_phone`) and is available without network access. Default value is `112`.

### AsyncStorage Keys

| Key | Content | Used By |
|-----|---------|---------|
| `jeevansetu_user` | Serialised user object (phone, full_name, age, gender) | `AuthContext` — restores session across app restarts |
| `jeevansetu_offline_alerts` | Last fetched alerts array (JSON) | Alerts screen offline fallback |
| `jeevansetu_rescue_phone` | Configurable emergency contact number | Home screen call-rescue button |

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m "feat: add my feature"`
4. Push to the branch: `git push origin feature/my-feature`
5. Open a Pull Request

---

## License

This project is licensed under the MIT License.

---

<div align="center">

Built with ❤️ for disaster-resilient communities.

**JeevanSetu** — *Setu* means bridge. A bridge between citizens and safety.

</div>
