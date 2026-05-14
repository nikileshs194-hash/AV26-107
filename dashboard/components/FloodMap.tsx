"use client";

import { MapContainer, TileLayer, Marker, Popup, Circle } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useState } from "react";
import L from "leaflet";

// Fix default Leaflet marker icon in Next.js
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

// ── Types ─────────────────────────────────────────────────────────────────────

interface FloodData {
  flood_predicted: boolean;
  probability: number;
  risk_level: string;
  features: {
    rainfall_1h: number;
    rainfall_24h: number;
    soil_moisture: number;
    elevation: number;
    drainage: number;
  };
  advice: string[];
}

interface CycloneData {
  cyclone_risk: string;
  probability: number;
  category: string;
  features: {
    wind_gusts_kmh: number;
    surface_pressure_hpa: number;
    pressure_drop_6h: number;
    coastal_proximity_km: number;
  };
  advice: string[];
  ml_model_active?: boolean;
}

interface EarthquakeData {
  earthquake_risk: string;
  probability: number;
  probability_pct: string;
  seismic_zone: string;
  features: {
    recent_quakes_7d: number;
    recent_quakes_30d: number;
    max_mag_30d: number;
    b_value: number;
    cv_interevent: number;
    quake_acceleration: number;
    depth_avg_30d: number;
    depth_shallow_frac: number;
    dist_to_fault_km: number;
  };
  advice: string[];
  ml_model_active: boolean;
}

// ── Config ────────────────────────────────────────────────────────────────────

const BACKEND =
  typeof window !== "undefined" && window.location.hostname !== "localhost"
    ? `http://${window.location.hostname}:8000`
    : "http://localhost:8000";

const DEFAULT_LAT = 12.9716;
const DEFAULT_LON = 77.5946;

// ── Risk colour helpers ───────────────────────────────────────────────────────

function riskColor(level: string) {
  const map: Record<string, string> = {
    "Very Low": "#22c55e",
    Low: "#86efac",
    Moderate: "#f59e0b",
    High: "#ef4444",
    Extreme: "#7c3aed",
    Unknown: "#94a3b8",
  };
  return map[level] ?? "#94a3b8";
}

function riskBg(level: string) {
  const map: Record<string, string> = {
    "Very Low": "#f0fdf4",
    Low: "#f0fdf4",
    Moderate: "#fffbeb",
    High: "#fef2f2",
    Extreme: "#f5f3ff",
    Unknown: "#f8fafc",
  };
  return map[level] ?? "#f8fafc";
}

function eqRiskColor(level: string) {
  const map: Record<string, string> = {
    "Very Low": "#ea580c",
    Low: "#ea580c",
    Moderate: "#d97706",
    High: "#dc2626",
    Unknown: "#94a3b8",
  };
  return map[level] ?? "#94a3b8";
}

// ── Sub-components ────────────────────────────────────────────────────────────

function RiskBadge({ level, color }: { level: string; color: string }) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 10px",
        borderRadius: 999,
        background: riskBg(level),
        color,
        fontWeight: 700,
        fontSize: 12,
        border: `1px solid ${color}40`,
      }}
    >
      {level}
    </span>
  );
}

function ProbBar({ prob, color }: { prob: number; color: string }) {
  const pct = Math.round(prob * 100);
  return (
    <div style={{ marginTop: 4 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#64748b", marginBottom: 3 }}>
        <span>Probability</span>
        <span style={{ fontWeight: 700, color }}>{pct}%</span>
      </div>
      <div style={{ height: 6, borderRadius: 3, background: "#e2e8f0", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: 3, transition: "width 0.4s ease" }} />
      </div>
    </div>
  );
}

function FeatureRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderBottom: "1px solid #f1f5f9", fontSize: 12 }}>
      <span style={{ color: "#64748b" }}>{label}</span>
      <span style={{ fontWeight: 600, color: "#0f172a" }}>{value}</span>
    </div>
  );
}

function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div
      style={{
        background: "#fff",
        borderRadius: 16,
        border: "1px solid #e2e8f0",
        padding: "18px 20px",
        marginBottom: 16,
        boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

function SectionTitle({ icon, title }: { icon: string; title: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 12 }}>
      <span style={{ fontSize: 18 }}>{icon}</span>
      <span style={{ fontWeight: 700, fontSize: 13, letterSpacing: 1, color: "#475569", textTransform: "uppercase" }}>
        {title}
      </span>
    </div>
  );
}

