import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  StyleSheet, View, Text, ScrollView, TextInput, TouchableOpacity,
  ActivityIndicator, KeyboardAvoidingView, Platform, Animated, Modal,
  Dimensions, Alert,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Colors } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';
import Header from '@/components/Header';
import { Feather, Ionicons } from '@expo/vector-icons';

import useLocation from '@/hooks/useLocation';
import { sendChatMessage, transcribeAudio } from '@/services/api';

// Conditionally import expo-av only on native
let Audio: any = null;
if (Platform.OS !== 'web') {
  try { Audio = require('expo-av').Audio; } catch { /* expo-av not available */ }
}

function getRecordingOptions(Av: any) {
  return {
    android: {
      extension: '.m4a',
      outputFormat: Av.AndroidOutputFormat?.MPEG_4 ?? 2,
      audioEncoder: Av.AndroidAudioEncoder?.AAC ?? 3,
      sampleRate: 44100, numberOfChannels: 1, bitRate: 128000,
    },
    ios: {
      extension: '.m4a',
      outputFormat: Av.IOSOutputFormat?.MPEG4AAC ?? 'aac ',
      audioQuality: Av.IOSAudioQuality?.HIGH ?? 96,
      sampleRate: 44100, numberOfChannels: 1, bitRate: 128000,
      linearPCMBitDepth: 16, linearPCMIsBigEndian: false, linearPCMIsFloat: false,
    },
    web: { mimeType: 'audio/webm', bitsPerSecond: 128000 },
  };
}

const INITIAL_SUGGESTIONS = [
  { text: 'Will it rain this weekend?', icon: 'rainy-outline' },
  { text: 'Is it safe to travel tomorrow?', icon: 'car-outline' },
  { text: "What's the flood risk near me?", icon: 'water-outline' },
  { text: 'Best time for outdoor activities?', icon: 'sunny-outline' },
];

interface Message {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  time: string;
  showFeedback?: boolean;
}

// ─── Typing indicator (3 animated dots) ──────────────────────────────────────
function TypingDots({ color }: { color: string }) {
  const dots = [
    useRef(new Animated.Value(0)).current,
    useRef(new Animated.Value(0)).current,
    useRef(new Animated.Value(0)).current,
  ];

  useEffect(() => {
    const animations = dots.map((dot, i) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(i * 160),
          Animated.timing(dot, { toValue: 1, duration: 380, useNativeDriver: true }),
          Animated.timing(dot, { toValue: 0, duration: 380, useNativeDriver: true }),
          Animated.delay(480 - i * 160),
        ]),
      ),
    );
    animations.forEach(a => a.start());
    return () => animations.forEach(a => a.stop());
  }, []);

  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 6, paddingHorizontal: 4 }}>
      {dots.map((dot, i) => (
        <Animated.View
          key={i}
          style={{
            width: 7, height: 7, borderRadius: 4,
            backgroundColor: color,
            opacity: dot,
            transform: [{ translateY: dot.interpolate({ inputRange: [0, 1], outputRange: [0, -4] }) }],
          }}
        />
      ))}
    </View>
  );
}

// ─── Waveform bars ────────────────────────────────────────────────────────────
const BAR_COUNT = 7;
const BAR_HEIGHTS = [18, 36, 28, 48, 22, 40, 24];
const BAR_DELAYS  = [0, 120, 240, 60, 180, 300, 90];

function WaveformBars({ active, color }: { active: boolean; color: string }) {
  const anims = useRef(
    Array.from({ length: BAR_COUNT }, () => new Animated.Value(6)),
  ).current;

  useEffect(() => {
    if (active) {
      const loops = anims.map((anim, i) =>
        Animated.loop(
          Animated.sequence([
            Animated.delay(BAR_DELAYS[i]),
            Animated.timing(anim, { toValue: BAR_HEIGHTS[i], duration: 350 + i * 40, useNativeDriver: false }),
            Animated.timing(anim, { toValue: 6, duration: 350 + i * 40, useNativeDriver: false }),
          ]),
        ),
      );
      loops.forEach(l => l.start());
      return () => loops.forEach(l => l.stop());
    } else {
      anims.forEach(a => Animated.spring(a, { toValue: 6, useNativeDriver: false }).start());
    }
  }, [active]);

  return (
    <View style={styles.waveRow}>
      {anims.map((anim, i) => (
        <Animated.View
          key={i}
          style={[styles.waveBar, { height: anim, backgroundColor: color, opacity: active ? 1 : 0.35 }]}
        />
      ))}
    </View>
  );
}

