import React, { useState, useCallback, useEffect, useRef } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  ActivityIndicator, RefreshControl, Animated, Alert,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Colors } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';
import Header from '@/components/Header';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';

import useLocation from '@/hooks/useLocation';
import { fetchAlerts, saveAlerts, getSavedAlerts, clearAlert, AlertItem } from '@/services/api';

const USER_KEY      = 'jeevansetu_user';
const OFFLINE_KEY   = 'jeevansetu_offline_alerts';
const AUTO_REFRESH  = 5 * 60 * 1000;

async function getStoredPhone(): Promise<string | null> {
  try {
    const raw = await AsyncStorage.getItem(USER_KEY);
    if (!raw) return null;
    return JSON.parse(raw)?.phone ?? null;
  } catch { return null; }
}

// ── Severity config ───────────────────────────────────────────────────────────
function getSeverityConfig(severity: string) {
  switch (severity) {
    case 'Extreme': return { bg: '#FEF2F2', border: '#FCA5A5', text: '#991B1B', dot: '#DC2626', gradStart: '#DC2626', gradEnd: '#991B1B' };
    case 'Severe':  return { bg: '#FEF2F2', border: '#FCA5A5', text: '#991B1B', dot: '#EF4444', gradStart: '#EF4444', gradEnd: '#DC2626' };
    case 'Moderate':return { bg: '#FFFBEB', border: '#FCD34D', text: '#92400E', dot: '#F59E0B', gradStart: '#F59E0B', gradEnd: '#D97706' };
    default:        return { bg: '#F0FDF4', border: '#86EFAC', text: '#166534', dot: '#22C55E', gradStart: '#22C55E', gradEnd: '#16A34A' };
  }
}

// ── Alert Card ────────────────────────────────────────────────────────────────
function AlertCard({
  alert, theme, index, onClear,
}: { alert: AlertItem; theme: any; index: number; onClear: () => void }) {
  const translateY = useRef(new Animated.Value(30)).current;
  const opacity    = useRef(new Animated.Value(0)).current;
  const cfg        = getSeverityConfig(alert.severity);

  useEffect(() => {
    Animated.parallel([
      Animated.timing(translateY, {
        toValue: 0, duration: 380,
        delay: index * 60,
        useNativeDriver: true,
      }),
      Animated.timing(opacity, {
        toValue: 1, duration: 380,
        delay: index * 60,
        useNativeDriver: true,
      }),
    ]).start();
  }, []);

  return (
    <Animated.View style={{ opacity, transform: [{ translateY }] }}>
      <View style={[styles.alertCard, { backgroundColor: theme.card }]}>
        {/* Severity strip on left */}
        <View style={[styles.severityStrip, { backgroundColor: cfg.dot }]} />

        <View style={styles.cardInner}>
          {/* Header row: icon + title + delete */}
          <View style={styles.alertHeader}>
            <View style={[styles.alertIconBox, { backgroundColor: alert.iconBg }]}>
              <Ionicons name={alert.icon as any} size={20} color={alert.iconColor} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[styles.alertTitle, { color: theme.text }]} numberOfLines={2}>
                {alert.title}
              </Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 4 }}>
                <View style={[styles.severityChip, { backgroundColor: cfg.bg, borderColor: cfg.border }]}>
                  <View style={[styles.severityDot, { backgroundColor: cfg.dot }]} />
                  <Text style={[styles.severityLabel, { color: cfg.text }]}>{alert.severity.toUpperCase()}</Text>
                </View>
                <Text style={[styles.whenText, { color: alert.whenColor }]}>{alert.when}</Text>
              </View>
            </View>
            <TouchableOpacity onPress={onClear} style={styles.clearBtn} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
              <Ionicons name="close-circle" size={20} color={theme.border} />
            </TouchableOpacity>
          </View>

          {/* Description */}
          <Text style={[styles.alertDesc, { color: theme.icon }]} numberOfLines={3}>
            {alert.desc}
          </Text>

          {/* Footer */}
          <View style={styles.alertFooter}>
            <Ionicons name="location-outline" size={11} color={theme.icon} />
            <Text style={[styles.alertLocation, { color: theme.icon }]} numberOfLines={1}>
              {' '}{alert.location}
            </Text>
            <View style={{ flex: 1 }} />
            <View style={[styles.sourceBadge, { backgroundColor: theme.background }]}>
              <Text style={[styles.sourceText, { color: theme.primary }]}>{alert.source}</Text>
            </View>
          </View>
        </View>
      </View>
    </Animated.View>
  );
}

