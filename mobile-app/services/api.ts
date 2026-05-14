import axios from 'axios';
import BACKEND_URL from '@/constants/api';

const api = axios.create({ baseURL: BACKEND_URL, timeout: 25000 });

export interface WeatherCurrent {
  city: string; country: string; lat: number; lon: number;
  temp: number; feels_like: number; temp_min: number; temp_max: number;
  humidity: number; pressure: number; visibility: number;
  wind_speed: number; wind_dir: string;
  condition: string; description: string; icon: string;
  rain_1h: number; uv_index: number; uv_label: string;
  air_quality: { aqi: number; label: string; color: string };
}

export interface HourlyItem {
  time: string; temp: number; icon: string; rain_prob: number; condition: string;
}

export interface DailyItem {
  day: string; temp_min: number; temp_max: number;
  icon: string; condition: string; rain_prob: number;
}

export interface RiskBreakdown {
  label: string; icon: string; level: string; color: string;
}

export interface RiskData {
  risk_level: string; risk_color: string;
  gauge_position: number; be_prepared: boolean;
  breakdown: RiskBreakdown[];
}

export interface HistoricalRainfall {
  total_30d: number;
  total_7d: number;
  avg_daily: number;
  saturation_index: number;
  days_data: number;
  sparkline: number[];
}

export interface WeatherResponse {
  current: WeatherCurrent;
  hourly: HourlyItem[];
  daily: DailyItem[];
  risk: RiskData;
  historical_rainfall?: HistoricalRainfall;
}

export interface AlertItem {
  id: string;
  db_id?: string;       // UUID from DB (used for individual delete)
  title: string; icon: string;
  iconBg: string; iconColor: string; borderColor: string;
  time: string; when: string; whenColor: string;
  desc: string; location: string; severity: string; source: string;
}

export interface AlertsResponse {
  alerts: AlertItem[]; source: string; count: number;
}

export interface ChatResponse {
  response: string; suggestions: string[];
}

export const fetchWeather = async (lat: number, lon: number): Promise<WeatherResponse> => {
  const res = await api.get('/api/weather', { params: { lat, lon } });
  return res.data;
};

export const fetchAlerts = async (lat: number, lon: number): Promise<AlertsResponse> => {
  const res = await api.get('/api/alerts', { params: { lat, lon } });
  return res.data;
};

export interface ChatHistoryMessage {
  role: 'user' | 'assistant';
  content: string;
  time: string;
}

export interface ChatHistoryResponse {
  phone: string;
  date: string;
  messages: ChatHistoryMessage[];
  count: number;
}

export const sendChatMessage = async (
  message: string,
  history: { role: string; content: string }[],
  lat?: number,
  lon?: number,
  phone?: string,
): Promise<ChatResponse> => {
  const res = await api.post('/api/chat', { message, history, lat, lon, phone }, { timeout: 30000 });
  return res.data;
};

export const fetchChatHistory = async (phone: string): Promise<ChatHistoryResponse> => {
  const res = await api.get('/api/chat/history', { params: { phone } });
  return res.data;
};

export const clearChatHistory = async (phone: string): Promise<void> => {
  await api.delete('/api/chat/history', { params: { phone } });
};

// ── Emergency / SOS ──────────────────────────────────────────────────────────

export interface SOSResponse {
  success: boolean;
  sos_id: string;
  address: string;
  google_maps_url: string;
  notified_count: number;
  message: string;
}

export interface NearbyUser {
  name: string;
  distance_m: number;
}

export interface NotifyNearbyResponse {
  success: boolean;
  notified_count: number;
  nearest_phone: string | null;
  nearest_name: string | null;
  nearest_dist_m: number | null;
  nearest_dist_str: string | null;
  nearby_users: NearbyUser[];
}

/** Full SOS — stores alert, notifies nearby users, alerts rescue team */
export const sendSOS = async (
  phone: string,
  name: string,
  lat: number,
  lon: number,
  age?: number,
  message = 'Emergency SOS',
): Promise<SOSResponse> => {
  const res = await api.post('/api/sos', { phone, name, lat, lon, age, message, severity: 'High' });
  return res.data;
};

/** "Call Nearby People" — finds nearest users, sends them push notification */
export const notifyNearby = async (
  phone: string,
  name: string,
  lat: number,
  lon: number,
  radius_m = 2000,
): Promise<NotifyNearbyResponse> => {
  const res = await api.post('/api/sos/notify-nearby', { phone, name, lat, lon, radius_m });
  return res.data;
};

/** Save Expo push token so this user can receive SOS alerts */
export const savePushToken = async (phone: string, push_token: string): Promise<void> => {
  await api.post('/api/sos/push-token', { phone, push_token });
};

export interface FindNearestResponse {
  found: boolean;
  message?: string;
  nearest: {
    name: string;
    phone: string;
    distance_m: number;
    distance_str: string;
  } | null;
  total_nearby: number;
}

/** Find the nearest registered user — used by "Call Nearby People" to dial directly */
export const findNearest = async (
  phone: string,
  lat: number,
  lon: number,
  radius_m = 5000,
): Promise<FindNearestResponse> => {
  const res = await api.get('/api/sos/find-nearest', {
    params: { phone, lat, lon, radius_m },
  });
  return res.data;
};

export interface FloodPrediction {
  flood_predicted: boolean;
  probability: number;
  risk_level: 'Very Low' | 'Low' | 'Moderate' | 'High';
  forecast_window: string;
  features: {
    rainfall_1h: number;
    rainfall_24h: number;
    humidity: number;
    soil_moisture: number;
    elevation: number;
    drainage: number;
  };
  advice: string[];
}