// ─── Voice overlay ────────────────────────────────────────────────────────────
interface VoiceOverlayProps {
  visible: boolean; isListening: boolean; isProcessing: boolean;
  interimText: string; onStop: () => void; onCancel: () => void;
  primaryColor: string;
}

function VoiceOverlay({ visible, isListening, isProcessing, interimText, onStop, onCancel, primaryColor }: VoiceOverlayProps) {
  const slideAnim = useRef(new Animated.Value(300)).current;
  const stopScale = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    Animated.spring(slideAnim, { toValue: visible ? 0 : 300, useNativeDriver: true, tension: 80, friction: 12 }).start();
  }, [visible]);

  useEffect(() => {
    if (isListening) {
      Animated.loop(Animated.sequence([
        Animated.timing(stopScale, { toValue: 1.12, duration: 700, useNativeDriver: true }),
        Animated.timing(stopScale, { toValue: 1.00, duration: 700, useNativeDriver: true }),
      ])).start();
    } else {
      stopScale.setValue(1);
    }
  }, [isListening]);

  if (!visible) return null;

  return (
    <Modal transparent animationType="none" visible={visible} onRequestClose={onCancel}>
      <View style={styles.overlayBackdrop}>
        <Animated.View style={[styles.overlaySheet, { transform: [{ translateY: slideAnim }] }]}>
          <View style={styles.overlayHandle} />
          <Text style={[styles.overlayStatus, { color: primaryColor }]}>
            {isProcessing ? 'Processing…' : 'Listening…'}
          </Text>
          <View style={styles.overlayWaveArea}>
            {isProcessing
              ? <ActivityIndicator size="large" color={primaryColor} />
              : <WaveformBars active={isListening} color={primaryColor} />}
          </View>
          {interimText ? (
            <Text style={styles.interimText} numberOfLines={3}>"{interimText}"</Text>
          ) : (
            <Text style={styles.overlayHint}>
              {isProcessing ? 'Hang tight…' : 'Speak now · tap stop when done'}
            </Text>
          )}
          <View style={styles.overlayBtns}>
            <TouchableOpacity style={styles.cancelBtn} onPress={onCancel}>
              <Ionicons name="close" size={22} color="rgba(255,255,255,0.6)" />
            </TouchableOpacity>
            <Animated.View style={{ transform: [{ scale: stopScale }] }}>
              <TouchableOpacity
                style={[styles.stopBtn, { backgroundColor: primaryColor }]}
                onPress={onStop}
                disabled={isProcessing}
                activeOpacity={0.8}
              >
                {isProcessing
                  ? <ActivityIndicator size="small" color="#fff" />
                  : <Ionicons name="stop" size={28} color="#fff" />}
              </TouchableOpacity>
            </Animated.View>
            <View style={styles.cancelBtn} />
          </View>
        </Animated.View>
      </View>
    </Modal>
  );
}

// ─── Markdown-lite renderer ───────────────────────────────────────────────────
function renderText(text: string, isDark: boolean) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**'))
      return <Text key={i} style={{ fontFamily: 'PlusJakartaSans_700Bold' }}>{part.slice(2, -2)}</Text>;
    if (part.startsWith('*') && part.endsWith('*'))
      return <Text key={i} style={{ fontStyle: 'italic', color: isDark ? '#93c5fd' : '#1d4ed8' }}>{part.slice(1, -1)}</Text>;
    return <Text key={i}>{part}</Text>;
  });
}

// ─── Web Speech hook ──────────────────────────────────────────────────────────
function useWebSpeech(onFinal: (t: string) => void, onInterim: (t: string) => void) {
  const recogRef = useRef<any>(null);
  const [listening, setListening] = useState(false);

  const start = useCallback(() => {
    if (typeof window === 'undefined') return;
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) { alert('Speech recognition not supported in this browser.'); return; }
    const r = new SR();
    r.lang = 'en-IN'; r.continuous = true; r.interimResults = true;
    r.onresult = (e: any) => {
      let interim = '', final = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) final += t; else interim += t;
      }
      if (interim) onInterim(interim);
      if (final)   onFinal(final);
    };
    r.onerror = () => setListening(false);
    r.onend   = () => setListening(false);
    recogRef.current = r;
    r.start();
    setListening(true);
  }, [onFinal, onInterim]);

  const stop = useCallback(() => { recogRef.current?.stop(); setListening(false); }, []);
  return { listening, start, stop };
}

