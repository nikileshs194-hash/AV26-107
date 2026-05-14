/**
 * SOSAlertModal
 * Shown when a nearby user sends an SOS / "Call Nearby People" alert.
 * Matches the red-header emergency card shown in the design screenshot.
 */
import React, { useEffect, useRef } from 'react';
import {
  View, Text, Modal, TouchableOpacity, Linking,
  StyleSheet, Animated, Platform, ScrollView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

export interface SOSAlertData {
  sos_id?: string;
  victim_name: string;
  victim_phone: string;
  victim_lat: number;
  victim_lon: number;
  address: string;
  distance_m: number;
  google_maps_url: string;
}

interface Props {
  visible: boolean;
  data: SOSAlertData | null;
  onDismiss: () => void;
}

export default function SOSAlertModal({ visible, data, onDismiss }: Props) {
  const slideAnim = useRef(new Animated.Value(800)).current;
  const pulseAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (visible) {
      Animated.spring(slideAnim, {
        toValue: 0, useNativeDriver: true,
        tension: 65, friction: 10,
      }).start();

      // Pulse the call button
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 1.06, duration: 700, useNativeDriver: true }),
          Animated.timing(pulseAnim, { toValue: 1,    duration: 700, useNativeDriver: true }),
        ])
      ).start();
    } else {
      Animated.timing(slideAnim, {
        toValue: 800, duration: 250, useNativeDriver: true,
      }).start();
    }
  }, [visible]);

  if (!data) return null;

  const distText =
    data.distance_m >= 1000
      ? `${(data.distance_m / 1000).toFixed(1)} km`
      : `${data.distance_m} meters`;

  const callVictim = () => {
    const tel = data.victim_phone.replace(/\s/g, '');
    Linking.openURL(`tel:${tel}`);
  };

  const openMaps = () => {
    Linking.openURL(data.google_maps_url);
  };

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      statusBarTranslucent
      onRequestClose={onDismiss}
    >
      <View style={styles.overlay}>
        <Animated.View style={[styles.sheet, { transform: [{ translateY: slideAnim }] }]}>

          {/* ── Red Header ───────────────────────────────── */}
          <View style={styles.header}>
            {/* Pulsing warning icon */}
            <View style={styles.iconWrap}>
              <Ionicons name="warning" size={32} color="#ef4444" />
            </View>

            <Text style={styles.headerTitle}>EMERGENCY SOS ALERT</Text>
            <Text style={styles.headerSub}>A person nearby requires urgent help</Text>

            <TouchableOpacity style={styles.closeBtn} onPress={onDismiss}>
              <Ionicons name="close" size={20} color="#fff" />
            </TouchableOpacity>
          </View>

          {/* ── Info Cards ───────────────────────────────── */}
          <ScrollView style={styles.body} contentContainerStyle={{ paddingBottom: 24 }} bounces={false}>

            {/* Distance */}
            <View style={styles.card}>
              <View style={[styles.cardIcon, { backgroundColor: '#fee2e2' }]}>
                <Ionicons name="person" size={22} color="#ef4444" />
              </View>
              <View style={styles.cardText}>
                <Text style={styles.cardLabel}>VICTIM DISTANCE</Text>
                <Text style={styles.cardValueRed}>
                  <Text style={styles.cardValueBig}>{distText}</Text>
                  {' '}from your location
                </Text>
              </View>
            </View>

            {/* Location */}
            <View style={styles.card}>
              <View style={[styles.cardIcon, { backgroundColor: '#dcfce7' }]}>
                <Ionicons name="location" size={22} color="#16a34a" />
              </View>
              <View style={styles.cardText}>
                <Text style={styles.cardLabel}>LOCATION</Text>
                <Text style={styles.cardValue}>{data.address}</Text>
              </View>
            </View>

            {/* Google Maps */}
            <TouchableOpacity style={styles.card} onPress={openMaps} activeOpacity={0.7}>
              <View style={[styles.cardIcon, { backgroundColor: '#dbeafe' }]}>
                <Ionicons name="map" size={22} color="#2563eb" />
              </View>
              <View style={styles.cardText}>
                <Text style={styles.cardLabel}>LIVE GOOGLE MAPS</Text>
                <Text style={styles.cardLink} numberOfLines={1}>
                  {data.google_maps_url}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={16} color="#94a3b8" />
            </TouchableOpacity>

            {/* Quick Actions */}
            <Text style={styles.actionsLabel}>QUICK ACTIONS</Text>

            <Animated.View style={{ transform: [{ scale: pulseAnim }] }}>
              <TouchableOpacity style={styles.callBtn} onPress={callVictim} activeOpacity={0.85}>
                <Ionicons name="call" size={20} color="#fff" />
                <Text style={styles.callBtnText}>Call {data.victim_name}</Text>
              </TouchableOpacity>
            </Animated.View>

            <TouchableOpacity style={styles.mapsBtn} onPress={openMaps} activeOpacity={0.85}>
              <Ionicons name="navigate" size={18} color="#2563eb" />
              <Text style={styles.mapsBtnText}>Navigate to Location</Text>
            </TouchableOpacity>

            {/* Urgency banner */}
            <View style={styles.urgencyBanner}>
              <Ionicons name="time" size={16} color="#ef4444" />
              <Text style={styles.urgencyText}>
                Your quick response can save a life.{' '}
                <Text style={{ fontFamily: 'PlusJakartaSans_700Bold', color: '#ef4444' }}>
                  PLEASE ACT IMMEDIATELY.
                </Text>
              </Text>
            </View>

            {/* Dismiss */}
            <TouchableOpacity style={styles.dismissBtn} onPress={onDismiss}>
              <Text style={styles.dismissText}>I cannot help right now</Text>
            </TouchableOpacity>
          </ScrollView>

        </Animated.View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.65)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    overflow: 'hidden',
    maxHeight: '92%',
  },

  // Header
  header: {
    backgroundColor: '#ef4444',
    paddingTop: 32,
    paddingBottom: 28,
    paddingHorizontal: 24,
    alignItems: 'center',
  },
  iconWrap: {
    width: 68,
    height: 68,
    borderRadius: 18,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 14,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
    elevation: 6,
  },
  headerTitle: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 20,
    color: '#fff',
    letterSpacing: 0.5,
    textAlign: 'center',
  },
  headerSub: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: 'rgba(255,255,255,0.85)',
    marginTop: 4,
    textAlign: 'center',
  },
  closeBtn: {
    position: 'absolute',
    top: 16,
    right: 16,
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: 'rgba(0,0,0,0.2)',
    alignItems: 'center',
    justifyContent: 'center',
  },

  // Body
  body: {
    paddingHorizontal: 20,
    paddingTop: 20,
  },

  // Info cards
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f8fafc',
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
    gap: 14,
    borderWidth: 1,
    borderColor: '#f1f5f9',
  },
  cardIcon: {
    width: 46,
    height: 46,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  cardText: { flex: 1 },
  cardLabel: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 10,
    color: '#94a3b8',
    letterSpacing: 0.8,
    marginBottom: 3,
  },
  cardValue: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 15,
    color: '#0f172a',
    lineHeight: 20,
  },
  cardValueRed: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 14,
    color: '#374151',
  },
  cardValueBig: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 18,
    color: '#ef4444',
  },
  cardLink: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 13,
    color: '#2563eb',
  },

  // Actions
  actionsLabel: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 11,
    color: '#94a3b8',
    letterSpacing: 1,
    marginBottom: 12,
    marginTop: 4,
  },
  callBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#ef4444',
    borderRadius: 16,
    paddingVertical: 16,
    gap: 10,
    marginBottom: 10,
    shadowColor: '#ef4444',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.35,
    shadowRadius: 12,
    elevation: 8,
  },
  callBtnText: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 16,
    color: '#fff',
  },
  mapsBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#eff6ff',
    borderRadius: 16,
    paddingVertical: 14,
    gap: 8,
    marginBottom: 16,
    borderWidth: 1.5,
    borderColor: '#bfdbfe',
  },
  mapsBtnText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 15,
    color: '#2563eb',
  },

  // Urgency
  urgencyBanner: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: '#fff1f2',
    borderRadius: 12,
    padding: 14,
    gap: 10,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#fecaca',
  },
  urgencyText: {
    flex: 1,
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: '#374151',
    lineHeight: 19,
  },

  // Dismiss
  dismissBtn: {
    alignItems: 'center',
    paddingVertical: 8,
  },
  dismissText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: '#94a3b8',
    textDecorationLine: 'underline',
  },
});
