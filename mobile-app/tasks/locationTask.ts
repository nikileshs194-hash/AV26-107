/**
 * Background Location Task
 *
 * This file ONLY defines the task handler (must be in module/global scope,
 * called before any React component renders — Expo requirement).
 *
 * The permission request + startLocationUpdatesAsync call live in
 * app/(tabs)/_layout.tsx so that:
 *   1. Foreground permission is requested first (required on iOS before background)
 *   2. Background permission is requested in the correct UX sequence
 *   3. No race condition from two places calling startLocationUpdatesAsync
 */

import { Platform } from 'react-native';
import BACKEND_URL from '@/constants/api';

export const LOCATION_TASK_NAME = 'jeevansetu-background-location';

// Task handler must be registered at module load time (before any UI renders).
// This is an Expo hard requirement — do not move this inside a component.
if (Platform.OS !== 'web') {
  Promise.all([
    import('expo-task-manager'),
    import('@react-native-async-storage/async-storage'),
  ]).then(([TaskManager, { default: AsyncStorage }]) => {

    TaskManager.defineTask(
      LOCATION_TASK_NAME,
      async ({ data, error }: any) => {
        if (error) {
          console.warn('[BG Location] Task error:', error.message);
          return;
        }
        if (!data) return;

        const { locations } = data as { locations: any[] };
        const loc = locations?.[0];
        if (!loc) return;

        try {
          const userStr = await AsyncStorage.getItem('jeevansetu_user');
          if (!userStr) return;
          const user = JSON.parse(userStr);
          if (!user?.phone) return;

          await fetch(`${BACKEND_URL}/api/auth/update-location`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
              phone:     user.phone,
              latitude:  loc.coords.latitude,
              longitude: loc.coords.longitude,
            }),
          });
          console.log(
            `[BG Location] Updated: ${loc.coords.latitude.toFixed(5)}, ${loc.coords.longitude.toFixed(5)}`
          );
        } catch (e) {
          console.warn('[BG Location] Failed to send location:', e);
        }
      }
    );

    console.log('[BG Location] Task handler registered ✅');
  }).catch((e) => {
    console.warn('[BG Location] Module load failed:', e);
  });
}