// ── Flood Panel ───────────────────────────────────────────────────────────────

function FloodPanel({ data }: { data: FloodData }) {
  const color = riskColor(data.risk_level);
  return (
    <Card>
      <SectionTitle icon="🌊" title="Flood Forecast · 12h" />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div>
          <RiskBadge level={data.risk_level} color={color} />
          <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>
            {data.flood_predicted ? "⚠ Flood likely" : "No flood expected"}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 28, fontWeight: 800, color }}>{Math.round(data.probability * 100)}%</div>
          <div style={{ fontSize: 10, color: "#94a3b8" }}>chance</div>
        </div>
      </div>
      <ProbBar prob={data.probability} color={color} />
      <div style={{ marginTop: 12 }}>
        <FeatureRow label="Peak rainfall" value={`${data.features.rainfall_1h?.toFixed(1) ?? "—"} mm/h`} />
        <FeatureRow label="24h accumulation" value={`${data.features.rainfall_24h?.toFixed(0) ?? "—"} mm`} />
        <FeatureRow label="Soil moisture" value={`${Math.round((data.features.soil_moisture ?? 0) * 100)}%`} />
        <FeatureRow label="Elevation" value={`${data.features.elevation?.toFixed(0) ?? "—"} m`} />
        <FeatureRow label="Drainage score" value={`${data.features.drainage?.toFixed(1) ?? "—"} / 10`} />
      </div>
      {data.advice.slice(0, 2).map((tip, i) => (
        <div key={i} style={{ display: "flex", gap: 6, marginTop: 8, fontSize: 12, color: "#475569" }}>
          <span>💡</span><span>{tip}</span>
        </div>
      ))}
    </Card>
  );
}

// ── Cyclone Panel ─────────────────────────────────────────────────────────────

function CyclonePanel({ data }: { data: CycloneData }) {
  const color = riskColor(data.cyclone_risk);
  return (
    <Card>
      <SectionTitle icon="🌀" title="Cyclone Forecast · Live" />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div>
          <RiskBadge level={data.cyclone_risk} color={color} />
          <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>{data.category}</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 28, fontWeight: 800, color }}>{Math.round(data.probability * 100)}%</div>
          <div style={{ fontSize: 10, color: "#94a3b8" }}>risk</div>
        </div>
      </div>
      <ProbBar prob={data.probability} color={color} />
      <div style={{ marginTop: 12 }}>
        <FeatureRow label="Wind gusts" value={`${data.features.wind_gusts_kmh?.toFixed(0) ?? "—"} km/h`} />
        <FeatureRow label="Pressure" value={`${data.features.surface_pressure_hpa?.toFixed(0) ?? "—"} hPa`} />
        <FeatureRow label="Pressure drop 6h" value={`${data.features.pressure_drop_6h ?? 0} hPa`} />
        <FeatureRow label="Coast distance" value={`${data.features.coastal_proximity_km?.toFixed(0) ?? "—"} km`} />
      </div>
      {data.advice.slice(0, 2).map((tip, i) => (
        <div key={i} style={{ display: "flex", gap: 6, marginTop: 8, fontSize: 12, color: "#475569" }}>
          <span>💡</span><span>{tip}</span>
        </div>
      ))}
      <div style={{ marginTop: 10, fontSize: 10, color: "#94a3b8" }}>
        {data.ml_model_active ? "🤖 ML Model Active" : "⚡ Physics Model"}
      </div>
    </Card>
  );
}

// ── Earthquake Panel ──────────────────────────────────────────────────────────

