import React, { useState, useRef, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator, Alert, Animated,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { updateProfile } from '@/services/auth';
import { useAuth } from '@/context/AuthContext';

const GENDERS = [
  { key: 'Male',   icon: 'male-outline'   as const },
  { key: 'Female', icon: 'female-outline' as const },
  { key: 'Other',  icon: 'people-outline' as const },
];

export default function ProfileSetupScreen() {
  const router = useRouter();
  const { phone } = useLocalSearchParams<{ phone: string }>();
  const { updateUser } = useAuth();

  const [fullName, setFullName] = useState('');
  const [age, setAge] = useState('');
  const [gender, setGender] = useState('');
  const [loading, setLoading] = useState(false);
  const [nameFocus, setNameFocus] = useState(false);
  const [ageFocus, setAgeFocus] = useState(false);

  const cardAnim = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.spring(cardAnim, { toValue: 1, tension: 55, friction: 11, useNativeDriver: true }).start();
  }, []);

  const handleComplete = async () => {
    if (!fullName.trim()) { Alert.alert('Required', 'Please enter your full name.'); return; }
    const ageNum = parseInt(age, 10);
    if (!age || isNaN(ageNum) || ageNum < 1 || ageNum > 120) {
      Alert.alert('Invalid Age', 'Please enter a valid age.'); return;
    }
    if (!gender) { Alert.alert('Required', 'Please select your gender.'); return; }
    setLoading(true);
    try {
      const res = await updateProfile(phone!, fullName.trim(), ageNum, gender);
      await updateUser({ full_name: res.user.full_name, age: res.user.age, gender: res.user.gender });
      router.replace('/(tabs)');
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Could not save profile. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const progress = [!!fullName.trim(), !!age && !isNaN(parseInt(age)), !!gender].filter(Boolean).length;

  return (
    <LinearGradient
      colors={['#0a0f1e', '#0d1b3e', '#0f2460', '#1a3a8a']}
      style={styles.bg}
      start={{ x: 0.1, y: 0 }} end={{ x: 0.9, y: 1 }}
    >
      <View style={styles.orb1} />
      <View style={styles.orb2} />

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>

          {/* Header */}
          <Animated.View style={[
            styles.topSection,
            {
              opacity: cardAnim,
              transform: [{ translateY: cardAnim.interpolate({ inputRange: [0, 1], outputRange: [20, 0] }) }],
            },
          ]}>
            <View style={styles.iconGlowWrap}>
              <View style={styles.iconGlow} />
              <View style={styles.iconCircle}>
                <Ionicons name="person-outline" size={34} color="#fff" />
              </View>
            </View>
            <Text style={styles.title}>Complete Your{'\n'}Profile</Text>
            <Text style={styles.subtitle}>
              Personal details help us provide faster rescue{'\n'}and medical assistance in emergencies.
            </Text>

            {/* Progress indicator */}
            <View style={styles.progressWrap}>
              {[0, 1, 2].map(i => (
                <View
                  key={i}
                  style={[styles.progressDot, i < progress && styles.progressDotFilled]}
                />
              ))}
              <Text style={styles.progressLabel}>{progress}/3 completed</Text>
            </View>
          </Animated.View>

          {/* Card */}
          <Animated.View style={[
            styles.card,
            {
              opacity: cardAnim,
              transform: [{ translateY: cardAnim.interpolate({ inputRange: [0, 1], outputRange: [32, 0] }) }],
            },
          ]}>
            <View style={styles.cardShine} />

            {/* Full Name */}
            <Text style={styles.label}>Full Name</Text>
            <View style={[styles.inputWrap, nameFocus && styles.inputWrapFocus]}>
              <Ionicons name="person-outline" size={18} color={nameFocus ? '#60a5fa' : 'rgba(255,255,255,0.3)'} style={{ marginRight: 10 }} />
              <TextInput
                style={styles.input}
                placeholder="e.g. Ramesh Kumar"
                placeholderTextColor="rgba(255,255,255,0.25)"
                value={fullName}
                onChangeText={setFullName}
                onFocus={() => setNameFocus(true)}
                onBlur={() => setNameFocus(false)}
                autoCapitalize="words"
              />
            </View>

            {/* Age */}
            <Text style={styles.label}>Age</Text>
            <View style={[styles.inputWrap, ageFocus && styles.inputWrapFocus]}>
              <Ionicons name="calendar-outline" size={18} color={ageFocus ? '#60a5fa' : 'rgba(255,255,255,0.3)'} style={{ marginRight: 10 }} />
              <TextInput
                style={styles.input}
                placeholder="Your age"
                placeholderTextColor="rgba(255,255,255,0.25)"
                value={age}
                onChangeText={setAge}
                onFocus={() => setAgeFocus(true)}
                onBlur={() => setAgeFocus(false)}
                keyboardType="number-pad"
                maxLength={3}
              />
            </View>

            {/* Gender */}
            <Text style={styles.label}>Gender</Text>
            <View style={styles.genderRow}>
              {GENDERS.map(g => (
                <TouchableOpacity
                  key={g.key}
                  style={[styles.genderBtn, gender === g.key && styles.genderBtnActive]}
                  onPress={() => setGender(g.key)}
                  activeOpacity={0.8}
                >
                  <Ionicons name={g.icon} size={20} color={gender === g.key ? '#60a5fa' : 'rgba(255,255,255,0.5)'} />
                  <Text style={[styles.genderText, gender === g.key && styles.genderTextActive]}>{g.key}</Text>
                </TouchableOpacity>
              ))}
            </View>

            {/* Complete button */}
            <TouchableOpacity
              activeOpacity={0.88}
              onPress={handleComplete}
              disabled={loading}
              style={styles.completeBtnWrap}
            >
              <LinearGradient
                colors={loading ? ['#374151', '#374151'] : ['#2563eb', '#1d4ed8', '#1e40af']}
                style={styles.completeBtn}
                start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }}
              >
                {loading ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <>
                    <Ionicons name="checkmark-circle-outline" size={18} color="#fff" style={{ marginRight: 8 }} />
                    <Text style={styles.completeBtnText}>Complete Setup</Text>
                  </>
                )}
              </LinearGradient>
            </TouchableOpacity>

            <TouchableOpacity onPress={() => router.replace('/(tabs)')} activeOpacity={0.7} style={styles.skipBtn}>
              <Text style={styles.skipText}>Skip for now</Text>
            </TouchableOpacity>

            {/* Privacy note */}
            <View style={styles.privacyRow}>
              <Ionicons name="lock-closed" size={12} color="rgba(255,255,255,0.3)" />
              <Text style={styles.privacyText}>Your data is encrypted and used only for emergency services.</Text>
            </View>
          </Animated.View>

        </ScrollView>
      </KeyboardAvoidingView>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  bg: { flex: 1 },
  scroll: { flexGrow: 1, paddingHorizontal: 24, paddingTop: 72, paddingBottom: 48 },

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

  topSection: { alignItems: 'center', marginBottom: 32 },
  iconGlowWrap: { alignItems: 'center', justifyContent: 'center', marginBottom: 18 },
  iconGlow: {
    position: 'absolute', width: 100, height: 100, borderRadius: 50,
    backgroundColor: 'rgba(37,99,235,0.25)', transform: [{ scale: 1.5 }],
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
    textAlign: 'center', marginBottom: 10,
    lineHeight: 36, letterSpacing: -0.3,
  },
  subtitle: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14, color: 'rgba(255,255,255,0.5)',
    textAlign: 'center', lineHeight: 20, marginBottom: 16,
  },

  progressWrap: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  progressDot: {
    width: 8, height: 8, borderRadius: 4,
    backgroundColor: 'rgba(255,255,255,0.15)',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)',
  },
  progressDotFilled: { backgroundColor: '#2563eb', borderColor: '#2563eb' },
  progressLabel: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 12, color: 'rgba(255,255,255,0.4)', marginLeft: 4,
  },

  card: {
    backgroundColor: 'rgba(255,255,255,0.07)',
    borderRadius: 28, borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
    padding: 28, overflow: 'hidden',
  },
  cardShine: {
    position: 'absolute', top: 0, left: 0, right: 0, height: 1,
    backgroundColor: 'rgba(255,255,255,0.15)',
  },

  label: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 13, color: 'rgba(255,255,255,0.7)',
    marginBottom: 8, letterSpacing: 0.3,
  },
  inputWrap: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderRadius: 14, paddingHorizontal: 14,
    borderWidth: 1.5, borderColor: 'rgba(255,255,255,0.1)',
    marginBottom: 20,
  },
  inputWrapFocus: { borderColor: '#2563eb', backgroundColor: 'rgba(37,99,235,0.08)' },
  input: {
    flex: 1, paddingVertical: 14,
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 15, color: '#fff',
  },

  genderRow: { flexDirection: 'row', gap: 10, marginBottom: 24 },
  genderBtn: {
    flex: 1, alignItems: 'center', paddingVertical: 14,
    borderRadius: 14, borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,0.1)',
    backgroundColor: 'rgba(255,255,255,0.05)',
  },
  genderBtnActive: {
    borderColor: '#2563eb',
    backgroundColor: 'rgba(37,99,235,0.15)',
  },
  genderText: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 12, color: 'rgba(255,255,255,0.45)',
    marginTop: 6,
  },
  genderTextActive: {
    color: '#60a5fa',
    fontFamily: 'PlusJakartaSans_600SemiBold',
  },

  completeBtnWrap: { borderRadius: 50, overflow: 'hidden', marginBottom: 14 },
  completeBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: 17, borderRadius: 50,
  },
  completeBtnText: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 16, color: '#fff', letterSpacing: 0.3,
  },

  skipBtn: { alignItems: 'center', paddingVertical: 10, marginBottom: 20 },
  skipText: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 14, color: 'rgba(96,165,250,0.7)',
  },

  privacyRow: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 6,
  },
  privacyText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 11, color: 'rgba(255,255,255,0.3)',
    flex: 1, lineHeight: 16,
  },
});