// ── Main Screen ───────────────────────────────────────────────────────────────
export default function AlertsScreen() {
  const colorScheme  = useColorScheme() ?? 'light';
  const theme        = Colors[colorScheme];
  const { location } = useLocation();

  const [phone, setPhone]             = useState<string | null>(null);
  const [alerts, setAlerts]           = useState<AlertItem[]>([]);
  const [loading, setLoading]         = useState(false);
  const [refreshing, setRefreshing]   = useState(false);
  const [error, setError]             = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState('');
  const [isOffline, setIsOffline]     = useState(false);

  useEffect(() => {
    getStoredPhone().then(p => setPhone(p));
  }, []);

  const load = useCallback(async (isRefresh = false) => {
    if (!location) return;
    isRefresh ? setRefreshing(true) : setLoading(true);
    setError(null);
    setIsOffline(false);
    try {
      const userPhone = phone ?? (await getStoredPhone());
      const fresh     = await fetchAlerts(location.lat, location.lon);
      const freshAlerts = fresh.alerts ?? [];

      // Save to offline cache
      if (freshAlerts.length > 0) {
        await AsyncStorage.setItem(OFFLINE_KEY, JSON.stringify(freshAlerts)).catch(() => {});
      }

      if (userPhone && freshAlerts.length > 0) {
        try { await saveAlerts(userPhone, freshAlerts); } catch { /* ignore */ }
      }

      if (userPhone) {
        try {
          const dbRes = await getSavedAlerts(userPhone);
          setAlerts(dbRes.alerts ?? []);
        } catch {
          setAlerts(freshAlerts);
        }
      } else {
        setAlerts(freshAlerts);
      }
      setLastUpdated(new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }));
    } catch (e: any) {
      // Network failed — try offline cache
      try {
        const cached = await AsyncStorage.getItem(OFFLINE_KEY);
        if (cached) {
          setAlerts(JSON.parse(cached));
          setIsOffline(true);
        } else {
          setError('No network. Pull to retry.');
        }
      } catch {
        setError(e.message || 'Failed to load alerts');
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [location, phone]);

  useEffect(() => {
    const interval = setInterval(() => load(true), AUTO_REFRESH);
    return () => clearInterval(interval);
  }, [load]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const handleClear = async (alert: AlertItem) => {
    const userPhone = phone ?? await getStoredPhone();
    setAlerts(prev => prev.filter(a => (a.db_id ?? a.id) !== (alert.db_id ?? alert.id)));
    if (userPhone) {
      try { await clearAlert(userPhone, alert.db_id); } catch { /* already removed from UI */ }
    }
  };

  const handleClearAll = async () => {
    if (alerts.length === 0) return;
    Alert.alert('Clear All Alerts', 'Remove all saved alerts? This cannot be undone.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Clear All', style: 'destructive',
        onPress: async () => {
          const userPhone = phone ?? await getStoredPhone();
          setAlerts([]);
          await AsyncStorage.removeItem(OFFLINE_KEY).catch(() => {});
          if (userPhone) {
            try { await clearAlert(userPhone); } catch { /* ignore */ }
          }
        },
      },
    ]);
  };

  if (loading) {
    return (
      <View style={[styles.container, styles.center, { backgroundColor: theme.background }]}>
        <ActivityIndicator size="large" color={theme.primary} />
        <Text style={[styles.loadingText, { color: theme.icon }]}>Checking weather alerts…</Text>
      </View>
    );
  }

  const extremeCount  = alerts.filter(a => a.severity === 'Extreme').length;
  const severeCount   = alerts.filter(a => a.severity === 'Severe').length;
  const moderateCount = alerts.filter(a => a.severity === 'Moderate').length;

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: theme.background }]}
      contentContainerStyle={styles.contentContainer}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={theme.primary} />}
    >
      <Header city={location?.city} />

      {/* Page title row */}
      <View style={styles.titleRow}>
        <View style={{ flex: 1 }}>
          <Text style={[styles.pageTitle, { color: theme.text }]}>Alerts</Text>
          {lastUpdated ? (
            <Text style={[styles.updatedText, { color: theme.icon }]}>Updated {lastUpdated}</Text>
          ) : null}
        </View>
        {alerts.length > 0 && (
          <TouchableOpacity onPress={handleClearAll} style={styles.clearAllBtn}>
            <Ionicons name="trash-outline" size={14} color="#DC2626" />
            <Text style={styles.clearAllText}>Clear All</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* Offline banner */}
      {isOffline && (
        <View style={styles.offlineBanner}>
          <Ionicons name="cloud-offline-outline" size={15} color="#D97706" />
          <Text style={styles.offlineText}>Offline — showing cached alerts. Pull to refresh.</Text>
        </View>
      )}

      {/* Error banner */}
      {error && !isOffline && (
        <TouchableOpacity style={[styles.errorBanner, { backgroundColor: theme.card }]} onPress={() => load()}>
          <Ionicons name="wifi-outline" size={15} color="#DC2626" />
          <Text style={[styles.errorText, { color: '#DC2626' }]}>{error}</Text>
          <Text style={[styles.retryText, { color: theme.primary }]}>Retry</Text>
        </TouchableOpacity>
      )}

      {/* Severity summary chips */}
      {alerts.length > 0 && (
        <View style={styles.summaryRow}>
          {extremeCount > 0 && (
            <View style={[styles.summaryChip, { backgroundColor: '#FEF2F2', borderColor: '#FCA5A5' }]}>
              <Text style={[styles.summaryChipText, { color: '#991B1B' }]}>{extremeCount} Extreme</Text>
            </View>
          )}
          {severeCount > 0 && (
            <View style={[styles.summaryChip, { backgroundColor: '#FEF2F2', borderColor: '#FCA5A5' }]}>
              <Text style={[styles.summaryChipText, { color: '#DC2626' }]}>{severeCount} Severe</Text>
            </View>
          )}
          {moderateCount > 0 && (
            <View style={[styles.summaryChip, { backgroundColor: '#FFFBEB', borderColor: '#FCD34D' }]}>
              <Text style={[styles.summaryChipText, { color: '#92400E' }]}>{moderateCount} Moderate</Text>
            </View>
          )}
        </View>
      )}

      {/* Alert cards */}
      <View style={styles.cardsList}>
        {alerts.length === 0 ? (
          <View style={styles.emptyBox}>
            <LinearGradient colors={['#F0FDF4', '#DCFCE7']} style={styles.emptyIconBg}>
              <Ionicons name="checkmark-circle" size={48} color="#22C55E" />
            </LinearGradient>
            <Text style={[styles.emptyTitle, { color: theme.text }]}>All Clear</Text>
            <Text style={[styles.emptyText, { color: theme.icon }]}>
              No active weather alerts for your area.{'\n'}Pull down to refresh.
            </Text>
          </View>
        ) : (
          alerts.map((alert, i) => (
            <AlertCard
              key={alert.db_id ?? alert.id}
              alert={alert}
              theme={theme}
              index={i}
              onClear={() => handleClear(alert)}
            />
          ))
        )}
      </View>

      {/* Footer info card */}
      <View style={[styles.infoBanner, { backgroundColor: theme.card }]}>
        <LinearGradient colors={['#EFF6FF', '#DBEAFE']} style={styles.infoIconBg}>
          <Ionicons name="shield-checkmark" size={22} color="#2563EB" />
        </LinearGradient>
        <View style={{ flex: 1 }}>
          <Text style={[styles.infoTitle, { color: theme.text }]}>Stay Safe. Stay Informed.</Text>
          <Text style={[styles.infoSub, { color: theme.icon }]}>
            Alerts auto-refresh every 5 min · Alerts saved for offline access
          </Text>
        </View>
      </View>
    </ScrollView>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  container:        { flex: 1 },
  center:           { justifyContent: 'center', alignItems: 'center' },
  contentContainer: { padding: 20, paddingTop: 60, paddingBottom: 48 },
  loadingText:      { fontFamily: 'PlusJakartaSans_400Regular', fontSize: 14, marginTop: 12 },

  titleRow:    { flexDirection: 'row', alignItems: 'center', marginBottom: 20, gap: 12 },
  pageTitle:   { fontFamily: 'PlusJakartaSans_700Bold', fontSize: 34, letterSpacing: -0.5 },
  updatedText: { fontFamily: 'PlusJakartaSans_400Regular', fontSize: 11, marginTop: 2 },
  clearAllBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 7, paddingHorizontal: 12, borderRadius: 20, backgroundColor: '#FEF2F2' },
  clearAllText:{ fontFamily: 'PlusJakartaSans_600SemiBold', fontSize: 12, color: '#DC2626' },

  offlineBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: '#FFFBEB', borderRadius: 12, padding: 12, marginBottom: 14, borderWidth: 1, borderColor: '#FCD34D' },
  offlineText:   { fontFamily: 'PlusJakartaSans_500Medium', fontSize: 13, color: '#92400E', flex: 1 },

  errorBanner: { flexDirection: 'row', alignItems: 'center', borderRadius: 12, padding: 14, marginBottom: 16, gap: 8 },
  errorText:   { fontFamily: 'PlusJakartaSans_500Medium', flex: 1, fontSize: 13 },
  retryText:   { fontFamily: 'PlusJakartaSans_600SemiBold', fontSize: 13 },

  summaryRow:      { flexDirection: 'row', gap: 8, marginBottom: 16, flexWrap: 'wrap' },
  summaryChip:     { borderRadius: 20, paddingVertical: 4, paddingHorizontal: 12, borderWidth: 1 },
  summaryChipText: { fontFamily: 'PlusJakartaSans_700Bold', fontSize: 11, letterSpacing: 0.5 },

  cardsList:  { gap: 12, marginBottom: 24 },

  // Alert card
  alertCard:     { borderRadius: 18, overflow: 'hidden', flexDirection: 'row', shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.06, shadowRadius: 8, elevation: 3 },
  severityStrip: { width: 4, borderRadius: 2 },
  cardInner:     { flex: 1, padding: 16 },
  alertHeader:   { flexDirection: 'row', gap: 12, marginBottom: 10 },
  alertIconBox:  { width: 44, height: 44, borderRadius: 13, justifyContent: 'center', alignItems: 'center', flexShrink: 0 },
  alertTitle:    { fontFamily: 'PlusJakartaSans_700Bold', fontSize: 14, lineHeight: 20 },
  severityChip:  { flexDirection: 'row', alignItems: 'center', gap: 5, borderRadius: 20, paddingVertical: 3, paddingHorizontal: 8, borderWidth: 1 },
  severityDot:   { width: 6, height: 6, borderRadius: 3 },
  severityLabel: { fontFamily: 'PlusJakartaSans_700Bold', fontSize: 9, letterSpacing: 0.8 },
  whenText:      { fontFamily: 'PlusJakartaSans_600SemiBold', fontSize: 12 },
  clearBtn:      { padding: 2, alignSelf: 'flex-start' },
  alertDesc:     { fontFamily: 'PlusJakartaSans_400Regular', fontSize: 13, lineHeight: 20, marginBottom: 10, color: '#64748B' },
  alertFooter:   { flexDirection: 'row', alignItems: 'center' },
  alertLocation: { fontFamily: 'PlusJakartaSans_400Regular', fontSize: 11, flex: 1 },
  sourceBadge:   { borderRadius: 8, paddingVertical: 3, paddingHorizontal: 8 },
  sourceText:    { fontFamily: 'PlusJakartaSans_600SemiBold', fontSize: 10 },

  // Empty state
  emptyBox:    { alignItems: 'center', paddingVertical: 64, gap: 14 },
  emptyIconBg: { width: 88, height: 88, borderRadius: 28, alignItems: 'center', justifyContent: 'center' },
  emptyTitle:  { fontFamily: 'PlusJakartaSans_700Bold', fontSize: 20 },
  emptyText:   { fontFamily: 'PlusJakartaSans_400Regular', fontSize: 14, textAlign: 'center', lineHeight: 22, maxWidth: 260 },

  // Footer
  infoBanner:  { borderRadius: 18, padding: 16, flexDirection: 'row', alignItems: 'center', gap: 14 },
  infoIconBg:  { width: 46, height: 46, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  infoTitle:   { fontFamily: 'PlusJakartaSans_700Bold', fontSize: 13, marginBottom: 3 },
  infoSub:     { fontFamily: 'PlusJakartaSans_400Regular', fontSize: 11, lineHeight: 17 },
});
