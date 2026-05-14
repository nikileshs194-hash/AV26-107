/**
 * FloodAlertModal — matches the uploaded design exactly:
 *  - White background, no red header
 *  - Warning triangle (red) + bold red "URBAN FLOOD ALERT" title
 *  - Gray subtitle + red "Please evacuate immediately."
 *  - Three info rows: NEAREST SAFE SHELTER / DISTANCE / SAFE ROUTE
 *  - Blue "Open Navigation" full-width button in SAFE ROUTE row
 *  - EMERGENCY OPTIONS: SOS (red) | I AM SAFE (green) side by side
 *  - X close button top-right
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  View, Text, Modal, TouchableOpacity, Linking,
  StyleSheet, Animated, Alert, ScrollView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { sendSOS } from '@/services/api';

// ── Data shape from push notification payload ─────────────────────────────────
export interface FloodAlertData {
  type:             'flood_alert';
  probability:      number;
  risk_level:       string;
  shelter_name:     string;
  shelter_distance: string;
  shelter_maps_url: string;
  shelter_lat:      number;
  shelter_lon:      number;
  user_lat:         number;
  user_lon:         number;
}

interface Props {
  visible:   boolean;
  data:      FloodAlertData | null;
  onDismiss: () => void;
}

// ── Component ──────────────────────────────────────────────────────────────────
export default function FloodAlertModal({ visible, data, onDismiss }: Props) {
  const slideAnim = useRef(new Animated.Value(900)).current;
  const [sosSent, setSosSent] = useState(false);
  const [safe,    setSafe]    = useState(false);

  useEffect(() => {
    if (visible) {
      setSosSent(false);
      setSafe(false);
      Animated.spring(slideAnim, {
        toValue: 0, useNativeDriver: true,
        tension: 65, friction: 11,
      }).start();
    } else {
      Animated.timing(slideAnim, {
        toValue: 900, duration: 220, useNativeDriver: true,
      }).start();
    }
  }, [visible]);

  if (!data) return null;

  // ── Open navigation ─────────────────────────────────────────────────────────
  const openNavigation = () => {
    Linking.openURL(data.shelter_maps_url).catch(() =>
      Linking.openURL(
        `https://www.google.com/maps/search/emergency+shelter/@${data.user_lat},${data.user_lon},15z`
      )
    );
  };

  // ── SOS ─────────────────────────────────────────────────────────────────────
  const handleSOS = async () => {
    try {
      const raw  = await AsyncStorage.getItem('jeevansetu_user');
      const user = raw ? JSON.parse(raw) : null;
      if (!user?.phone) {
        Alert.alert('Not logged in', 'Please log in to send an SOS.');
        return;
      }
      await sendSOS(
        user.phone,
        user.full_name ?? user.name ?? 'User',
        data.user_lat,
        data.user_lon,
        undefined,
        'Flood Emergency — Evacuation Required',
      );
      setSosSent(true);
      Alert.alert('✅ SOS Sent', 'Emergency services and nearby users have been notified.');
    } catch (e: any) {
      Alert.alert('SOS Failed', e?.message ?? 'Please try again.');
    }
  };

  // ── I AM SAFE ───────────────────────────────────────────────────────────────
  const handleSafe = () => {
    setSafe(true);
    Alert.alert(
      '✅ Marked Safe',
      'Glad you are safe! Stay alert and follow local evacuation advisories.',
      [{ text: 'Close', onPress: onDismiss }]
    );
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

          {/* ── Close button ─────────────────────────────────────────────── */}
          <TouchableOpacity style={styles.closeBtn} onPress={onDismiss} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
            <Ionicons name="close" size={22} color="#9ca3af" />
          </TouchableOpacity>

          <ScrollView
            contentContainerStyle={styles.content}
            bounces={false}
            showsVerticalScrollIndicator={false}
          >

            {/* ── Warning triangle ─────────────────────────────────────── */}
            <View style={styles.triangleWrap}>
              <Ionicons name="warning" size={52} color="#ef4444" />
            </View>

            {/* ── Titles ──────────────────────────────────────────────── */}
            <Text style={styles.title}>URBAN FLOOD ALERT</Text>
            <Text style={styles.subtitle}>
              Severe flood risk detected in{'\n'}your current area.
            </Text>
            <Text style={styles.evacuate}>Please evacuate{'\n'}immediately.</Text>

            {/* ── Divider ──────────────────────────────────────────────── */}
            <View style={styles.divider} />

            {/* ── Info rows ────────────────────────────────────────────── */}

            {/* NEAREST SAFE SHELTER */}
            <View style={styles.row}>
              <View style={[styles.rowIcon, { backgroundColor: '#dcfce7' }]}>
                <Ionicons name="business-outline" size={22} color="#16a34a" />
              </View>
              <View style={styles.rowText}>
                <Text style={styles.rowLabel}>NEAREST SAFE SHELTER</Text>
                <Text style={styles.rowValue} numberOfLines={2}>{data.shelter_name}</Text>
              </View>
            </View>

            {/* DISTANCE */}
            <View style={styles.row}>
              <View style={[styles.rowIcon, { backgroundColor: '#dbeafe' }]}>
                <Ionicons name="location-outline" size={22} color="#2563eb" />
              </View>
              <View style={styles.rowText}>
                <Text style={styles.rowLabel}>DISTANCE</Text>
                <Text style={styles.rowDist}>{data.shelter_distance}</Text>
              </View>
            </View>

            {/* SAFE ROUTE */}
            <View style={styles.row}>
              <View style={[styles.rowIcon, { backgroundColor: '#ede9fe' }]}>
                <Ionicons name="map-outline" size={22} color="#7c3aed" />
              </View>
              <View style={styles.rowText}>
                <Text style={styles.rowLabel}>SAFE ROUTE</Text>
                <TouchableOpacity style={styles.navBtn} onPress={openNavigation} activeOpacity={0.85}>
                  <Ionicons name="navigate" size={16} color="#fff" />
                  <Text style={styles.navBtnText}>Open Navigation</Text>
                </TouchableOpacity>
              </View>
            </View>

            {/* ── Emergency options ─────────────────────────────────────── */}
            <Text style={styles.emergencyLabel}>EMERGENCY OPTIONS:</Text>

            <View style={styles.btnRow}>
              {/* SOS */}
              <TouchableOpacity
                style={[styles.sosBtn, sosSent && styles.btnDisabled]}
                onPress={handleSOS}
                activeOpacity={0.85}
                disabled={sosSent}
              >
                <Ionicons name={sosSent ? 'checkmark-circle' : 'call'} size={24} color="#fff" />
                <Text style={styles.btnLabel}>{sosSent ? 'SENT ✓' : 'SOS'}</Text>
              </TouchableOpacity>

              {/* I AM SAFE */}
              <TouchableOpacity
                style={[styles.safeBtn, safe && styles.btnDisabled]}
                onPress={handleSafe}
                activeOpacity={0.85}
                disabled={safe}
              >
                <Ionicons name="checkmark-circle" size={24} color="#fff" />
                <Text style={styles.btnLabel}>{safe ? 'SAFE ✓' : 'I AM SAFE'}</Text>
              </TouchableOpacity>
            </View>

          </ScrollView>
        </Animated.View>
      </View>
    </Modal>
  );
}

