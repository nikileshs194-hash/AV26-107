import React, { useState, useCallback, useRef, useEffect } from 'react';
import { StyleSheet, View, Text, ScrollView, TouchableOpacity, RefreshControl, ActivityIndicator, Alert, Linking, Platform, Modal, Animated, TextInput, Easing } from 'react-native';
import { Colors } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';
import Header from '@/components/Header';
import { LinearGradient } from 'expo-linear-gradient';
import { Feather, Ionicons } from '@expo/vector-icons';
import Svg, { Circle, Path } from 'react-native-svg';
import { useFocusEffect } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';

import useLocation from '@/hooks/useLocation';
import { useAuth } from '@/context/AuthContext';
import {
  fetchWeather, fetchFloodPrediction, fetchCyclonePrediction,
  sendSOS, notifyNearby, findNearest,
  FloodPrediction, WeatherResponse, CyclonePrediction,
} from '@/services/api';

// ─── Flood Prediction Card ────────────────────────────────────────────────────

const FLOOD_COLORS: Record<string, { bg: string; border: string; text: string; badge: string }> = {
  'Very Low': { bg: '#f0fdf4', border: '#86efac', text: '#166534', badge: '#22c55e' },
  'Low':      { bg: '#f0fdf4', border: '#86efac', text: '#166534', badge: '#22c55e' },
  'Moderate': { bg: '#fffbeb', border: '#fcd34d', text: '#92400e', badge: '#f59e0b' },
  'High':     { bg: '#fff1f2', border: '#fca5a5', text: '#991b1b', badge: '#ef4444' },
};

function FloodPredictionCard({ data }: { data: FloodPrediction }) {
  const c = FLOOD_COLORS[data.risk_level] ?? FLOOD_COLORS['Low'];
  const pct = Math.round(data.probability * 100);

  return (
    <View style={[fpStyles.card, { backgroundColor: c.bg, borderColor: c.border }]}>
      {/* Header */}
      <View style={fpStyles.header}>
        <View style={fpStyles.headerLeft}>
          <Ionicons name="analytics-outline" size={20} color={c.text} />
          <Text style={[fpStyles.title, { color: c.text }]}>AI FLOOD FORECAST</Text>
        </View>
        <View style={[fpStyles.windowBadge, { backgroundColor: c.border }]}>
          <Ionicons name="time-outline" size={11} color={c.text} />
          <Text style={[fpStyles.windowText, { color: c.text }]}> Next 12 hours</Text>
        </View>
      </View>

      {/* Risk level + probability */}
      <View style={fpStyles.riskRow}>
        <View>
          <Text style={[fpStyles.riskLevel, { color: c.text }]}>{data.risk_level} Risk</Text>
          <Text style={[fpStyles.riskSub, { color: c.text }]}>
            {data.flood_predicted ? 'Flood likely' : 'No flood expected'}
          </Text>
        </View>
        <View style={[fpStyles.probCircle, { borderColor: c.badge }]}>
          <Text style={[fpStyles.probNum, { color: c.badge }]}>{pct}%</Text>
          <Text style={[fpStyles.probLabel, { color: c.text }]}>chance</Text>
        </View>
      </View>

      {/* Key signals */}
      <View style={fpStyles.signals}>
        <View style={fpStyles.signal}>
          <Ionicons name="rainy-outline" size={14} color={c.text} />
          <Text style={[fpStyles.signalText, { color: c.text }]}>
            {data.features.rainfall_1h.toFixed(1)} mm/h peak
          </Text>
        </View>
        <View style={fpStyles.signal}>
          <Ionicons name="water-outline" size={14} color={c.text} />
          <Text style={[fpStyles.signalText, { color: c.text }]}>
            {data.features.rainfall_24h.toFixed(0)} mm / 24h
          </Text>
        </View>
        <View style={fpStyles.signal}>
          <Ionicons name="earth-outline" size={14} color={c.text} />
          <Text style={[fpStyles.signalText, { color: c.text }]}>
            Soil {Math.round(data.features.soil_moisture * 100)}% saturated
          </Text>
        </View>
      </View>

      {/* Top advice */}
      {data.advice.slice(0, 2).map((tip, i) => (
        <View key={i} style={fpStyles.tip}>
          <Ionicons name="alert-circle-outline" size={13} color={c.badge} style={{ marginTop: 1 }} />
          <Text style={[fpStyles.tipText, { color: c.text }]}>{tip}</Text>
        </View>
      ))}
    </View>
  );
}

