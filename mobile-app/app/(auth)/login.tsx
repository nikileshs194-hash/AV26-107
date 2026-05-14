import React, { useState, useRef, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator,
  Alert, Animated, Dimensions,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { sendOTP } from '@/services/auth';

const { width: SW } = Dimensions.get('window');

const COUNTRY_CODES = [
  { label: '+91',  value: '+91',  flag: '🇮🇳', name: 'India' },
  { label: '+1',   value: '+1',   flag: '🇺🇸', name: 'USA' },
  { label: '+44',  value: '+44',  flag: '🇬🇧', name: 'UK' },
  { label: '+61',  value: '+61',  flag: '🇦🇺', name: 'Australia' },
  { label: '+971', value: '+971', flag: '🇦🇪', name: 'UAE' },
];

export default function LoginScreen() {
  const router = useRouter();
  const [phone, setPhone] = useState('');
  const [countryCode, setCountryCode] = useState('+91');
  const [showCodes, setShowCodes] = useState(false);
  const [loading, setLoading] = useState(false);
  const [phoneFocused, setPhoneFocused] = useState(false);

  // Entrance animations
  const logoAnim   = useRef(new Animated.Value(0)).current;
  const cardAnim   = useRef(new Animated.Value(0)).current;
  const glowAnim   = useRef(new Animated.Value(0.4)).current;
  const phoneBorder = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    // Staggered entrance
    Animated.stagger(120, [
      Animated.spring(logoAnim, { toValue: 1, tension: 60, friction: 10, useNativeDriver: true }),
      Animated.spring(cardAnim, { toValue: 1, tension: 55, friction: 11, useNativeDriver: true }),
    ]).start();

    // Pulsing logo glow
    Animated.loop(
      Animated.sequence([
        Animated.timing(glowAnim, { toValue: 1,   duration: 1800, useNativeDriver: true }),
        Animated.timing(glowAnim, { toValue: 0.4, duration: 1800, useNativeDriver: true }),
      ]),
    ).start();
  }, []);

  // Focus border animation
  useEffect(() => {
    Animated.timing(phoneBorder, {
      toValue: phoneFocused ? 1 : 0,
      duration: 200,
      useNativeDriver: false,
    }).start();
  }, [phoneFocused]);

  const handleGetOTP = async () => {
    const digits = phone.replace(/\D/g, '');
    if (digits.length < 10) {
      Alert.alert('Invalid Number', 'Please enter a valid 10-digit phone number.');
      return;
    }
    const fullPhone = `${countryCode}${digits}`;
    setLoading(true);
    try {
      await sendOTP(fullPhone, countryCode);
      router.push({ pathname: '/(auth)/verify', params: { phone: fullPhone } });
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Could not send OTP. Check backend is running.');
    } finally {
      setLoading(false);
    }
  };

  const activeBorderColor = phoneBorder.interpolate({
    inputRange: [0, 1],
    outputRange: ['rgba(255,255,255,0.15)', 'rgba(255,255,255,0.7)'],
  });

  const selectedCode = COUNTRY_CODES.find(c => c.value === countryCode);

  return (
    <LinearGradient
      colors={['#0a0f1e', '#0d1b3e', '#0f2460', '#1a3a8a']}
      style={styles.bg}
      start={{ x: 0.1, y: 0 }}
      end={{ x: 0.9, y: 1 }}
    >
      {/* Background orbs */}
      <View style={styles.orb1} />
      <View style={styles.orb2} />

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* ── Logo ── */}
          <Animated.View style={[
            styles.logoWrap,
            {
              opacity: logoAnim,
              transform: [{ translateY: logoAnim.interpolate({ inputRange: [0, 1], outputRange: [24, 0] }) }],
            },
          ]}>
            <View style={styles.logoGlowWrap}>
              <Animated.View style={[styles.logoGlow, { opacity: glowAnim }]} />
              <View style={styles.logoBox}>
                <Ionicons name="shield-half-outline" size={46} color="#fff" />
              </View>
            </View>
            <Text style={styles.appName}>JeevanSetu</Text>
            <Text style={styles.tagline}>Before Disaster Strikes.{'\n'}JeevanSetu Acts.</Text>
          </Animated.View>

          {/* ── Card ── */}
          <Animated.View style={[
            styles.cardWrap,
            {
              opacity: cardAnim,
              transform: [{ translateY: cardAnim.interpolate({ inputRange: [0, 1], outputRange: [32, 0] }) }],
            },
          ]}>
            <View style={styles.card}>
              {/* Glass shine */}
              <View style={styles.cardShine} />

              <Text style={styles.cardTitle}>Welcome back</Text>
              <Text style={styles.cardSub}>Enter your phone number to continue</Text>

              {/* Input row */}
              <Animated.View style={[styles.inputRow, { borderColor: activeBorderColor }]}>
                {/* Country code picker */}
                <TouchableOpacity
                  style={styles.codeBox}
                  onPress={() => setShowCodes(!showCodes)}
                  activeOpacity={0.8}
                >
                  <Text style={styles.codeFlag}>{selectedCode?.flag}</Text>
                  <Text style={styles.codeText}>{countryCode}</Text>
                  <Ionicons
                    name={showCodes ? 'chevron-up' : 'chevron-down'}
                    size={13}
                    color="rgba(255,255,255,0.6)"
                  />
                </TouchableOpacity>

                <View style={styles.divider} />

                <TextInput
                  style={styles.phoneInput}
                  placeholder="Phone number"
                  placeholderTextColor="rgba(255,255,255,0.35)"
                  keyboardType="phone-pad"
                  value={phone}
                  onChangeText={setPhone}
                  onFocus={() => setPhoneFocused(true)}
                  onBlur={() => setPhoneFocused(false)}
                  maxLength={10}
                />
              </Animated.View>

              {/* Country code dropdown */}
              {showCodes && (
                <View style={styles.dropdown}>
                  {COUNTRY_CODES.map(c => (
                    <TouchableOpacity
                      key={c.value}
                      style={[styles.dropItem, c.value === countryCode && styles.dropItemActive]}
                      onPress={() => { setCountryCode(c.value); setShowCodes(false); }}
                      activeOpacity={0.7}
                    >
                      <Text style={styles.dropFlag}>{c.flag}</Text>
                      <Text style={styles.dropName}>{c.name}</Text>
                      <Text style={styles.dropCode}>{c.label}</Text>
                      {c.value === countryCode && (
                        <Ionicons name="checkmark-circle" size={16} color="#60a5fa" />
                      )}
                    </TouchableOpacity>
                  ))}
                </View>
              )}

              {/* CTA */}
              <TouchableOpacity
                activeOpacity={0.88}
                onPress={handleGetOTP}
                disabled={loading}
                style={styles.otpBtnWrap}
              >
                <LinearGradient
                  colors={loading ? ['#374151', '#374151'] : ['#2563eb', '#1d4ed8', '#1e40af']}
                  style={styles.otpBtn}
                  start={{ x: 0, y: 0 }}
                  end={{ x: 1, y: 0 }}
                >
                  {loading ? (
                    <ActivityIndicator color="#fff" />
                  ) : (
                    <>
                      <Text style={styles.otpBtnText}>Get OTP</Text>
                      <Ionicons name="arrow-forward" size={18} color="#fff" style={{ marginLeft: 8 }} />
                    </>
                  )}
                </LinearGradient>
              </TouchableOpacity>

              {/* Security note */}
              <View style={styles.securityRow}>
                <Ionicons name="lock-closed" size={12} color="rgba(255,255,255,0.4)" />
                <Text style={styles.securityText}>256-bit encrypted · OTP expires in 5 min</Text>
              </View>
            </View>
          </Animated.View>

          {/* ── Trust badges ── */}
          <View style={styles.badges}>
            {[
              { icon: 'shield-checkmark-outline', label: 'Secure Login' },
              { icon: 'globe-outline',            label: 'Used across India' },
              { icon: 'pulse-outline',            label: 'Live Flood AI' },
            ].map((b, i) => (
              <View key={i} style={styles.badge}>
                <Ionicons name={b.icon as any} size={14} color="rgba(255,255,255,0.5)" />
                <Text style={styles.badgeText}>{b.label}</Text>
              </View>
            ))}
          </View>

          {/* Footer */}
          <View style={styles.footer}>
            <TouchableOpacity><Text style={styles.footerLink}>Terms of Service</Text></TouchableOpacity>
            <Text style={styles.footerDot}>·</Text>
            <TouchableOpacity><Text style={styles.footerLink}>Privacy Policy</Text></TouchableOpacity>
          </View>
          <Text style={styles.copyright}>© 2025 JeevanSetu Disaster Response</Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  bg: { flex: 1 },
  scroll: { flexGrow: 1, paddingHorizontal: 24, paddingTop: 80, paddingBottom: 48 },

  // Background orbs
  orb1: {
    position: 'absolute', top: -80, right: -80,
    width: 280, height: 280, borderRadius: 140,
    backgroundColor: 'rgba(37,99,235,0.18)',
  },
  orb2: {
    position: 'absolute', bottom: 120, left: -100,
    width: 320, height: 320, borderRadius: 160,
    backgroundColor: 'rgba(99,102,241,0.12)',
  },

  // Logo section
  logoWrap: { alignItems: 'center', marginBottom: 44 },
  logoGlowWrap: { alignItems: 'center', justifyContent: 'center', marginBottom: 18 },
  logoGlow: {
    position: 'absolute',
    width: 120, height: 120, borderRadius: 60,
    backgroundColor: '#2563eb',
    transform: [{ scale: 1.4 }],
  },
  logoBox: {
    width: 88, height: 88, borderRadius: 24,
    backgroundColor: 'rgba(37,99,235,0.9)',
    alignItems: 'center', justifyContent: 'center',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)',
    shadowColor: '#2563eb', shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.6, shadowRadius: 24, elevation: 14,
  },
  appName: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 34, color: '#fff',
    letterSpacing: -0.5, marginBottom: 10,
  },
  tagline: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 15, color: 'rgba(255,255,255,0.55)',
    textAlign: 'center', lineHeight: 22,
  },

  // Card
  cardWrap: { marginBottom: 28 },
  card: {
    backgroundColor: 'rgba(255,255,255,0.07)',
    borderRadius: 28,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
    padding: 28,
    overflow: 'hidden',
  },
  cardShine: {
    position: 'absolute', top: 0, left: 0, right: 0, height: 1,
    backgroundColor: 'rgba(255,255,255,0.15)',
  },
  cardTitle: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 24, color: '#fff', marginBottom: 6,
  },
  cardSub: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14, color: 'rgba(255,255,255,0.5)', marginBottom: 24,
  },

  // Phone input row
  inputRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderRadius: 16, borderWidth: 1.5,
    marginBottom: 20, overflow: 'hidden',
  },
  codeBox: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    paddingHorizontal: 14, paddingVertical: 16,
  },
  codeFlag: { fontSize: 18 },
  codeText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 15, color: '#fff',
  },
  divider: {
    width: 1, height: 24,
    backgroundColor: 'rgba(255,255,255,0.12)',
    marginRight: 4,
  },
  phoneInput: {
    flex: 1,
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 16, color: '#fff',
    paddingHorizontal: 12, paddingVertical: 16,
  },

  // Dropdown
  dropdown: {
    backgroundColor: 'rgba(15,24,64,0.98)',
    borderRadius: 16, borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
    marginBottom: 16, overflow: 'hidden',
  },
  dropItem: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingVertical: 13, paddingHorizontal: 16,
    borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.06)',
  },
  dropItemActive: { backgroundColor: 'rgba(37,99,235,0.15)' },
  dropFlag: { fontSize: 20 },
  dropName: {
    flex: 1,
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 14, color: 'rgba(255,255,255,0.85)',
  },
  dropCode: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14, color: 'rgba(255,255,255,0.5)',
    marginRight: 4,
  },

  // CTA
  otpBtnWrap: { borderRadius: 50, overflow: 'hidden', marginBottom: 16 },
  otpBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: 17, borderRadius: 50,
  },
  otpBtnText: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 16, color: '#fff', letterSpacing: 0.3,
  },
  securityRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5,
  },
  securityText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 11, color: 'rgba(255,255,255,0.35)',
  },

  // Trust badges
  badges: {
    flexDirection: 'row', justifyContent: 'center',
    flexWrap: 'wrap', gap: 16, marginBottom: 32,
  },
  badge: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  badgeText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 12, color: 'rgba(255,255,255,0.4)',
  },

  // Footer
  footer: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, marginBottom: 8 },
  footerLink: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 13, color: 'rgba(96,165,250,0.8)',
  },
  footerDot: { color: 'rgba(255,255,255,0.2)', fontSize: 16 },
  copyright: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 11, color: 'rgba(255,255,255,0.2)',
    textAlign: 'center',
  },
});