function EarthquakePanel({ data }: { data: EarthquakeData }) {
  const color = eqRiskColor(data.earthquake_risk);
  const f = data.features;
  return (
    <Card style={{ borderLeft: `4px solid ${color}` }}>
      <SectionTitle icon="🔴" title="Earthquake Forecast · 7 days" />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div>
          <RiskBadge level={data.earthquake_risk} color={color} />
          <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>{data.seismic_zone}</div>
          {f.b_value < 0.80 && (
            <div style={{ fontSize: 11, color: "#dc2626", marginTop: 4, fontWeight: 600 }}>
              ⚠ Low b-value: High stress
            </div>
          )}
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 28, fontWeight: 800, color }}>{data.probability_pct}</div>
          <div style={{ fontSize: 10, color: "#94a3b8" }}>M≥4.5 risk</div>
        </div>
      </div>
      <ProbBar prob={data.probability} color={color} />

      {/* Seismological feature grid */}
      <div style={{ marginTop: 12 }}>
        <FeatureRow label="Quakes nearby (7d / 30d)" value={`${f.recent_quakes_7d} / ${f.recent_quakes_30d}`} />
        <FeatureRow label="Max magnitude 30d" value={`M${f.max_mag_30d.toFixed(1)}`} />
        <FeatureRow label="b-value (stress index)" value={`${f.b_value.toFixed(3)} ${f.b_value < 0.80 ? "⚠" : "✓"}`} />
        <FeatureRow label="Inter-event CV (clustering)" value={`${f.cv_interevent.toFixed(2)} ${f.cv_interevent > 1.5 ? "🔴" : "✓"}`} />
        <FeatureRow label="Seismic acceleration" value={`${f.quake_acceleration.toFixed(1)}× ${f.quake_acceleration > 2 ? "↑" : "—"}`} />
        <FeatureRow label="Avg depth" value={`${f.depth_avg_30d.toFixed(0)} km`} />
        <FeatureRow label="Shallow fraction" value={`${Math.round(f.depth_shallow_frac * 100)}%`} />
        <FeatureRow label="Distance to fault" value={`${f.dist_to_fault_km.toFixed(0)} km`} />
      </div>

      {data.advice.slice(0, 2).map((tip, i) => (
        <div key={i} style={{ display: "flex", gap: 6, marginTop: 8, fontSize: 12, color: "#475569" }}>
          <span>💡</span><span>{tip}</span>
        </div>
      ))}
      <div style={{ marginTop: 10, fontSize: 10, color: "#94a3b8" }}>
        {data.ml_model_active ? "🤖 ML Model Active (90.7% AUC)" : "⚡ Physics Model"}
        {" · USGS Catalog · BIS 1893"}
      </div>
    </Card>
  );
}

// ── Main FloodMap component ───────────────────────────────────────────────────