const fpStyles = StyleSheet.create({
  card: { borderRadius: 20, borderWidth: 1.5, padding: 18, marginBottom: 24 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  title: { fontFamily: 'PlusJakartaSans_700Bold', fontSize: 12, letterSpacing: 1 },
  windowBadge: { flexDirection: 'row', alignItems: 'center', borderRadius: 20, paddingHorizontal: 8, paddingVertical: 4 },
  windowText: { fontFamily: 'PlusJakartaSans_600SemiBold', fontSize: 11 },
  riskRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 },
  riskLevel: { fontFamily: 'PlusJakartaSans_700Bold', fontSize: 24, marginBottom: 2 },
  riskSub: { fontFamily: 'PlusJakartaSans_400Regular', fontSize: 13 },
  probCircle: { width: 72, height: 72, borderRadius: 36, borderWidth: 3, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(255,255,255,0.6)' },
  probNum: { fontFamily: 'PlusJakartaSans_700Bold', fontSize: 22 },
  probLabel: { fontFamily: 'PlusJakartaSans_400Regular', fontSize: 10 },
  signals: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 },
  signal: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: 'rgba(255,255,255,0.5)', borderRadius: 20, paddingHorizontal: 10, paddingVertical: 5 },
  signalText: { fontFamily: 'PlusJakartaSans_500Medium', fontSize: 12 },
  tip: { flexDirection: 'row', gap: 6, marginBottom: 4 },
  tipText: { fontFamily: 'PlusJakartaSans_400Regular', fontSize: 12, flex: 1, lineHeight: 17 },
});

// ─── Cyclone Prediction Card ──────────────────────────────────────────────────

const CYCLONE_COLORS: Record<string, { bg: string; border: string; text: string; badge: string }> = {
  'Very Low': { bg: '#f5f3ff', border: '#c4b5fd', text: '#4c1d95', badge: '#7c3aed' },
  'Low':      { bg: '#f5f3ff', border: '#c4b5fd', text: '#4c1d95', badge: '#7c3aed' },
  'Moderate': { bg: '#ede9fe', border: '#a78bfa', text: '#3730a3', badge: '#6d28d9' },
  'High':     { bg: '#e0e7ff', border: '#818cf8', text: '#1e1b4b', badge: '#4f46e5' },
  'Extreme':  { bg: '#fdf4ff', border: '#d946ef', text: '#4a044e', badge: '#a21caf' },
};

function CyclonePredictionCard({ data }: { data: CyclonePrediction }) {
  const c   = CYCLONE_COLORS[data.cyclone_risk] ?? CYCLONE_COLORS['Low'];
  const pct = Math.round(data.probability * 100);
  const f   = data.features;

  return (
    <View style={[fpStyles.card, { backgroundColor: c.bg, borderColor: c.border }]}>
      {/* Header */}
      <View style={fpStyles.header}>
        <View style={fpStyles.headerLeft}>
          <Ionicons name="thunderstorm-outline" size={20} color={c.text} />
          <Text style={[fpStyles.title, { color: c.text }]}>AI CYCLONE FORECAST</Text>
        </View>
        <View style={[fpStyles.windowBadge, { backgroundColor: c.border }]}>
          <Ionicons name="navigate-outline" size={11} color={c.text} />
          <Text style={[fpStyles.windowText, { color: c.text }]}> Live conditions</Text>
        </View>
      </View>

      {/* Risk level + probability circle */}
      <View style={fpStyles.riskRow}>
        <View style={{ flex: 1 }}>
          <Text style={[fpStyles.riskLevel, { color: c.text }]}>{data.cyclone_risk} Risk</Text>
          <Text style={[fpStyles.riskSub, { color: c.text }]}>{data.category}</Text>
          {/* GDACS active badge */}
          {f.gdacs_active && (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 6,
              backgroundColor: '#fef2f2', borderRadius: 12, paddingHorizontal: 8, paddingVertical: 3,
              alignSelf: 'flex-start', borderWidth: 1, borderColor: '#fca5a5' }}>
              <Ionicons name="warning-outline" size={11} color="#dc2626" />
              <Text style={{ fontSize: 10, color: '#dc2626', fontFamily: 'PlusJakartaSans_600SemiBold' }}>
                Active: {f.gdacs_name || 'Cyclone Nearby'}
              </Text>
            </View>
          )}
        </View>
        <View style={[fpStyles.probCircle, { borderColor: c.badge }]}>
          <Text style={[fpStyles.probNum, { color: c.badge }]}>{pct}%</Text>
          <Text style={[fpStyles.probLabel, { color: c.text }]}>risk</Text>
        </View>
      </View>

      {/* Key signals */}
      <View style={fpStyles.signals}>
        <View style={fpStyles.signal}>
          <Ionicons name="thunderstorm-outline" size={14} color={c.text} />
          <Text style={[fpStyles.signalText, { color: c.text }]}>
            Gusts {f.wind_gusts_kmh.toFixed(0)} km/h
          </Text>
        </View>
        <View style={fpStyles.signal}>
          <Ionicons name="speedometer-outline" size={14} color={c.text} />
          <Text style={[fpStyles.signalText, { color: c.text }]}>
            {f.surface_pressure_hpa.toFixed(0)} hPa
          </Text>
        </View>
        <View style={fpStyles.signal}>
          <Ionicons name="trending-down-outline" size={14} color={c.text} />
          <Text style={[fpStyles.signalText, { color: c.text }]}>
            {f.pressure_drop_6h > 0 ? `↓${f.pressure_drop_6h} hPa/6h` : 'Stable pressure'}
          </Text>
        </View>
        <View style={fpStyles.signal}>
          <Ionicons name="location-outline" size={14} color={c.text} />
          <Text style={[fpStyles.signalText, { color: c.text }]}>
            {f.coastal_proximity_km < 1000
              ? `${f.coastal_proximity_km.toFixed(0)} km coast`
              : 'Inland'}
          </Text>
        </View>
      </View>

      {/* Top advice tips */}
      {data.advice.slice(0, 2).map((tip, i) => (
        <View key={i} style={fpStyles.tip}>
          <Ionicons name="alert-circle-outline" size={13} color={c.badge} style={{ marginTop: 1 }} />
          <Text style={[fpStyles.tipText, { color: c.text }]}>{tip}</Text>
        </View>
      ))}

      {/* Data sources */}
      <Text style={{ fontFamily: 'PlusJakartaSans_400Regular', fontSize: 10,
        color: c.text, opacity: 0.55, marginTop: 6 }}>
        Sources: {data.data_sources.join(' · ')} · IMD Scale
      </Text>
    </View>
  );
}

