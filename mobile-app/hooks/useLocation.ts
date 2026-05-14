import { useState, useEffect } from 'react';
import * as Location from 'expo-location';

export interface UserLocation {
  lat: number;
  lon: number;
  city: string;
}

async function resolveCityName(lat: number, lon: number): Promise<string> {
  // Try expo-location reverse geocode first
  try {
    const [geo] = await Location.reverseGeocodeAsync({ latitude: lat, longitude: lon });
    if (geo) {
      const parts = [geo.city, geo.district, geo.region, geo.country].filter(Boolean);
      if (parts.length >= 2) return parts.join(', ');
    }
  } catch (_) {}

  // Fallback: Nominatim (free OpenStreetMap, no key required)
  try {
    const res = await fetch(
      `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json`,
      { headers: { 'Accept-Language': 'en', 'User-Agent': 'FloodAIApp/1.0' } }
    );
    if (res.ok) {
      const data = await res.json();
      const addr = data.address ?? {};
      const city =
        addr.city || addr.town || addr.village || addr.county || addr.state_district;
      const region = addr.state;
      const country = addr.country;
      const parts = [city, region, country].filter(Boolean);
      if (parts.length > 0) return parts.join(', ');
      if (data.display_name) return data.display_name.split(',').slice(0, 3).join(',').trim();
    }
  } catch (_) {}

  return `${lat.toFixed(2)}, ${lon.toFixed(2)}`;
}

export default function useLocation() {
  const [location, setLocation] = useState<UserLocation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const { status } = await Location.requestForegroundPermissionsAsync();
        if (status !== 'granted') {
          if (mounted) {
            setError('Location permission denied');
            setLocation({ lat: 12.9716, lon: 77.5946, city: 'Bengaluru, Karnataka, India' });
          }
          return;
        }
        const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
        if (!mounted) return;
        const { latitude: lat, longitude: lon } = pos.coords;
        const city = await resolveCityName(lat, lon);
        setLocation({ lat, lon, city });

        // Save location to backend so "Call Nearby People" can find us
        try {
          const AsyncStorage = (await import('@react-native-async-storage/async-storage')).default;
          const userStr = await AsyncStorage.getItem('jeevansetu_user');
          if (userStr) {
            const user = JSON.parse(userStr);
            if (user?.phone) {
              const BACKEND_URL = (await import('@/constants/api')).default;
              await fetch(`${BACKEND_URL}/api/auth/update-location`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phone: user.phone, latitude: lat, longitude: lon }),
              });
            }
          }
        } catch (_) {
          // Non-critical — don't block the UI
        }
      } catch (e: any) {
        if (mounted) {
          setError(e.message);
          setLocation({ lat: 12.9716, lon: 77.5946, city: 'Bengaluru, Karnataka, India' });
        }
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, []);

  return { location, loading, error };
}
