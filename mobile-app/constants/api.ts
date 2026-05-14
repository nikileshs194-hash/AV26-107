import { Platform } from 'react-native';

// web (browser on laptop) → localhost
// real Android/iOS device   → laptop's LAN IP (must be on same WiFi)
// Android emulator          → 10.0.2.2 (maps to host localhost)
const BACKEND_URL =
  Platform.OS === 'web'
    ? 'http://localhost:8000'
    : 'http://10.92.249.1:8000';

export default BACKEND_URL;
