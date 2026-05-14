import { useEffect, useRef, useState } from 'react';
import { Platform } from 'react-native';
import { DarkTheme, DefaultTheme, ThemeProvider } from '@react-navigation/native';
import { Stack, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import '@/tasks/locationTask';

import { useColorScheme } from '@/hooks/use-color-scheme';
import { AuthProvider, useAuth } from '@/context/AuthContext';
import SOSAlertModal,       { SOSAlertData }       from '@/components/SOSAlertModal';
import FloodAlertModal,     { FloodAlertData }     from '@/components/FloodAlertModal';
import CycloneAlertModal,   { CycloneAlertData }   from '@/components/CycloneAlertModal';
import EarthquakeAlertModal,{ EarthquakeAlertData }from '@/components/EarthquakeAlertModal';
import { savePushToken } from '@/services/api';

// ── Push notification setup (native only) ────────────────────────────────────
let Notifications: any = null;
if (Platform.OS !== 'web') {
  Notifications = require('expo-notifications');
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldPlaySound: true,
      shouldSetBadge:  true,
    }),
  });
}

// ── AuthGate ──────────────────────────────────────────────────────────────────

function AuthGate() {
  const { user, loading } = useAuth();
  const router   = useRouter();
  const segments = useSegments();

  useEffect(() => {
    if (loading) return;
    const inAuth = segments[0] === '(auth)';
    if (!user) {
      if (!inAuth) router.replace('/(auth)/login');
      return;
    }
    if (!user.full_name) {
      if (segments[1] !== 'profile-setup')
        router.replace({ pathname: '/(auth)/profile-setup', params: { phone: user.phone } });
      return;
    }
    if (inAuth) router.replace('/(tabs)');
  }, [user, loading, segments]);

  return null;
}

// ── Root layout ───────────────────────────────────────────────────────────────

