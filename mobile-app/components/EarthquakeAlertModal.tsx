import React, { useEffect, useRef, useState } from 'react';
import {
  View, Text, Modal, TouchableOpacity, Linking,
  StyleSheet, Animated, Alert, ScrollView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { sendSOS } from '@/services/api';

export interface EarthquakeAlertData {
  type:         'earthquake_alert';
  probability:  number;
  risk_level:   string;
  seismic_zone: string;
  user_lat:     number;
  user_lon:     number;
}

interface Props {
  visible:   boolean;
  data:      EarthquakeAlertData | null;
  onDismiss: () => void;
}

export default function EarthquakeAlertModal({ visible, data, onDismiss }: Props) {
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

  const pct  = Math.round((data.probability ?? 0) * 100);
  const risk = data.risk_level   ?? 'High';
  const zone = data.seismic_zone ?? 'Zone IV';

  const openSafetyInfo = () => {
    Linking.openURL(
      `https://www.google.com/maps/search/emergency+assembly+point/@${data.user_lat},${data.user_lon},14z`
    );
  };

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
        'Earthquake Emergency — Trapped / Injured',
      );
      setSosSent(true);
      Alert.alert('✅ SOS Sent', 'Emergency services and nearby users have been notified.');
    } catch (e: any) {
      Alert.alert('SOS Failed', e?.message ?? 'Please try again.');
    }
  };

  const handleSafe = () => {
    setSafe(true);
    Alert.alert(
      '✅ Marked Safe',
      'Stay outdoors away from buildings. Watch for aftershocks.',
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

          <TouchableOpacity style={styles.closeBtn} onPress={onDismiss} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
            <Ionicons name="close" size={22} color="#9ca3af" />
          </TouchableOpacity>

          <ScrollView contentContainerStyle={styles.content} bounces={false} showsVerticalScrollIndicator={false}>

            {/* Icon */}
            <View style={styles.iconWrap}>
              <Text style={styles.iconEmoji}>🪨</Text>
            </View>

            {/* Titles */}
            <Text style={styles.title}>EARTHQUAKE ALERT</Text>
            <Text style={styles.subtitle}>
              {risk} seismic risk ({pct}%) detected{'\n'}in your current region.
            </Text>
            <Text style={styles.action}>Move to open ground.{'\n'}Stay away from buildings.</Text>

            <View style={styles.divider} />

            {/* Seismic Zone */}
            <View style={styles.row}>
              <View style={[styles.rowIcon, { backgroundColor: '#fff7ed' }]}>
                <Ionicons name="layers-outline" size={22} color="#d97706" />
              </View>
              <View style={styles.rowText}>
                <Text style={styles.rowLabel}>BIS 1893 SEISMIC ZONE</Text>
                <Text style={styles.rowValue}>{zone}</Text>
              </View>
            </View>

            {/* Risk Level */}
            <View style={styles.row}>
              <View style={[styles.rowIcon, { backgroundColor: '#fef2f2' }]}>
                <Ionicons name="warning-outline" size={22} color="#ef4444" />
              </View>
              <View style={styles.rowText}>
                <Text style={styles.rowLabel}>RISK LEVEL</Text>
                <Text style={styles.rowDist}>{risk}</Text>
              </View>
            </View>

            {/* Assembly Point */}
            <View style={styles.row}>
              <View style={[styles.rowIcon, { backgroundColor: '#dbeafe' }]}>
                <Ionicons name="map-outline" size={22} color="#2563eb" />
              </View>
              <View style={styles.rowText}>
                <Text style={styles.rowLabel}>NEAREST ASSEMBLY POINT</Text>
                <TouchableOpacity style={styles.navBtn} onPress={openSafetyInfo} activeOpacity={0.85}>
                  <Ionicons name="navigate" size={16} color="#fff" />
                  <Text style={styles.navBtnText}>Open Navigation</Text>
                </TouchableOpacity>
              </View>
            </View>

            {/* Safety tips */}
            <View style={styles.tipsBox}>
              <Text style={styles.tipsTitle}>⚠️ SAFETY INSTRUCTIONS</Text>
              <Text style={styles.tipsText}>• DROP, COVER, and HOLD ON during shaking{'\n'}• Move away from buildings, trees and power lines{'\n'}• Do not use lifts — use stairs only{'\n'}• Watch for aftershocks after main quake</Text>
            </View>

            {/* Emergency options */}
            <Text style={styles.emergencyLabel}>EMERGENCY OPTIONS:</Text>
            <View style={styles.btnRow}>
              <TouchableOpacity style={[styles.sosBtn, sosSent && styles.btnDisabled]} onPress={handleSOS} activeOpacity={0.85} disabled={sosSent}>
                <Ionicons name={sosSent ? 'checkmark-circle' : 'call'} size={24} color="#fff" />
                <Text style={styles.btnLabel}>{sosSent ? 'SENT ✓' : 'SOS'}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.safeBtn, safe && styles.btnDisabled]} onPress={handleSafe} activeOpacity={0.85} disabled={safe}>
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