// ─── Risk Gauge ──────────────────────────────────────────────────────────────

function RiskGauge({ level = 'Low', color = '#4CAF50' }: { level: string; color: string }) {
  const cx = 100, cy = 100, r = 80, strokeW = 14;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const arcPath = (s: number, e: number) => {
    const x1 = cx + r * Math.cos(toRad(s)), y1 = cy + r * Math.sin(toRad(s));
    const x2 = cx + r * Math.cos(toRad(e)), y2 = cy + r * Math.sin(toRad(e));
    return `M ${x1} ${y1} A ${r} ${r} 0 ${e - s > 180 ? 1 : 0} 1 ${x2} ${y2}`;
  };
  const zones = [
    { start: 135, end: 202.5, color: '#4CAF50' }, { start: 202.5, end: 270, color: '#FFC107' },
    { start: 270, end: 337.5, color: '#FF9800' }, { start: 337.5, end: 405, color: '#F44336' },
  ];
  const needleDeg: Record<string, number> = { Low: 168, Moderate: 300, High: 375 };
  const nd = needleDeg[level] ?? 300;
  const nx = cx + (r - 12) * Math.cos(toRad(nd));
  const ny = cy + (r - 12) * Math.sin(toRad(nd));

  return (
    <View style={{ alignItems: 'center', marginVertical: 4 }}>
      <Svg width={200} height={120} viewBox="0 0 200 120">
        <Path d={arcPath(135, 405)} fill="none" stroke="#e1e3e4" strokeWidth={strokeW} strokeLinecap="round" />
        {zones.map((z, i) => (
          <Path key={i} d={arcPath(z.start, z.end)} fill="none" stroke={z.color}
            strokeWidth={strokeW} strokeLinecap={i === 0 || i === zones.length - 1 ? 'round' : 'butt'} />
        ))}
        <Path d={`M ${cx} ${cy} L ${nx} ${ny}`} stroke="#191c1d" strokeWidth={3} strokeLinecap="round" />
        <Circle cx={cx} cy={cy} r={6} fill="#191c1d" />
        <Circle cx={cx} cy={cy} r={3} fill="#fff" />
      </Svg>
      <Text style={{ fontFamily: 'PlusJakartaSans_700Bold', fontSize: 20, color, marginTop: -10 }}>{level}</Text>
      <Text style={{ fontFamily: 'PlusJakartaSans_400Regular', fontSize: 12, color: '#707785', marginTop: 2 }}>Be Prepared</Text>
    </View>
  );
}

const RESCUE_PHONE_KEY = 'jeevansetu_rescue_phone';