function RootLayoutInner() {
  const { user }    = useAuth();
  const colorScheme = useColorScheme();

  const [sosAlert,       setSosAlert]       = useState<SOSAlertData | null>(null);
  const [floodAlert,     setFloodAlert]     = useState<FloodAlertData | null>(null);
  const [cycloneAlert,   setCycloneAlert]   = useState<CycloneAlertData | null>(null);
  const [earthquakeAlert,setEarthquakeAlert]= useState<EarthquakeAlertData | null>(null);

  const notifListenerRef    = useRef<any>(null);
  const responseListenerRef = useRef<any>(null);

  // Register push token + create notification channels + listen for alerts
  useEffect(() => {
    if (Platform.OS === 'web' || !Notifications) return;
    if (!user?.phone) return;

    (async () => {
      // Request permission
      const { status: existing } = await Notifications.getPermissionsAsync();
      let finalStatus = existing;
      if (existing !== 'granted') {
        const { status } = await Notifications.requestPermissionsAsync();
        finalStatus = status;
      }
      if (finalStatus !== 'granted') return;

      // ── Android notification channels ──────────────────────────────────
      if (Platform.OS === 'android') {
        // MAX importance — SOS emergencies + flood alerts (bypasses DnD)
        await Notifications.setNotificationChannelAsync('sos', {
          name:                'Emergency SOS',
          importance:          Notifications.AndroidImportance.MAX,
          vibrationPattern:    [0, 500, 200, 500],
          lightColor:         '#ef4444',
          sound:              'default',
          lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
          bypassDnd:           true,
        });

        // DEFAULT importance — weather tips
        await Notifications.setNotificationChannelAsync('weather', {
          name:       'Weather Updates',
          importance: Notifications.AndroidImportance.DEFAULT,
          sound:      'default',
        });
      }

      // ── iOS — SOS + flood alert actions ────────────────────────────────
      if (Platform.OS === 'ios') {
        await Notifications.setNotificationCategoryAsync('SOS_ALERT', [
          {
            identifier:  'CALL_VICTIM',
            buttonTitle: '📞 Call Victim',
            options:     { opensAppToForeground: true },
          },
          {
            identifier:  'NAVIGATE',
            buttonTitle: '🗺 Navigate',
            options:     { opensAppToForeground: true },
          },
        ]);
        await Notifications.setNotificationCategoryAsync('FLOOD_ALERT', [
          {
            identifier:  'NAVIGATE_SHELTER',
            buttonTitle: '🗺 Navigate to Shelter',
            options:     { opensAppToForeground: true },
          },
          {
            identifier:  'I_AM_SAFE',
            buttonTitle: '✅ I Am Safe',
            options:     { opensAppToForeground: true },
          },
        ]);
      }

      // ── Get & save push token ──────────────────────────────────────────
      try {
        const Constants = require('expo-constants').default;
        const projectId =
          Constants?.expoConfig?.extra?.eas?.projectId ??
          Constants?.easConfig?.projectId ??
          undefined;

        const tokenData = await Notifications.getExpoPushTokenAsync(
          projectId ? { projectId } : undefined,
        );
        const token: string = tokenData.data;
        console.log('[PushToken] Got token:', token);
        await savePushToken(user.phone, token);
        console.log('[PushToken] Saved for', user.phone);
      } catch (e: any) {
        console.warn('[PushToken] Failed:', e?.message ?? e);
      }

      // ── Foreground notification listener ──────────────────────────────
      notifListenerRef.current = Notifications.addNotificationReceivedListener(
        (notification: any) => {
          const data = notification?.request?.content?.data;
          if (!data) return;

          if (data.type === 'sos_alert') {
            setSosAlert(data as SOSAlertData);
          } else if (data.type === 'flood_alert') {
            setFloodAlert(data as FloodAlertData);
          } else if (data.type === 'cyclone_alert') {
            setCycloneAlert(data as CycloneAlertData);
          } else if (data.type === 'earthquake_alert') {
            setEarthquakeAlert(data as EarthquakeAlertData);
          }
        }
      );

      // ── Background tap listener ───────────────────────────────────────
      responseListenerRef.current = Notifications.addNotificationResponseReceivedListener(
        (response: any) => {
          const data = response?.notification?.request?.content?.data;
          if (!data) return;

          if (data.type === 'sos_alert') {
            setSosAlert(data as SOSAlertData);
          } else if (data.type === 'flood_alert') {
            setFloodAlert(data as FloodAlertData);
          } else if (data.type === 'cyclone_alert') {
            setCycloneAlert(data as CycloneAlertData);
          } else if (data.type === 'earthquake_alert') {
            setEarthquakeAlert(data as EarthquakeAlertData);
          }
        }
      );
    })();

    return () => {
      notifListenerRef.current?.remove?.();
      responseListenerRef.current?.remove?.();
    };
  }, [user?.phone]);

  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <AuthGate />
      <Stack>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="(auth)"  options={{ headerShown: false }} />
        <Stack.Screen name="modal"   options={{ presentation: 'modal', title: 'Modal' }} />
      </Stack>
      <StatusBar style="auto" />

      {/* ── Global SOS Alert Modal ── */}
      <SOSAlertModal
        visible={!!sosAlert}
        data={sosAlert}
        onDismiss={() => setSosAlert(null)}
      />

      {/* ── Global Flood Alert Modal ── */}
      <FloodAlertModal
        visible={!!floodAlert}
        data={floodAlert}
        onDismiss={() => setFloodAlert(null)}
      />

      {/* ── Global Cyclone Alert Modal ── */}
      <CycloneAlertModal
        visible={!!cycloneAlert}
        data={cycloneAlert}
        onDismiss={() => setCycloneAlert(null)}
      />

      {/* ── Global Earthquake Alert Modal ── */}
      <EarthquakeAlertModal
        visible={!!earthquakeAlert}
        data={earthquakeAlert}
        onDismiss={() => setEarthquakeAlert(null)}
      />
    </ThemeProvider>
  );
}

export default function RootLayout() {
  return (
    <AuthProvider>
      <RootLayoutInner />
    </AuthProvider>
  );
}