export const fetchFloodPrediction = async (lat: number, lon: number): Promise<FloodPrediction> => {
  const res = await api.get('/predict', { params: { lat, lon }, timeout: 30000 });
  return res.data;
};

// ── Cyclone prediction ────────────────────────────────────────────────────────

export interface CycloneFeatures {
  wind_speed_kmh: number;
  wind_gusts_kmh: number;
  surface_pressure_hpa: number;
  pressure_6h_ago_hpa: number;
  pressure_drop_6h: number;
  pressure_anomaly_hpa: number;
  cape_jkg: number;
  precipitation_mm: number;
  humidity: number;
  tropical_instability: number;
  wind_intensity_index: number;
  wind_shear_kmh: number;        // vertical wind shear 200-850 hPa
  humidity_500hpa: number;       // mid-level humidity (dry air detection)
  coastal_proximity_km: number;
  season_factor: number;
  lat_abs?: number;
  gdacs_active: boolean;
  gdacs_name: string;
  gdacs_distance_km: number;
  gdacs_alert_level: string;
}

export interface CyclonePrediction {
  cyclone_risk: 'Very Low' | 'Low' | 'Moderate' | 'High' | 'Extreme';
  probability: number;
  category: string;
  cyclone_likely: boolean;
  features: CycloneFeatures;
  advice: string[];
  data_sources: string[];
  forecast_window: string;
  ml_model_active?: boolean;
}

export const fetchCyclonePrediction = async (lat: number, lon: number): Promise<CyclonePrediction> => {
  const res = await api.get('/api/cyclone', { params: { lat, lon }, timeout: 30000 });
  return res.data;
};

// ── Earthquake prediction ─────────────────────────────────────────────────────

export interface EarthquakeFeatures {
  recent_quakes_7d: number;
  recent_quakes_30d: number;
  max_mag_7d: number;
  max_mag_30d: number;
  energy_index_30d: number;
  b_value: number;
  cv_interevent: number;
  quake_acceleration: number;
  depth_avg_30d: number;
  depth_shallow_frac: number;
  dist_to_fault_km: number;
  seismic_zone: number;
  seismic_zone_label: string;
  total_events_bbox: number;
}

export interface EarthquakePrediction {
  earthquake_risk: 'Very Low' | 'Low' | 'Moderate' | 'High' | 'Unknown';
  probability: number;
  probability_pct: string;
  risk_high: boolean;
  forecast_window: string;
  target_radius_km: number;
  seismic_zone: string;
  features: EarthquakeFeatures;
  advice: string[];
  ml_model_active: boolean;
  data_sources: string[];
}

export const fetchEarthquakePrediction = async (lat: number, lon: number): Promise<EarthquakePrediction> => {
  const res = await api.get('/api/earthquake', { params: { lat, lon }, timeout: 30000 });
  return res.data;
};

// ── Alerts (DB-backed) ────────────────────────────────────────────────────────

/** Save freshly fetched alerts to DB for a user */
export const saveAlerts = async (phone: string, alerts: AlertItem[]): Promise<void> => {
  await api.post('/api/alerts/save', { phone, alerts });
};

/** Get all saved alerts for a user from DB */
export const getSavedAlerts = async (phone: string): Promise<{ alerts: AlertItem[] }> => {
  const res = await api.get('/api/alerts/saved', { params: { phone } });
  return res.data;
};

/** Delete one alert (db_id provided) or ALL alerts for user (no db_id) */
export const clearAlert = async (phone: string, db_id?: string): Promise<void> => {
  await api.delete('/api/alerts/clear', { params: db_id ? { phone, db_id } : { phone } });
};

// ── Voice transcription ───────────────────────────────────────────────────────

/**
 * Send a recorded audio file to the backend Groq Whisper endpoint.
 *
 * Uses multipart/form-data — the only approach React Native 0.73+ handles
 * reliably for local file:// URIs. RN's native networking reads the file from
 * disk and streams it as multipart without any extra libraries.
 */
export const transcribeAudio = async (audioUri: string): Promise<string> => {
  const filename = audioUri.split('/').pop() ?? 'recording.m4a';
  const ext      = filename.split('.').pop()?.toLowerCase() ?? 'm4a';

  // Map extension → MIME type that Groq Whisper accepts
  const MIME_MAP: Record<string, string> = {
    m4a: 'audio/m4a', mp4: 'audio/mp4', mp3: 'audio/mpeg',
    wav: 'audio/wav', webm: 'audio/webm', ogg: 'audio/ogg',
    flac: 'audio/flac', opus: 'audio/opus',
  };
  const mimeType = MIME_MAP[ext] ?? 'audio/m4a';

  // FormData with { uri, type, name } — React Native reads the local file and
  // sends it as multipart binary. This is the standard RN file-upload pattern.
  const formData = new FormData();
  formData.append('file', { uri: audioUri, type: mimeType, name: filename } as any);

  const response = await fetch(`${BACKEND_URL}/api/chat/transcribe`, {
    method:  'POST',
    body:    formData,
    // Do NOT set Content-Type manually — React Native adds the multipart
    // boundary automatically when the body is FormData.
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Transcription failed (${response.status}): ${errText.slice(0, 120)}`);
  }

  const data = await response.json();
  return (data.text ?? '').trim();
};
