import React, { useState, useRef, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator, Alert, Animated,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { verifyOTP, sendOTP } from '@/services/auth';
import { useAuth } from '@/context/AuthContext';

const OTP_LENGTH = 6;
const RESEND_SECONDS = 60;

export default function VerifyScreen() {
  const router = useRouter();
  const { phone } = useLocalSearchParams<{ phone: string }>();
  const { login } = useAuth();

  const [otp, setOtp] = useState(Array(OTP_LENGTH).fill(''));
  const [loading, setLoading] = useState(false);
  const [resendTimer, setResendTimer] = useState(RESEND_SECONDS);
  const [canResend, setCanResend] = useState(false);
  const inputs = useRef<(TextInput | null)[]>([]);

  // Entrance animation
  const cardAnim = useRef(new Animated.Value(0)).current;
  const shakeAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.spring(cardAnim, {
      toValue: 1, tension: 55, friction: 11, useNativeDriver: true,
    }).start();
  }, []);

  // Countdown timer
  useEffect(() => {
    if (resendTimer <= 0) { setCanResend(true); return; }
    const t = setTimeout(() => setResendTimer(p => p - 1), 1000);
    return () => clearTimeout(t);
  }, [resendTimer]);

  const triggerShake = () => {
    Animated.sequence([
      Animated.timing(shakeAnim, { toValue: 8,  duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: -8, duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: 6,  duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: -6, duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: 0,  duration: 60, useNativeDriver: true }),
    ]).start();
  };

  const handleChange = (val: string, idx: number) => {
    const digit = val.replace(/\D/g, '').slice(-1);
    const next = [...otp];
    next[idx] = digit;
    setOtp(next);
    if (digit && idx < OTP_LENGTH - 1) inputs.current[idx + 1]?.focus();
    if (!digit && idx > 0) inputs.current[idx - 1]?.focus();
  };

  const handleKeyPress = (e: any, idx: number) => {
    if (e.nativeEvent.key === 'Backspace' && !otp[idx] && idx > 0) {
      inputs.current[idx - 1]?.focus();
    }
  };

  const handleVerify = async () => {
    const code = otp.join('');
    if (code.length < OTP_LENGTH) {
      Alert.alert('Incomplete', 'Please enter all 6 digits.');
      triggerShake();
      return;
    }
    setLoading(true);
    try {
      const result = await verifyOTP(phone!, code);
      await login(result.user);
      if (!result.user.full_name) {
        router.replace({ pathname: '/(auth)/profile-setup', params: { phone: phone! } });
      } else {
        router.replace('/(tabs)');
      }
    } catch (e: any) {
      Alert.alert('Invalid OTP', e?.response?.data?.detail || 'The code is wrong or has expired. Try again.');
      setOtp(Array(OTP_LENGTH).fill(''));
      inputs.current[0]?.focus();
      triggerShake();
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    if (!canResend) return;
    try {
      await sendOTP(phone!);
      setOtp(Array(OTP_LENGTH).fill(''));
      setResendTimer(RESEND_SECONDS);
      setCanResend(false);
      inputs.current[0]?.focus();
      Alert.alert('OTP Sent', 'A new code has been sent to your number.');
    } catch {
      Alert.alert('Error', 'Could not resend OTP. Please try again.');
    }
  };

  const timerLabel = `${String(Math.floor(resendTimer / 60)).padStart(2, '0')}:${String(resendTimer % 60).padStart(2, '0')}`;
  const maskedPhone = phone ? phone.slice(0, -4).replace(/\d/g, '•') + phone.slice(-4) : '';
  const filled = otp.filter(Boolean).length;

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

      {/* Back button */}
      <TouchableOpacity style={styles.backBtn} onPress={() => router.back()} activeOpacity={0.7}>
        <View style={styles.backBtnInner}>
          <Ionicons name="arrow-back" size={20} color="#fff" />
        </View>
      </TouchableOpacity>

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={{ flex: 1 }}
      >
        <View style={styles.content}>
          {/* Top section */}
          <Animated.View style={[
            styles.topSection,
            {
              opacity: cardAnim,
              transform: [
                { translateY: cardAnim.interpolate({ inputRange: [0, 1], outputRange: [20, 0] }) },
              ],
            },
          ]}>
            <View style={styles.iconGlowWrap}>
              <View style={styles.iconGlow} />
              <View style={styles.iconCircle}>
                <Ionicons name="phone-portrait-outline" size={34} color="#fff" />
              </View>
            </View>
            <Text style={styles.title}>Verify Phone</Text>
            <Text style={styles.subtitle}>Enter the 6-digit code sent to</Text>
            <TouchableOpacity onPress={() => router.back()} activeOpacity={0.7}>
              <View style={styles.phonePill}>
                <Text style={styles.phoneLabel}>{maskedPhone}</Text>
                <Ionicons name="pencil" size={12} color="#60a5fa" style={{ marginLeft: 6 }} />
              </View>
            </TouchableOpacity>
          </Animated.View>

          {/* OTP Card */}
          <Animated.View style={[
            styles.card,
            {
              opacity: cardAnim,
              transform: [
                { translateY: cardAnim.interpolate({ inputRange: [0, 1], outputRange: [32, 0] }) },
                { translateX: shakeAnim },
              ],
            },
          ]}>
            <View style={styles.cardShine} />

            {/* OTP inputs */}
            <View style={styles.otpRow}>
              {otp.map((digit, i) => (
                <TextInput
                  key={i}
                  ref={el => { inputs.current[i] = el; }}
                  style={[
                    styles.otpBox,
                    digit ? styles.otpBoxFilled : null,
                    i === filled && styles.otpBoxActive,
                  ]}
                  value={digit}
                  onChangeText={val => handleChange(val, i)}
                  onKeyPress={e => handleKeyPress(e, i)}
                  keyboardType="number-pad"
                  maxLength={1}
                  selectTextOnFocus
                  textAlign="center"
                />
              ))}
            </View>

            {/* Progress bar */}
            <View style={styles.progressBar}>
              <Animated.View style={[styles.progressFill, { width: `${(filled / OTP_LENGTH) * 100}%` }]} />
            </View>

            {/* Timer / Resend */}
            <View style={styles.resendRow}>
              {!canResend ? (
                <View style={styles.timerChip}>
                  <Ionicons name="timer-outline" size={13} color="rgba(255,255,255,0.5)" />
                  <Text style={styles.timerText}>
                    Resend in <Text style={styles.timerCount}>{timerLabel}</Text>
                  </Text>
                </View>
              ) : (
                <TouchableOpacity onPress={handleResend} activeOpacity={0.7}>
                  <Text style={styles.resendActive}>
                    Didn't receive code?{' '}
                    <Text style={styles.resendLink}>Resend OTP</Text>
                  </Text>
                </TouchableOpacity>
              )}
            </View>

            {/* Verify button */}
            <TouchableOpacity
              activeOpacity={0.88}
              onPress={handleVerify}
              disabled={loading}
              style={styles.verifyBtnWrap}
            >
              <LinearGradient
                colors={loading ? ['#374151', '#374151'] : ['#2563eb', '#1d4ed8', '#1e40af']}
                style={styles.verifyBtn}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 0 }}
              >
                {loading ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <>
                    <Ionicons name="shield-checkmark-outline" size={18} color="#fff" style={{ marginRight: 8 }} />
                    <Text style={styles.verifyBtnText}>Verify & Continue</Text>
                  </>
                )}
              </LinearGradient>
            </TouchableOpacity>

            {/* Note */}
            <View style={styles.noteRow}>
              <Ionicons name="lock-closed" size={11} color="rgba(255,255,255,0.3)" />
              <Text style={styles.noteText}>OTP expires in 5 minutes</Text>
            </View>
          </Animated.View>
        </View>
      </KeyboardAvoidingView>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  bg: { flex: 1 },

  orb1: {
    position: 'absolute', top: -60, right: -80,
    width: 260, height: 260, borderRadius: 130,
    backgroundColor: 'rgba(37,99,235,0.15)',
  },
  orb2: {
    position: 'absolute', bottom: 80, left: -100,
    width: 300, height: 300, borderRadius: 150,
    backgroundColor: 'rgba(99,102,241,0.10)',
  },

  backBtn: {
    position: 'absolute', top: 56, left: 20, zIndex: 10,
  },
  backBtnInner: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.1)',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.15)',
    alignItems: 'center', justifyContent: 'center',
  },

  content: {
    flex: 1, paddingHorizontal: 24,
    paddingTop: 110, paddingBottom: 32,
    justifyContent: 'flex-start',
  },

  topSection: { alignItems: 'center', marginBottom: 32 },
  iconGlowWrap: { alignItems: 'center', justifyContent: 'center', marginBottom: 20 },
  iconGlow: {
    position: 'absolute',
    width: 100, height: 100, borderRadius: 50,
    backgroundColor: 'rgba(37,99,235,0.25)',
    transform: [{ scale: 1.5 }],
  },
  iconCircle: {
    width: 76, height: 76, borderRadius: 22,
    backgroundColor: 'rgba(37,99,235,0.85)',
    alignItems: 'center', justifyContent: 'center',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)',
    shadowColor: '#2563eb', shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.5, shadowRadius: 18, elevation: 10,
  },
  title: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 28, color: '#fff',
    marginBottom: 6, letterSpacing: -0.3,
  },
  subtitle: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14, color: 'rgba(255,255,255,0.5)',
    marginBottom: 12,
  },
  phonePill: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderRadius: 20, paddingHorizontal: 16, paddingVertical: 8,
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.12)',
  },
  phoneLabel: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 15, color: '#93c5fd',
    letterSpacing: 1,
  },

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

  otpRow: {
    flexDirection: 'row', justifyContent: 'space-between',
    marginBottom: 16,
  },
  otpBox: {
    width: 46, height: 58,
    borderRadius: 14,
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderWidth: 1.5, borderColor: 'rgba(255,255,255,0.12)',
    fontFamily: 'PlusJakartaSans_700Bold', fontSize: 24,
    color: '#fff',
  },
  otpBoxFilled: {
    borderColor: '#2563eb',
    backgroundColor: 'rgba(37,99,235,0.15)',
  },
  otpBoxActive: {
    borderColor: '#60a5fa',
    backgroundColor: 'rgba(96,165,250,0.08)',
  },

  progressBar: {
    height: 3, backgroundColor: 'rgba(255,255,255,0.08)',
    borderRadius: 2, marginBottom: 20, overflow: 'hidden',
  },
  progressFill: {
    height: 3, backgroundColor: '#2563eb', borderRadius: 2,
  },

  resendRow: { alignItems: 'center', marginBottom: 20 },
  timerChip: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderRadius: 20, paddingVertical: 8, paddingHorizontal: 14,
  },
  timerText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13, color: 'rgba(255,255,255,0.45)',
  },
  timerCount: {
    fontFamily: 'PlusJakartaSans_700Bold',
    color: '#60a5fa',
  },
  resendActive: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13, color: 'rgba(255,255,255,0.5)',
  },
  resendLink: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    color: '#60a5fa',
  },

  verifyBtnWrap: { borderRadius: 50, overflow: 'hidden', marginBottom: 16 },
  verifyBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: 17, borderRadius: 50,
  },
  verifyBtnText: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 16, color: '#fff', letterSpacing: 0.3,
  },
  noteRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5,
  },
  noteText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 11, color: 'rgba(255,255,255,0.3)',
  },
});