export default function FloodMap() {
  const [lat] = useState(DEFAULT_LAT);
  const [lon] = useState(DEFAULT_LON);
  const [flood, setFlood] = useState<FloodData | null>(null);
  const [cyclone, setCyclone] = useState<CycloneData | null>(null);
  const [earthquake, setEarthquake] = useState<EarthquakeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchAll = async () => {
      setLoading(true);
      setError(null);
      try {
        const [floodRes, cycloneRes, eqRes] = await Promise.allSettled([
          fetch(`${BACKEND}/predict?lat=${lat}&lon=${lon}`).then((r) => r.json()),
          fetch(`${BACKEND}/api/cyclone?lat=${lat}&lon=${lon}`).then((r) => r.json()),
          fetch(`${BACKEND}/api/earthquake?lat=${lat}&lon=${lon}`).then((r) => r.json()),
        ]);
        if (floodRes.status === "fulfilled") setFlood(floodRes.value);
        if (cycloneRes.status === "fulfilled") setCyclone(cycloneRes.value);
        if (eqRes.status === "fulfilled") setEarthquake(eqRes.value);
      } catch (e: any) {
        setError("Failed to load risk data — is the backend running?");
      } finally {
        setLoading(false);
      }
    };
    fetchAll();
  }, [lat, lon]);

  const floodColor  = flood    ? riskColor(flood.risk_level)      : "#94a3b8";
  const cycloneColor = cyclone ? riskColor(cyclone.cyclone_risk)   : "#94a3b8";
  const eqColor      = earthquake ? eqRiskColor(earthquake.earthquake_risk) : "#94a3b8";

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "Inter, system-ui, sans-serif" }}>

      {/* ── Left sidebar ── */}
      <div
        style={{
          width: 360,
          minWidth: 320,
          height: "100vh",
          overflowY: "auto",
          background: "#f8fafc",
          borderRight: "1px solid #e2e8f0",
          padding: "20px 16px 40px",
        }}
      >
        {/* Header */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontWeight: 800, fontSize: 20, color: "#0f172a", letterSpacing: -0.5 }}>
            JeevanSetu Dashboard
          </div>
          <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 2 }}>
            Bengaluru · {new Date().toLocaleDateString("en-IN", { weekday: "long", month: "short", day: "numeric" })}
          </div>
        </div>

        {/* Risk summary row */}
        <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
          {[
            { label: "Flood",    color: floodColor,   level: flood?.risk_level      ?? "—" },
            { label: "Cyclone",  color: cycloneColor, level: cyclone?.cyclone_risk   ?? "—" },
            { label: "Quake",    color: eqColor,      level: earthquake?.earthquake_risk ?? "—" },
          ].map((r) => (
            <div key={r.label} style={{
              flex: 1, borderRadius: 12, background: "#fff",
              border: `1px solid ${r.color}40`,
              padding: "10px 8px", textAlign: "center",
              boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
            }}>
              <div style={{ fontSize: 10, color: "#94a3b8", marginBottom: 3, textTransform: "uppercase", letterSpacing: 0.5 }}>{r.label}</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: r.color }}>{r.level}</div>
            </div>
          ))}
        </div>

        {loading && (
          <div style={{ textAlign: "center", color: "#94a3b8", padding: 32 }}>
            Loading risk data…
          </div>
        )}
        {error && (
          <div style={{ background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 12, padding: 14, color: "#991b1b", fontSize: 13, marginBottom: 16 }}>
            {error}
          </div>
        )}

        {flood      && <FloodPanel      data={flood} />}
        {cyclone    && <CyclonePanel    data={cyclone} />}
        {earthquake && <EarthquakePanel data={earthquake} />}
      </div>

      {/* ── Map ── */}
      <div style={{ flex: 1, position: "relative" }}>
        <MapContainer
          center={[lat, lon]}
          zoom={11}
          style={{ height: "100%", width: "100%" }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          {/* Flood risk radius */}
          {flood && (
            <Circle
              center={[lat, lon]}
              radius={15000}
              pathOptions={{ color: floodColor, fillColor: floodColor, fillOpacity: 0.12, weight: 2 }}
            />
          )}

          {/* Earthquake risk radius (100km) */}
          {earthquake && (
            <Circle
              center={[lat, lon]}
              radius={100000}
              pathOptions={{ color: eqColor, fillColor: eqColor, fillOpacity: 0.06, weight: 1.5, dashArray: "6 4" }}
            />
          )}

          {/* Main location marker */}
          <Marker position={[lat, lon]}>
            <Popup>
              <div style={{ fontFamily: "Inter, sans-serif", minWidth: 200 }}>
                <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 8 }}>Bengaluru</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "#64748b", fontSize: 12 }}>Flood risk</span>
                    <span style={{ fontWeight: 600, fontSize: 12, color: floodColor }}>{flood?.risk_level ?? "—"}</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "#64748b", fontSize: 12 }}>Cyclone risk</span>
                    <span style={{ fontWeight: 600, fontSize: 12, color: cycloneColor }}>{cyclone?.cyclone_risk ?? "—"}</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "#64748b", fontSize: 12 }}>Earthquake risk</span>
                    <span style={{ fontWeight: 600, fontSize: 12, color: eqColor }}>{earthquake?.earthquake_risk ?? "—"}</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "#64748b", fontSize: 12 }}>Seismic zone</span>
                    <span style={{ fontWeight: 600, fontSize: 12, color: "#475569" }}>{earthquake?.seismic_zone ?? "—"}</span>
                  </div>
                </div>
              </div>
            </Popup>
          </Marker>
        </MapContainer>

        {/* Map legend */}
        <div style={{
          position: "absolute", bottom: 24, right: 16, zIndex: 1000,
          background: "rgba(255,255,255,0.95)", borderRadius: 12,
          border: "1px solid #e2e8f0", padding: "10px 14px",
          boxShadow: "0 2px 8px rgba(0,0,0,0.1)", fontSize: 11,
          backdropFilter: "blur(4px)",
        }}>
          <div style={{ fontWeight: 700, color: "#0f172a", marginBottom: 6, fontSize: 11, textTransform: "uppercase", letterSpacing: 0.5 }}>Legend</div>
          <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 4 }}>
            <div style={{ width: 14, height: 14, borderRadius: "50%", background: `${floodColor}30`, border: `2px solid ${floodColor}` }} />
            <span style={{ color: "#475569" }}>Flood zone (15km)</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <div style={{ width: 14, height: 14, borderRadius: "50%", background: `${eqColor}18`, border: `2px dashed ${eqColor}` }} />
            <span style={{ color: "#475569" }}>Seismic zone (100km)</span>
          </div>
        </div>
      </div>
    </div>
  );
}