export default function DashboardScreen() {
  const colorScheme = useColorScheme() ?? 'light';
  const theme = Colors[colorScheme];
  const { location } = useLocation();
  const { user } = useAuth();
  const [weather, setWeather] = useState<WeatherResponse | null>(null);
  const [flood, setFlood] = useState<FloodPrediction | null>(null);
  const [cyclone, setCyclone] = useState<CyclonePrediction | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sosLoading, setSosLoading] = useState(false);
  const [nearbyLoading, setNearbyLoading] = useState(false);
  const [showSOSPicker, setShowSOSPicker] = useState(false);

  // Configurable rescue phone
  const [rescuePhone, setRescuePhone] = useState('9353124446');
  const [showRescueEdit, setShowRescueEdit] = useState(false);
  const [rescueInput, setRescueInput] = useState('');

  // SOS pulse animation
  const pulseAnim  = useRef(new Animated.Value(1)).current;
  const pulseOpacity = useRef(new Animated.Value(0.6)).current;
  const fadeIn     = useRef(new Animated.Value(0)).current;

  // Load saved rescue phone
  useEffect(() => {
    AsyncStorage.getItem(RESCUE_PHONE_KEY).then(v => { if (v) setRescuePhone(v); });
    Animated.timing(fadeIn, { toValue: 1, duration: 600, useNativeDriver: true }).start();
  }, []);

  // Pulsing ring around SOS button
  useEffect(() => {
    const pulse = Animated.loop(
      Animated.sequence([
        Animated.parallel([
          Animated.timing(pulseAnim, { toValue: 1.35, duration: 900, easing: Easing.out(Easing.ease), useNativeDriver: true }),
          Animated.timing(pulseOpacity, { toValue: 0, duration: 900, useNativeDriver: true }),
        ]),
        Animated.parallel([
          Animated.timing(pulseAnim, { toValue: 1, duration: 0, useNativeDriver: true }),
          Animated.timing(pulseOpacity, { toValue: 0.6, duration: 0, useNativeDriver: true }),
        ]),
      ])
    );
    pulse.start();
    return () => pulse.stop();
  }, []);

  const load = useCallback(async (isRefresh = false) => {
    if (!location) return;
    isRefresh ? setRefreshing(true) : setLoading(true);
    setError(null);
    try {
      const [weatherData, floodData, cycloneData] = await Promise.all([
        fetchWeather(location.lat, location.lon),
        fetchFloodPrediction(location.lat, location.lon).catch(() => null),
        fetchCyclonePrediction(location.lat, location.lon).catch(() => null),
      ]);
      setWeather(weatherData);
      setFlood(floodData);
      setCyclone(cycloneData);
    } catch (e: any) {
      setError(e.message || 'Failed to load weather');
    } finally {
      setLoading(false); setRefreshing(false);
    }
  }, [location]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  // ── SOS: open emergency type picker modal ─────────────────────────────────
  const handleSOS = () => {
    if (!location) {
      Alert.alert('No Location', 'Waiting for your location. Please wait a moment.');
      return;
    }
    setShowSOSPicker(true);
  };

  const fireSOS = async (category: string) => {
    if (!location) return;
    setSosLoading(true);
    try {
      const result = await sendSOS(
        user?.phone    ?? '',
        user?.full_name ?? 'Unknown',
        location.lat,
        location.lon,
        undefined,
        category,
      );
      Alert.alert(
        '✅ SOS Sent',
        `📍 ${result.address}\n\nRescue team has been alerted and will respond shortly.\n\nUse "Call Nearby People" to alert people around you.`,
      );
    } catch {
      Alert.alert('Error', 'Failed to send SOS.\nCall 112 directly.');
    } finally {
      setSosLoading(false);
    }
  };

  // ── Call Rescue Team: dial configurable rescue number ────────────────────────
  const handleCallRescue = () => {
    Alert.alert(
      'Call Rescue Team',
      `This will call the rescue number: ${rescuePhone}`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: '📞 Call Now', onPress: () => dialNumber(rescuePhone) },
      ],
    );
  };

  const saveRescuePhone = async () => {
    const clean = rescueInput.replace(/[^0-9+]/g, '');
    if (!clean) return;
    setRescuePhone(clean);
    await AsyncStorage.setItem(RESCUE_PHONE_KEY, clean);
    setShowRescueEdit(false);
  };

  // ── Call Nearby People: notify via push + dial nearest person ────────────────
  const handleCallNearby = async () => {
    if (nearbyLoading) return;
    if (!location) {
      Alert.alert('No Location', 'Waiting for your location. Please try again.');
      return;
    }
    setNearbyLoading(true);
    try {
      // notifyNearby sends the full SOSAlertModal push notification to all
      // nearby users AND returns the nearest person's phone to call directly
      const result = await notifyNearby(
        user?.phone    ?? '',
        user?.full_name ?? 'Unknown',
        location.lat,
        location.lon,
      );

      if (!result.nearest_phone) {
        Alert.alert(
          'No one nearby',
          'No registered users found near your location.\n\nCall 112 for emergency services.',
          [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Call 112', onPress: () => dialNumber('112') },
          ],
        );
        return;
      }

      const name     = result.nearest_name ?? 'Nearby Person';
      const phone    = result.nearest_phone;
      const dist     = result.nearest_dist_str ?? `${result.nearest_dist_m} m`;
      const notified = result.notified_count;

      Alert.alert(
        '📢 Alert Sent!',
        `${notified > 0 ? `✅ Emergency notification sent to ${notified} nearby person${notified !== 1 ? 's' : ''}.\n\n` : ''}Nearest: ${name} (${dist} away)\n\nCall them now?`,
        [
          { text: 'Skip', style: 'cancel' },
          {
            text: `📞 Call ${name}`,
            onPress: () => dialNumber(phone.replace(/[\s\-\(\)]/g, '')),
          },
        ],
      );
    } catch {
      Alert.alert('Error', 'Could not reach nearby people.\nPlease call 112 directly.');
    } finally {
      setNearbyLoading(false);
    }
  };

  // Works on Android, iOS and web
  const dialNumber = (phone: string) => {
    Linking.openURL(`tel:${phone}`).catch(() => {});
  };

  if (loading) {
    return (
      <View style={[styles.container, styles.center, { backgroundColor: theme.background }]}>
        <View style={{ alignItems: 'center', gap: 16 }}>
          <ActivityIndicator size="large" color={theme.primary} />
          <Text style={[styles.loadingText, { color: theme.icon }]}>Loading weather…</Text>
          <View style={{ gap: 10, width: 280, marginTop: 8 }}>
            {[1,2,3].map(i => (
              <View key={i} style={{ height: 16, borderRadius: 8, backgroundColor: theme.border, opacity: 0.5 + i * 0.1 }} />
            ))}
          </View>
        </View>
      </View>
    );
  }

  const c = weather?.current;
  const hourly = weather?.hourly ?? [];
  const daily = weather?.daily ?? [];
  const risk = weather?.risk;

  return (
    <>
    <ScrollView
      style={[styles.container, { backgroundColor: theme.background }]}
      contentContainerStyle={styles.contentContainer}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={theme.primary} />}
    >
      <Header city={location?.city} />

      {error && (
        <View style={[styles.errorBanner, { backgroundColor: theme.card }]}>
          <Text style={{ color: theme.tertiaryContainer, fontFamily: 'PlusJakartaSans_500Medium' }}>{error}</Text>
          <TouchableOpacity onPress={() => load()}>
            <Text style={{ color: theme.primary, fontFamily: 'PlusJakartaSans_600SemiBold', marginTop: 6 }}>Retry</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Main Weather Card */}
      <LinearGradient colors={['#1E3A8A', '#2563EB', '#3B82F6']} style={styles.mainCard} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}>
        {/* Top row: date + condition */}
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <Text style={styles.dateText}>
            {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' }).toUpperCase()}
          </Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: 20, paddingHorizontal: 10, paddingVertical: 5 }}>
            <Ionicons name={(c?.icon as any) || 'partly-sunny-outline'} size={14} color="rgba(255,255,255,0.9)" />
            <Text style={{ fontFamily: 'PlusJakartaSans_500Medium', fontSize: 11, color: 'rgba(255,255,255,0.9)' }}>
              {c?.condition || '—'}
            </Text>
          </View>
        </View>

        {/* Temperature + description */}
        <View style={styles.tempRow}>
          <Text style={styles.largeTemp}>{c ? `${c.temp}°` : '--°'}</Text>
          <View style={{ marginLeft: 16, justifyContent: 'center' }}>
            <Text style={styles.weatherCondition}>{c?.description || 'Loading...'}</Text>
            <Text style={styles.feelsLikeText}>
              {c ? `Feels ${c.feels_like}°  ↑${c.temp_max}° ↓${c.temp_min}°` : ''}
            </Text>
          </View>
        </View>

        {/* 6-metric grid with pill design */}
        <View style={styles.metricsContainer}>
          {[
            { icon: 'water-outline',    label: 'Humidity',    value: c ? `${c.humidity}%` : '—' },
            { icon: 'thunderstorm-outline', label: 'Wind',    value: c ? `${c.wind_speed} km/h` : '—' },
            { icon: 'sunny-outline',    label: 'UV Index',    value: c?.uv_label || '—' },
            { icon: 'eye-outline',      label: 'Visibility',  value: c ? `${c.visibility} km` : '—' },
            { icon: 'contract-outline', label: 'Pressure',    value: c ? `${c.pressure} hPa` : '—' },
            { icon: 'leaf-outline',     label: 'Air Quality', value: c?.air_quality?.label || '—' },
          ].map((m, i) => (
            <View key={i} style={styles.metricPill}>
              <Ionicons name={m.icon as any} size={13} color="rgba(255,255,255,0.75)" />
              <View>
                <Text style={styles.metricLabel}>{m.label}</Text>
                <Text style={styles.metricValue}>{m.value}</Text>
              </View>
            </View>
          ))}
        </View>
      </LinearGradient>

      {/* Hourly Forecast */}
      <View style={styles.sectionHeader}>
        <Text style={[styles.sectionTitle, { color: theme.text }]}>HOURLY FORECAST</Text>
        <Text style={[styles.linkText, { color: theme.primary }]}>Next 24h</Text>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.hourlyScroll}>
        {hourly.length === 0 && !loading ? (
          <View style={[styles.hourlyItem, { backgroundColor: theme.card }]}>
            <Text style={[styles.hourlyTime, { color: theme.icon }]}>--</Text>
          </View>
        ) : hourly.map((h, i) => (
          <View key={i} style={[styles.hourlyItem, { backgroundColor: i === 0 ? '#EBF4FF' : theme.card }]}>
            <Text style={[styles.hourlyTime, { color: i === 0 ? theme.primary : theme.icon }]}>{i === 0 ? 'Now' : h.time}</Text>
            <Ionicons name={h.icon as any} size={24} color={i === 0 ? theme.primary : theme.icon} style={{ marginVertical: 8 }} />
            {h.rain_prob > 0 && (
              <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 2 }}>
                <Ionicons name="water-outline" size={10} color={theme.primary} />
                <Text style={{ fontSize: 10, color: theme.primary, fontFamily: 'PlusJakartaSans_600SemiBold' }}> {h.rain_prob}%</Text>
              </View>
            )}
            <Text style={[styles.hourlyTemp, { color: theme.text }]}>{h.temp}°</Text>
          </View>
        ))}
      </ScrollView>

      {/* 7-Day Forecast */}
      <View style={[styles.forecastCard, { backgroundColor: theme.card }]}>
        <View style={styles.forecastHeader}>
          <Text style={[styles.sectionTitle, { color: theme.text }]}>7-DAY FORECAST</Text>
          <Ionicons name="calendar-outline" size={20} color={theme.icon} />
        </View>
        {daily.length === 0 ? (
          <Text style={{ color: theme.icon, fontFamily: 'PlusJakartaSans_400Regular' }}>Loading forecast...</Text>
        ) : daily.map((item, idx) => (
          <View key={idx} style={[styles.forecastRow, { borderBottomColor: theme.border }]}>
            <Text style={[styles.forecastDay, { color: theme.text }]}>{item.day}</Text>
            <Ionicons name={item.icon as any} size={20} color={theme.icon} style={{ width: 30 }} />
            <View style={styles.chanceWrapper}>
              <Text style={[styles.forecastChance, { color: theme.primary }]}>{item.rain_prob}%</Text>
              <Ionicons name="water-outline" size={12} color={theme.primary} />
            </View>
            <Text style={[styles.forecastTemp, { color: theme.icon }]}>{item.temp_min}° / {item.temp_max}°</Text>
          </View>
        ))}
      </View>

      {/* Risk of Disaster */}
      <View style={[styles.riskContainer, { backgroundColor: theme.card }]}>
        <View style={styles.forecastHeader}>
          <Text style={[styles.sectionTitle, { color: theme.text }]}>RISK OF DISASTER</Text>
          <Ionicons name="information-circle-outline" size={20} color={theme.icon} />
        </View>
        <RiskGauge level={risk?.risk_level ?? 'Low'} color={risk?.risk_color ?? '#4CAF50'} />
        {(risk?.breakdown ?? []).map((b, i) => (
          <View key={i} style={[styles.riskPillRow, { backgroundColor: theme.background }]}>
            <View style={{ flexDirection: 'row', alignItems: 'center' }}>
              <Ionicons name={b.icon as any} size={16} color={b.color} />
              <Text style={[styles.riskType, { color: theme.text }]}>{b.label}</Text>
            </View>
            <Text style={[styles.riskLevel, { color: b.color }]}>{b.level}</Text>
          </View>
        ))}
      </View>

      {/* AI Flood Prediction */}
      {flood && <FloodPredictionCard data={flood} />}

      {/* AI Cyclone Prediction */}
      {cyclone && <CyclonePredictionCard data={cyclone} />}

      {/* ── Emergency Section ── */}
      <View style={{ marginBottom: 8 }}>
        <Text style={[styles.sectionTitle, { color: theme.text, marginBottom: 14 }]}>🚨 EMERGENCY</Text>
      </View>

      {/* SOS + flanking buttons row */}
      <View style={{ alignItems: 'center', marginBottom: 20 }}>
        {/* Pulsing ring */}
        <View style={{ alignItems: 'center', justifyContent: 'center', marginBottom: 16, width: 160, height: 160 }}>
          <Animated.View style={{
            position: 'absolute', width: 160, height: 160, borderRadius: 80,
            borderWidth: 3, borderColor: '#ef4444',
            transform: [{ scale: pulseAnim }], opacity: pulseOpacity,
          }} />
          <Animated.View style={{
            position: 'absolute', width: 130, height: 130, borderRadius: 65,
            borderWidth: 2, borderColor: '#ef4444',
            transform: [{ scale: pulseAnim }], opacity: pulseOpacity,
          }} />
          <TouchableOpacity
            style={[styles.sosButton, sosLoading && { opacity: 0.75 }]}
            activeOpacity={0.85}
            onPress={handleSOS}
            disabled={sosLoading}
          >
            {sosLoading
              ? <ActivityIndicator color="#fff" size="large" />
              : <>
                  <Ionicons name="warning" size={30} color="#FFF" />
                  <Text style={styles.sosText}>SOS</Text>
                </>}
          </TouchableOpacity>
        </View>
        <Text style={{ fontFamily: 'PlusJakartaSans_700Bold', fontSize: 11, letterSpacing: 2, color: '#ef4444', marginBottom: 6 }}>
          TAP FOR EMERGENCY
        </Text>
        <Text style={{ fontFamily: 'PlusJakartaSans_400Regular', fontSize: 12, color: theme.icon, textAlign: 'center' }}>
          Alerts rescue team with your live location
        </Text>
      </View>

      {/* Call Rescue + Call Nearby side by side */}
      <View style={{ flexDirection: 'row', gap: 12, marginBottom: 24 }}>
        <TouchableOpacity
          style={[styles.emergencyCardBtn, { backgroundColor: theme.card, flex: 1 }]}
          activeOpacity={0.8}
          onPress={handleCallRescue}
        >
          <View style={[styles.rescueIconWrap, { backgroundColor: '#fef2f2' }]}>
            <Ionicons name="call-outline" size={22} color="#dc2626" />
          </View>
          <Text style={[styles.emergencyTitle, { color: theme.text }]}>Call Rescue</Text>
          {/* Gear icon to edit */}
          <TouchableOpacity
            style={{ position: 'absolute', top: 10, right: 10, padding: 4 }}
            onPress={() => { setRescueInput(rescuePhone); setShowRescueEdit(true); }}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Ionicons name="settings-outline" size={14} color={theme.icon} />
          </TouchableOpacity>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.emergencyCardBtn, { backgroundColor: theme.card, flex: 1 }]}
          activeOpacity={0.8}
          onPress={handleCallNearby}
          disabled={nearbyLoading}
        >
          {nearbyLoading ? (
            <ActivityIndicator color={theme.primary} style={{ marginBottom: 8 }} />
          ) : (
            <View style={[styles.rescueIconWrap, { backgroundColor: '#eff6ff' }]}>
              <Ionicons name="people-outline" size={22} color={theme.primary} />
            </View>
          )}
          <Text style={[styles.emergencyTitle, { color: theme.text }]}>Nearby People</Text>
          <Text style={[styles.emergencySub, { color: theme.icon }]}>
            {nearbyLoading ? 'Finding…' : 'Alert closest person'}
          </Text>
        </TouchableOpacity>
      </View>
    </ScrollView>

    {/* ── Rescue Phone Edit Modal ── */}
    <Modal visible={showRescueEdit} transparent animationType="fade" onRequestClose={() => setShowRescueEdit(false)}>
      <View style={sosStyles.overlay}>
        <View style={[sosStyles.sheet, { paddingBottom: 28 }]}>
          <View style={sosStyles.header}>
            <Ionicons name="call-outline" size={24} color={theme.primary} />
            <Text style={sosStyles.headerTitle}>Set Rescue Team Number</Text>
            <Text style={sosStyles.headerSub}>This number will be dialled when you tap "Call Rescue Team"</Text>
          </View>
          <TextInput
            style={{
              borderWidth: 1.5, borderColor: theme.border, borderRadius: 14,
              paddingHorizontal: 16, paddingVertical: 14,
              fontSize: 18, fontFamily: 'PlusJakartaSans_600SemiBold',
              color: theme.text, backgroundColor: theme.background, marginBottom: 16,
              textAlign: 'center', letterSpacing: 2,
            }}
            value={rescueInput}
            onChangeText={setRescueInput}
            keyboardType="phone-pad"
            placeholder="e.g. 9353124446"
            placeholderTextColor={theme.icon}
          />
          <TouchableOpacity
            style={[sosStyles.optionBtn, { backgroundColor: theme.primary, borderColor: theme.primary, justifyContent: 'center' }]}
            onPress={saveRescuePhone}
          >
            <Text style={{ fontFamily: 'PlusJakartaSans_700Bold', fontSize: 15, color: '#fff' }}>Save Number</Text>
          </TouchableOpacity>
          <TouchableOpacity style={sosStyles.cancelBtn} onPress={() => setShowRescueEdit(false)}>
            <Text style={sosStyles.cancelText}>Cancel</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>

    {/* ── Emergency Type Picker Modal (works on web + native) ── */}
    <Modal
      visible={showSOSPicker}
      transparent
      animationType="slide"
      onRequestClose={() => setShowSOSPicker(false)}
    >
      <View style={sosStyles.overlay}>
        <View style={sosStyles.sheet}>
          {/* Header */}
          <View style={sosStyles.header}>
            <Ionicons name="warning" size={28} color="#ef4444" />
            <Text style={sosStyles.headerTitle}>What is your emergency?</Text>
            <Text style={sosStyles.headerSub}>Rescue team will be notified immediately</Text>
          </View>

          {/* Type buttons */}
          {[
            { label: 'In Danger (Flooding)',    icon: 'water',             color: '#ef4444', bg: '#fef2f2', category: 'In Danger'  },
            { label: 'Stranded / Need Help',    icon: 'flag',              color: '#f97316', bg: '#fff7ed', category: 'Stranded'   },
            { label: 'Injured / Need Assistance', icon: 'medkit',          color: '#8b5cf6', bg: '#f5f3ff', category: 'Injured'    },
          ].map((opt) => (
            <TouchableOpacity
              key={opt.category}
              style={[sosStyles.optionBtn, { backgroundColor: opt.bg, borderColor: opt.color }]}
              activeOpacity={0.8}
              onPress={() => { setShowSOSPicker(false); fireSOS(opt.category); }}
            >
              <View style={[sosStyles.optionIcon, { backgroundColor: opt.color }]}>
                <Ionicons name={opt.icon as any} size={20} color="#fff" />
              </View>
              <Text style={[sosStyles.optionText, { color: opt.color }]}>{opt.label}</Text>
              <Ionicons name="chevron-forward" size={18} color={opt.color} />
            </TouchableOpacity>
          ))}

          {/* Cancel */}
          <TouchableOpacity style={sosStyles.cancelBtn} onPress={() => setShowSOSPicker(false)}>
            <Text style={sosStyles.cancelText}>Cancel</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  container:        { flex: 1 },
  center:           { justifyContent: 'center', alignItems: 'center' },
  contentContainer: { padding: 20, paddingTop: 60, paddingBottom: 48 },
  loadingText:      { fontFamily: 'PlusJakartaSans_400Regular', fontSize: 14, marginTop: 12 },
  errorBanner:      { borderRadius: 14, padding: 14, marginBottom: 16, alignItems: 'center', borderWidth: 1, borderColor: '#fca5a5' },

  // ── Weather card
  mainCard:          { borderRadius: 28, padding: 22, marginBottom: 24, overflow: 'hidden' },
  dateText:          { fontFamily: 'PlusJakartaSans_500Medium', color: 'rgba(255,255,255,0.7)', fontSize: 10, letterSpacing: 1.5 },
  tempRow:           { flexDirection: 'row', alignItems: 'center', marginBottom: 4, marginTop: 8 },
  largeTemp:         { fontFamily: 'PlusJakartaSans_700Bold', fontSize: 76, color: '#FFF', lineHeight: 84, letterSpacing: -2 },
  weatherCondition:  { fontFamily: 'PlusJakartaSans_600SemiBold', fontSize: 18, color: '#FFF', lineHeight: 26 },
  feelsLikeText:     { fontFamily: 'PlusJakartaSans_400Regular', color: 'rgba(255,255,255,0.7)', fontSize: 13 },
  metricsContainer:  { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 20 },
  metricPill:        { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: 22, paddingHorizontal: 12, paddingVertical: 7 },
  metricLabel:       { fontFamily: 'PlusJakartaSans_400Regular', color: 'rgba(255,255,255,0.7)', fontSize: 10 },
  metricValue:       { fontFamily: 'PlusJakartaSans_700Bold', color: '#FFF', fontSize: 13 },

  // ── Section headers
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  sectionTitle:  { fontFamily: 'PlusJakartaSans_700Bold', fontSize: 11, letterSpacing: 1.5 },
  linkText:      { fontFamily: 'PlusJakartaSans_500Medium', fontSize: 14 },

  // ── Hourly
  hourlyScroll:  { marginBottom: 24 },
  hourlyItem:    { alignItems: 'center', paddingVertical: 14, paddingHorizontal: 14, borderRadius: 18, marginRight: 10, minWidth: 70 },
  hourlyTime:    { fontFamily: 'PlusJakartaSans_600SemiBold', fontSize: 11 },
  hourlyTemp:    { fontFamily: 'PlusJakartaSans_700Bold', fontSize: 17 },

  // ── 7-day
  forecastCard:   { borderRadius: 22, padding: 20, marginBottom: 24 },
  forecastHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  forecastRow:    { flexDirection: 'row', alignItems: 'center', paddingVertical: 13, borderBottomWidth: 1 },
  forecastDay:    { fontFamily: 'PlusJakartaSans_600SemiBold', fontSize: 14, flex: 1 },
  chanceWrapper:  { flexDirection: 'row', alignItems: 'center', width: 60 },
  forecastChance: { fontFamily: 'PlusJakartaSans_600SemiBold', fontSize: 12, marginRight: 4 },
  forecastTemp:   { fontFamily: 'PlusJakartaSans_500Medium', fontSize: 14, width: 76, textAlign: 'right' },

  // ── Risk
  riskContainer:  { borderRadius: 22, padding: 20, marginBottom: 24 },
  riskPillRow:    { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 13, borderRadius: 14, marginBottom: 8 },
  riskType:       { fontFamily: 'PlusJakartaSans_500Medium', fontSize: 14, marginLeft: 8 },
  riskLevel:      { fontFamily: 'PlusJakartaSans_700Bold', fontSize: 14 },

  // ── Emergency
  sosButton: {
    width: 108, height: 108, borderRadius: 54,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: '#dc2626',
    shadowColor: '#dc2626', shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.45, shadowRadius: 20, elevation: 12,
  },
  sosText:          { fontFamily: 'PlusJakartaSans_700Bold', fontSize: 20, color: '#FFF', marginTop: 3, letterSpacing: 1 },
  emergencyCardBtn: { borderRadius: 22, padding: 18, alignItems: 'center', minHeight: 110, justifyContent: 'center', position: 'relative' },
  rescueIconWrap:   { width: 46, height: 46, borderRadius: 15, alignItems: 'center', justifyContent: 'center', marginBottom: 10 },
  emergencyTitle:   { fontFamily: 'PlusJakartaSans_700Bold', fontSize: 14, marginBottom: 2, textAlign: 'center' },
  emergencySub:     { fontFamily: 'PlusJakartaSans_400Regular', fontSize: 11, textAlign: 'center' },
});

// ── SOS Picker Modal Styles ──────────────────────────────────────────────────
const sosStyles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.55)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    padding: 24,
    paddingBottom: 36,
  },
  header: {
    alignItems: 'center',
    marginBottom: 24,
  },
  headerTitle: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 19,
    color: '#0f172a',
    marginTop: 10,
    textAlign: 'center',
  },
  headerSub: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: '#64748b',
    marginTop: 4,
    textAlign: 'center',
  },
  optionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 16,
    borderWidth: 1.5,
    padding: 16,
    marginBottom: 12,
    gap: 14,
  },
  optionIcon: {
    width: 40,
    height: 40,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  optionText: {
    flex: 1,
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 15,
  },
  cancelBtn: {
    alignItems: 'center',
    paddingVertical: 14,
    marginTop: 4,
  },
  cancelText: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 15,
    color: '#94a3b8',
  },
});