// ── Styles ─────────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  overlay: {
    flex:            1,
    backgroundColor: 'rgba(0,0,0,0.55)',
    justifyContent:  'flex-end',
  },
  sheet: {
    backgroundColor:      '#fff',
    borderTopLeftRadius:   28,
    borderTopRightRadius:  28,
    paddingBottom:         34,
    maxHeight:            '92%',
  },

  // ── Close ──
  closeBtn: {
    position:  'absolute',
    top:        16,
    right:      18,
    zIndex:     10,
    padding:     4,
  },

  // ── Scrollable content ──
  content: {
    alignItems:        'center',
    paddingTop:         32,
    paddingBottom:      16,
    paddingHorizontal:  24,
  },

  // ── Triangle ──
  triangleWrap: {
    marginBottom: 14,
  },

  // ── Titles ──
  title: {
    fontFamily:    'PlusJakartaSans_700Bold',
    fontSize:       26,
    color:         '#ef4444',
    letterSpacing:  0.5,
    textAlign:     'center',
    marginBottom:   10,
  },
  subtitle: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize:    15,
    color:      '#6b7280',
    textAlign:  'center',
    lineHeight:  22,
    marginBottom: 10,
  },
  evacuate: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize:    18,
    color:      '#ef4444',
    textAlign:  'center',
    lineHeight:  26,
    marginBottom: 18,
  },

  // ── Divider ──
  divider: {
    width:           '100%',
    height:           1,
    backgroundColor: '#f1f5f9',
    marginBottom:    20,
  },

  // ── Info rows ──
  row: {
    flexDirection: 'row',
    alignItems:    'center',
    width:         '100%',
    marginBottom:   16,
    gap:            14,
  },
  rowIcon: {
    width:          56,
    height:         56,
    borderRadius:   16,
    alignItems:     'center',
    justifyContent: 'center',
    flexShrink:      0,
  },
  rowText: { flex: 1 },
  rowLabel: {
    fontFamily:    'PlusJakartaSans_600SemiBold',
    fontSize:       11,
    color:         '#9ca3af',
    letterSpacing:  0.8,
    marginBottom:   4,
  },
  rowValue: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize:    15,
    color:      '#111827',
    lineHeight:  22,
  },
  rowDist: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize:    22,
    color:      '#111827',
  },

  // ── Navigation button ──
  navBtn: {
    flexDirection:   'row',
    alignItems:      'center',
    justifyContent:  'center',
    backgroundColor: '#2563eb',
    borderRadius:    12,
    paddingVertical:  11,
    paddingHorizontal: 20,
    gap:               8,
    alignSelf:        'flex-start',
    minWidth:          160,
  },
  navBtnText: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize:    15,
    color:      '#fff',
  },

  // ── Emergency options ──
  emergencyLabel: {
    fontFamily:    'PlusJakartaSans_600SemiBold',
    fontSize:       11,
    color:         '#9ca3af',
    letterSpacing:  1,
    alignSelf:     'flex-start',
    marginTop:      6,
    marginBottom:   14,
  },
  btnRow: {
    flexDirection: 'row',
    gap:            14,
    width:         '100%',
  },
  sosBtn: {
    flex:            1,
    flexDirection:   'column',
    alignItems:      'center',
    justifyContent:  'center',
    backgroundColor: '#ef4444',
    borderRadius:    16,
    paddingVertical:  20,
    gap:              8,
    shadowColor:    '#ef4444',
    shadowOffset:   { width: 0, height: 4 },
    shadowOpacity:   0.3,
    shadowRadius:    10,
    elevation:        6,
  },
  safeBtn: {
    flex:            1,
    flexDirection:   'column',
    alignItems:      'center',
    justifyContent:  'center',
    backgroundColor: '#16a34a',
    borderRadius:    16,
    paddingVertical:  20,
    gap:              8,
    shadowColor:    '#16a34a',
    shadowOffset:   { width: 0, height: 4 },
    shadowOpacity:   0.3,
    shadowRadius:    10,
    elevation:        6,
  },
  btnDisabled: {
    backgroundColor: '#9ca3af',
    shadowColor:    '#9ca3af',
  },
  btnLabel: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize:    15,
    color:      '#fff',
    letterSpacing: 0.3,
  },
});
