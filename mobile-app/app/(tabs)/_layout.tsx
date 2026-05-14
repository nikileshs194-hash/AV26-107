import { Tabs } from 'expo-router';
import React, { useEffect } from 'react';
import { Platform } from 'react-native';
import { useFonts, PlusJakartaSans_400Regular, PlusJakartaSans_500Medium, PlusJakartaSans_600SemiBold, PlusJakartaSans_700Bold } from '@expo-google-fonts/plus-jakarta-sans';
import * as Location from 'expo-location';
// This import ensures the background task handler is registered at module load
// time (Expo requirement: defineTask must run before any component renders).
import { LOCATION_TASK_NAME } from '@/tasks/locationTask';

import { HapticTab } from '@/components/haptic-tab';
import { IconSymbol } from '@/components/ui/icon-symbol';
import { Colors } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { Text } from 'react-native';
import { useAuth } from '@/context/AuthContext';
import { updateLocation } from '@/services/auth';

export default function TabLayout() {
  const colorScheme = useColorScheme();
  const { user } = useAuth();

  let [fontsLoaded] = useFonts({
    PlusJakartaSans_400Regular,
    PlusJakartaSans_500Medium,
    PlusJakartaSans_600SemiBold,
    PlusJakartaSans_700Bold,
  });

  useEffect(() => {
    if (!user?.phone) return;

    const startLocationTracking = async () => {
      try {
        // ── Step 1: Foreground permission (MUST come before background on iOS) ──
        const { status: fgStatus } = await Location.requestForegroundPermissionsAsync();
        if (fgStatus !== 'granted') {
          console.warn('[Location] Foreground permission denied');
          return;
        }

        // ── Step 2: Send first location to backend immediately ────────────────
        const loc = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
        await updateLocation(user.phone, loc.coords.latitude, loc.coords.longitude);
        console.log('[Location] Initial location sent ✅');

        // ── Step 3: Background tracking (native only) ─────────────────────────
        if (Platform.OS === 'web') return;

        // Request background permission — iOS shows "Upgrade to Always Allow"
        // dialog here (after foreground is granted, which is the correct UX order).
        const { status: bgStatus } = await Location.requestBackgroundPermissionsAsync();
        if (bgStatus !== 'granted') {
          console.log('[Location] Background permission not granted — foreground-only mode');
          return;
        }

        // Start the OS background task if not already running.
        // Once started it persists across app restarts until explicitly stopped.
        const alreadyRunning = await Location.hasStartedLocationUpdatesAsync(LOCATION_TASK_NAME)
          .catch(() => false);

        if (!alreadyRunning) {
          await Location.startLocationUpdatesAsync(LOCATION_TASK_NAME, {
            accuracy:                         Location.Accuracy.Balanced,
            distanceInterval:                 50,      // fire every 50 m of movement
            timeInterval:                     60_000,  // or at least every 60 s
            showsBackgroundLocationIndicator: true,    // iOS blue location bar
            foregroundService: {
              // Android: keeps the process alive as a visible foreground service
              notificationTitle: 'JeevanSetu',
              notificationBody:  'Tracking location for emergency alerts',
              notificationColor: '#2563eb',
            },
          });
          console.log('[Location] Background tracking started ✅');
        } else {
          console.log('[Location] Background tracking already running ✅');
        }
      } catch (e) {
        // Silently swallow on Expo Go / iOS simulator — background location
        // requires a custom dev build or production build.
        console.log('[Location] Tracking skipped (Expo Go or permission denied):', e);
      }
    };

    startLocationTracking();
  }, [user?.phone]);

  if (!fontsLoaded) {
    return <Text style={{flex: 1, textAlign: 'center', marginTop: 100}}>Loading Fonts...</Text>;
  }

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: Colors[colorScheme ?? 'light'].tint,
        headerShown: false,
        tabBarButton: HapticTab,
        tabBarStyle: {
          backgroundColor: Colors[colorScheme ?? 'light'].card,
          borderTopColor: Colors[colorScheme ?? 'light'].border,
        }
      }}>
      <Tabs.Screen
        name="index"
        options={{
          title: 'Weather',
          tabBarIcon: ({ color }) => <IconSymbol size={28} name="house.fill" color={color} />,
        }}
      />
      <Tabs.Screen
        name="ai"
        options={{
          title: 'AI Assistance',
          tabBarIcon: ({ color }) => <IconSymbol size={28} name="sparkles" color={color} />,
        }}
      />
      <Tabs.Screen
        name="alerts"
        options={{
          title: 'Alerts',
          tabBarIcon: ({ color }) => <IconSymbol size={28} name="bell.fill" color={color} />,
        }}
      />
    </Tabs>
  );
}