const styles = StyleSheet.create({
  overlay:   { flex: 1, backgroundColor: 'rgba(0,0,0,0.55)', justifyContent: 'flex-end' },
  sheet:     { backgroundColor: '#fff', borderTopLeftRadius: 28, borderTopRightRadius: 28, paddingBottom: 34, maxHeight: '92%' },
  closeBtn:  { position: 'absolute', top: 16, right: 18, zIndex: 10, padding: 4 },
  content:   { alignItems: 'center', paddingTop: 32, paddingBottom: 16, paddingHorizontal: 24 },
  iconWrap:  { marginBottom: 14 },
  iconEmoji: { fontSize: 52 },
  title: {
    fontFamily: 'PlusJakartaSans_700Bold', fontSize: 26,
    color: '#d97706', letterSpacing: 0.5, textAlign: 'center', marginBottom: 10,
  },
  subtitle: {
    fontFamily: 'PlusJakartaSans_400Regular', fontSize: 15,
    color: '#6b7280', textAlign: 'center', lineHeight: 22, marginBottom: 10,
  },
  action: {
    fontFamily: 'PlusJakartaSans_700Bold', fontSize: 18,
    color: '#d97706', textAlign: 'center', lineHeight: 26, marginBottom: 18,
  },
  divider:   { width: '100%', height: 1, backgroundColor: '#f1f5f9', marginBottom: 20 },
  row:       { flexDirection: 'row', alignItems: 'center', width: '100%', marginBottom: 16, gap: 14 },
  rowIcon:   { width: 56, height: 56, borderRadius: 16, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  rowText:   { flex: 1 },
  rowLabel:  { fontFamily: 'PlusJakartaSans_600SemiBold', fontSize: 11, color: '#9ca3af', letterSpacing: 0.8, marginBottom: 4 },
  rowValue:  { fontFamily: 'PlusJakartaSans_600SemiBold', fontSize: 15, color: '#111827', lineHeight: 22 },
  rowDist:   { fontFamily: 'PlusJakartaSans_700Bold', fontSize: 22, color: '#111827' },
  navBtn:    { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: '#2563eb', borderRadius: 12, paddingVertical: 11, paddingHorizontal: 20, gap: 8, alignSelf: 'flex-start', minWidth: 160 },
  navBtnText:{ fontFamily: 'PlusJakartaSans_700Bold', fontSize: 15, color: '#fff' },
  tipsBox:   { width: '100%', backgroundColor: '#fffbeb', borderRadius: 14, borderWidth: 1, borderColor: '#fcd34d', padding: 14, marginBottom: 20 },
  tipsTitle: { fontFamily: 'PlusJakartaSans_700Bold', fontSize: 12, color: '#d97706', letterSpacing: 0.5, marginBottom: 8 },
  tipsText:  { fontFamily: 'PlusJakartaSans_400Regular', fontSize: 13, color: '#92400e', lineHeight: 22 },
  emergencyLabel: { fontFamily: 'PlusJakartaSans_600SemiBold', fontSize: 11, color: '#9ca3af', letterSpacing: 1, alignSelf: 'flex-start', marginTop: 6, marginBottom: 14 },
  btnRow:    { flexDirection: 'row', gap: 14, width: '100%' },
  sosBtn:    { flex: 1, flexDirection: 'column', alignItems: 'center', justifyContent: 'center', backgroundColor: '#ef4444', borderRadius: 16, paddingVertical: 20, gap: 8, shadowColor: '#ef4444', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.3, shadowRadius: 10, elevation: 6 },
  safeBtn:   { flex: 1, flexDirection: 'column', alignItems: 'center', justifyContent: 'center', backgroundColor: '#16a34a', borderRadius: 16, paddingVertical: 20, gap: 8, shadowColor: '#16a34a', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.3, shadowRadius: 10, elevation: 6 },
  btnDisabled: { backgroundColor: '#9ca3af', shadowColor: '#9ca3af' },
  btnLabel:  { fontFamily: 'PlusJakartaSans_700Bold', fontSize: 15, color: '#fff', letterSpacing: 0.3 },
});