// ─── Main Screen ──────────────────────────────────────────────────────────────
export default function AIScreen() {
  const colorScheme  = useColorScheme() ?? 'light';
  const theme        = Colors[colorScheme];
  const isDark       = colorScheme === 'dark';
  const { location } = useLocation();

  const [messages, setMessages]         = useState<Message[]>([]);
  const [suggestions, setSuggestions]   = useState(INITIAL_SUGGESTIONS.map(s => s.text));
  const [input, setInput]               = useState('');
  const [isLoading, setIsLoading]       = useState(false);
  const [voiceOpen, setVoiceOpen]       = useState(false);
  const [isRecording, setIsRecording]   = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [interimText, setInterimText]   = useState('');
  const recordingRef = useRef<any>(null);
  const scrollRef    = useRef<ScrollView>(null);
  const now = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  const send = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;
    setInput('');
    const userMsg: Message = { id: Date.now().toString(), role: 'user', text: trimmed, time: now() };
    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
    try {
      const history = messages.slice(-10).map(m => ({
        role: m.role === 'user' ? 'user' : 'assistant', content: m.text,
      }));
      const result = await sendChatMessage(trimmed, history, location?.lat, location?.lon);
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(), role: 'assistant',
        text: result.response, time: now(), showFeedback: true,
      }]);
      if (result.suggestions?.length) setSuggestions(result.suggestions);
    } catch {
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(), role: 'assistant',
        text: "Sorry, I couldn't connect to the AI service. Please check the backend is running.",
        time: now(),
      }]);
    } finally {
      setIsLoading(false);
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
    }
  }, [messages, isLoading, location]);

  const handleWebFinal   = useCallback((t: string) => { setInput(p => (p + ' ' + t).trim()); setInterimText(''); }, []);
  const handleWebInterim = useCallback((t: string) => setInterimText(t), []);
  const webSpeech        = useWebSpeech(handleWebFinal, handleWebInterim);

  const openVoice = useCallback(async () => {
    setInterimText('');
    if (Platform.OS === 'web') { setVoiceOpen(true); webSpeech.start(); return; }
    if (!Audio) { Alert.alert('Not available', 'Audio recording requires a development build.'); return; }
    try {
      const perm = await Audio.requestPermissionsAsync();
      if (!perm.granted) { Alert.alert('Permission denied', 'Enable microphone access in Settings.'); return; }
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true, staysActiveInBackground: false });
      const { recording } = await Audio.Recording.createAsync(getRecordingOptions(Audio));
      recordingRef.current = recording;
      setIsRecording(true); setVoiceOpen(true);
    } catch (e: any) {
      try { await Audio.setAudioModeAsync({ allowsRecordingIOS: false, playsInSilentModeIOS: true }); } catch {}
      Alert.alert('Could not start recording', e?.message ?? 'Check microphone permissions.');
    }
  }, [webSpeech]);

  const stopVoice = useCallback(async () => {
    if (Platform.OS === 'web') {
      webSpeech.stop(); setInterimText(''); setVoiceOpen(false); return;
    }
    if (!recordingRef.current) { setVoiceOpen(false); return; }
    setIsRecording(false); setIsTranscribing(true);
    try {
      await recordingRef.current.stopAndUnloadAsync();
      const uri = recordingRef.current.getURI();
      recordingRef.current = null;
      if (Audio) { try { await Audio.setAudioModeAsync({ allowsRecordingIOS: false, playsInSilentModeIOS: true }); } catch {} }
      if (uri) {
        const text = await transcribeAudio(uri);
        if (text.trim()) setInput(text.trim());
        else Alert.alert('Nothing heard', 'No speech detected. Please try again.');
      }
    } catch (e: any) {
      Alert.alert('Transcription failed', e?.message ?? 'Could not convert speech to text.');
    } finally {
      setIsTranscribing(false); setVoiceOpen(false);
    }
  }, [webSpeech]);

  const cancelVoice = useCallback(async () => {
    if (Platform.OS === 'web') { webSpeech.stop(); }
    else if (recordingRef.current) {
      try { await recordingRef.current.stopAndUnloadAsync(); } catch {}
      recordingRef.current = null;
      if (Audio) { try { await Audio.setAudioModeAsync({ allowsRecordingIOS: false, playsInSilentModeIOS: true }); } catch {} }
    }
    setIsRecording(false); setIsTranscribing(false); setInterimText(''); setVoiceOpen(false);
  }, [webSpeech]);

  const micActive      = Platform.OS === 'web' ? webSpeech.listening : isRecording;
  const showSuggestions = messages.length === 0;
  const canSend        = input.trim().length > 0 && !isLoading;

  return (
    <View style={[styles.container, { backgroundColor: theme.background }]}>
      <VoiceOverlay
        visible={voiceOpen} isListening={micActive} isProcessing={isTranscribing}
        interimText={interimText} onStop={stopVoice} onCancel={cancelVoice}
        primaryColor={theme.primary}
      />

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={80}
      >
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={styles.contentContainer}
          showsVerticalScrollIndicator={false}
        >
          <Header city={location?.city} />

          {/* ── Hero section ── */}
          <View style={styles.heroSection}>
            <LinearGradient
              colors={['#1e3a8a', '#2563eb', '#3b82f6']}
              style={styles.heroGradient}
              start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
            >
              <View style={styles.heroIconBg}>
                <Ionicons name="hardware-chip-outline" size={36} color="#fff" />
              </View>
              <Text style={styles.heroTitle}>JeevanSetu AI</Text>
              <Text style={styles.heroSubtitle}>
                Your intelligent weather &amp; flood-safety assistant. Ask me anything.
              </Text>

              {/* Capability chips */}
              <View style={styles.heroChips}>
                {['Weather Forecasts', 'Flood Risk', 'Safety Tips'].map((c, i) => (
                  <View key={i} style={styles.heroChip}>
                    <Text style={styles.heroChipText}>{c}</Text>
                  </View>
                ))}
              </View>
            </LinearGradient>
          </View>

          {/* ── Suggestions (empty state) ── */}
          {showSuggestions && (
            <View style={styles.suggestionsSection}>
              <Text style={[styles.sectionLabel, { color: theme.icon }]}>SUGGESTED QUESTIONS</Text>
              <View style={styles.suggestionsGrid}>
                {INITIAL_SUGGESTIONS.map((q, idx) => (
                  <TouchableOpacity
                    key={idx}
                    style={[styles.suggestionCard, { backgroundColor: theme.card, borderColor: theme.border }]}
                    activeOpacity={0.7}
                    onPress={() => send(q.text)}
                  >
                    <View style={[styles.suggestionIconBox, { backgroundColor: theme.background }]}>
                      <Ionicons name={q.icon as any} size={18} color={theme.primary} />
                    </View>
                    <Text style={[styles.suggestionText, { color: theme.text }]}>{q.text}</Text>
                    <Ionicons name="arrow-forward-circle-outline" size={18} color={theme.icon} />
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          )}

          {/* ── Chat messages ── */}
          {messages.length > 0 && (
            <View style={styles.chatArea}>
              {messages.map((msg, idx) =>
                msg.role === 'user' ? (
                  <View key={msg.id} style={styles.userMsgWrap}>
                    <LinearGradient
                      colors={['#2563eb', '#1d4ed8']}
                      style={styles.userBubble}
                      start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
                    >
                      <Text style={styles.userText}>{msg.text}</Text>
                    </LinearGradient>
                    <Text style={[styles.timeText, { color: theme.icon }]}>{msg.time}</Text>
                  </View>
                ) : (
                  <View key={msg.id} style={styles.aiMsgWrap}>
                    <View style={styles.aiRow}>
                      {/* Avatar */}
                      <LinearGradient
                        colors={['#1e3a8a', '#2563eb']}
                        style={styles.aiAvatar}
                      >
                        <Ionicons name="hardware-chip-outline" size={14} color="#fff" />
                      </LinearGradient>

                      <View style={[styles.aiBubble, { backgroundColor: theme.card, borderColor: theme.border }]}>
                        <Text style={[styles.aiText, { color: theme.text }]}>
                          {renderText(msg.text, isDark)}
                        </Text>
                        {msg.showFeedback && (
                          <View style={[styles.feedbackRow, { borderTopColor: theme.border }]}>
                            <TouchableOpacity style={styles.feedbackBtn} activeOpacity={0.7}>
                              <Feather name="thumbs-up" size={14} color={theme.icon} />
                              <Text style={[styles.feedbackLabel, { color: theme.icon }]}>Helpful</Text>
                            </TouchableOpacity>
                            <TouchableOpacity style={styles.feedbackBtn} activeOpacity={0.7}>
                              <Feather name="thumbs-down" size={14} color={theme.icon} />
                              <Text style={[styles.feedbackLabel, { color: theme.icon }]}>Not helpful</Text>
                            </TouchableOpacity>
                          </View>
                        )}
                      </View>
                    </View>
                    <Text style={[styles.timeText, { color: theme.icon, marginLeft: 42 }]}>{msg.time}</Text>
                  </View>
                ),
              )}

              {/* Typing indicator */}
              {isLoading && (
                <View style={styles.aiRow}>
                  <LinearGradient colors={['#1e3a8a', '#2563eb']} style={styles.aiAvatar}>
                    <Ionicons name="hardware-chip-outline" size={14} color="#fff" />
                  </LinearGradient>
                  <View style={[styles.aiBubble, { backgroundColor: theme.card, borderColor: theme.border }]}>
                    <TypingDots color={theme.primary} />
                  </View>
                </View>
              )}

              {/* Follow-up chips */}
              {!isLoading && suggestions.length > 0 && (
                <View style={styles.chipsSection}>
                  <Text style={[styles.sectionLabel, { color: theme.icon }]}>FOLLOW-UP</Text>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: 8 }}>
                    <View style={{ flexDirection: 'row', gap: 8 }}>
                      {suggestions.map((s, i) => (
                        <TouchableOpacity
                          key={i}
                          style={[styles.chip, { backgroundColor: theme.card, borderColor: theme.border }]}
                          onPress={() => send(s)}
                          activeOpacity={0.7}
                        >
                          <Text style={[styles.chipText, { color: theme.primary }]}>{s}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </ScrollView>
                </View>
              )}
            </View>
          )}
        </ScrollView>

        {/* ── Input bar ── */}
        <View style={[styles.inputContainer, { backgroundColor: theme.background, borderTopColor: theme.border }]}>
          <View style={[styles.inputWrapper, { backgroundColor: theme.card, borderColor: theme.border }]}>
            <TextInput
              placeholder="Ask me anything…"
              placeholderTextColor={theme.icon}
              style={[styles.input, { color: theme.text }]}
              value={input}
              onChangeText={setInput}
              onSubmitEditing={() => send(input)}
              returnKeyType="send"
              editable={!isLoading}
              multiline
              maxLength={500}
            />

            <TouchableOpacity
              style={[styles.micButton, { opacity: isLoading ? 0.4 : 1, backgroundColor: micActive ? theme.primary + '22' : 'transparent' }]}
              onPress={openVoice}
              disabled={isLoading}
              activeOpacity={0.7}
            >
              <Feather name={micActive ? 'mic' : 'mic'} size={19} color={micActive ? theme.primary : theme.icon} />
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.sendButton, { backgroundColor: canSend ? theme.primary : theme.border }]}
              onPress={() => send(input)}
              disabled={!canSend}
              activeOpacity={0.8}
            >
              {isLoading
                ? <ActivityIndicator size="small" color="#fff" />
                : <Ionicons name="send" size={15} color={canSend ? '#fff' : theme.icon} />}
            </TouchableOpacity>
          </View>

          {/* Disclaimer */}
          <Text style={[styles.disclaimer, { color: theme.icon }]}>
            AI responses are for guidance only · Always follow official advisories
          </Text>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  container:        { flex: 1 },
  contentContainer: { padding: 20, paddingTop: 60, paddingBottom: 20 },

  // Hero
  heroSection: { marginBottom: 24 },
  heroGradient: {
    borderRadius: 24, padding: 24, alignItems: 'center',
    overflow: 'hidden',
  },
  heroIconBg: {
    width: 72, height: 72, borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.15)',
    alignItems: 'center', justifyContent: 'center',
    marginBottom: 14,
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)',
  },
  heroTitle: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 22, color: '#fff', marginBottom: 8, letterSpacing: -0.3,
  },
  heroSubtitle: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13, color: 'rgba(255,255,255,0.7)',
    textAlign: 'center', lineHeight: 19, marginBottom: 16,
    paddingHorizontal: 8,
  },
  heroChips: { flexDirection: 'row', gap: 8, flexWrap: 'wrap', justifyContent: 'center' },
  heroChip: {
    backgroundColor: 'rgba(255,255,255,0.15)',
    borderRadius: 20, paddingHorizontal: 12, paddingVertical: 5,
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)',
  },
  heroChipText: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 11, color: 'rgba(255,255,255,0.9)',
  },

  // Suggestions
  suggestionsSection: { marginBottom: 8 },
  sectionLabel: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 10, letterSpacing: 1.5, marginBottom: 12,
  },
  suggestionsGrid: { gap: 10 },
  suggestionCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    padding: 14, borderRadius: 16, borderWidth: 1,
  },
  suggestionIconBox: {
    width: 36, height: 36, borderRadius: 10,
    alignItems: 'center', justifyContent: 'center',
  },
  suggestionText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14, flex: 1, lineHeight: 20,
  },

  // Chat
  chatArea: { gap: 6, marginTop: 8 },
  userMsgWrap: { alignItems: 'flex-end', marginBottom: 4 },
  userBubble: {
    borderTopLeftRadius: 20, borderTopRightRadius: 20,
    borderBottomLeftRadius: 20, borderBottomRightRadius: 4,
    padding: 14, maxWidth: '82%',
  },
  userText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14, color: '#fff', lineHeight: 21,
  },
  timeText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 10, marginTop: 3, marginBottom: 8,
  },
  aiMsgWrap: { marginBottom: 4 },
  aiRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  aiAvatar: {
    width: 30, height: 30, borderRadius: 10,
    alignItems: 'center', justifyContent: 'center',
    marginTop: 2, flexShrink: 0,
  },
  aiBubble: {
    flex: 1, padding: 14,
    borderTopLeftRadius: 4, borderTopRightRadius: 20,
    borderBottomLeftRadius: 20, borderBottomRightRadius: 20,
    borderWidth: 1,
  },
  aiText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14, lineHeight: 22,
  },
  feedbackRow: {
    flexDirection: 'row', gap: 16,
    borderTopWidth: 1, paddingTop: 10, marginTop: 10,
  },
  feedbackBtn: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  feedbackLabel: {
    fontFamily: 'PlusJakartaSans_400Regular', fontSize: 12,
  },

  // Follow-up chips
  chipsSection: { marginTop: 8, marginBottom: 4 },
  chip: {
    borderRadius: 20, paddingVertical: 8, paddingHorizontal: 14,
    borderWidth: 1, flexShrink: 0,
  },
  chipText: { fontSize: 12, fontFamily: 'PlusJakartaSans_500Medium' },

  // Input bar
  inputContainer: {
    paddingHorizontal: 16, paddingTop: 12,
    paddingBottom: Platform.OS === 'ios' ? 28 : 16,
    borderTopWidth: 1,
  },
  inputWrapper: {
    flexDirection: 'row', alignItems: 'center',
    borderRadius: 26, paddingHorizontal: 14, paddingVertical: 6,
    borderWidth: 1, marginBottom: 8,
  },
  input: {
    flex: 1, fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14, paddingVertical: 8, maxHeight: 100,
  },
  micButton: {
    width: 34, height: 34, borderRadius: 17,
    alignItems: 'center', justifyContent: 'center',
    marginRight: 4,
  },
  sendButton: {
    width: 36, height: 36, borderRadius: 18,
    alignItems: 'center', justifyContent: 'center',
  },
  disclaimer: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 10, textAlign: 'center', letterSpacing: 0.2,
  },

  // Voice overlay
  overlayBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  overlaySheet: {
    backgroundColor: '#0f172a',
    borderTopLeftRadius: 32, borderTopRightRadius: 32,
    paddingTop: 16, paddingBottom: 48, paddingHorizontal: 32,
    alignItems: 'center',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)',
  },
  overlayHandle: {
    width: 40, height: 4, borderRadius: 2,
    backgroundColor: 'rgba(255,255,255,0.2)', marginBottom: 24,
  },
  overlayStatus: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 20, marginBottom: 28, letterSpacing: 0.3,
  },
  overlayWaveArea: {
    height: 64, justifyContent: 'center', alignItems: 'center', marginBottom: 20,
  },
  interimText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 15, fontStyle: 'italic', textAlign: 'center',
    marginBottom: 28, lineHeight: 22, paddingHorizontal: 8,
    minHeight: 44, color: 'rgba(255,255,255,0.8)',
  },
  overlayHint: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13, textAlign: 'center', marginBottom: 28,
    minHeight: 44, lineHeight: 20, color: 'rgba(255,255,255,0.4)',
  },
  overlayBtns: {
    flexDirection: 'row', alignItems: 'center',
    justifyContent: 'space-between', width: '100%', marginTop: 8,
  },
  cancelBtn: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center' },
  stopBtn: {
    width: 72, height: 72, borderRadius: 36,
    alignItems: 'center', justifyContent: 'center',
    shadowColor: '#000', shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3, shadowRadius: 10, elevation: 8,
  },
  waveRow: { flexDirection: 'row', alignItems: 'center', gap: 5, height: 56 },
  waveBar: { width: 5, borderRadius: 3, minHeight: 6 },
});
