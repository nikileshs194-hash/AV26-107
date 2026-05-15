import { Platform } from 'react-native';

const BACKEND_URL =
  Platform.OS === 'web'
    ? 'http://localhost:8000'
    : 'https://YOUR-RAILWAY-URL.up.railway.app';   // ← replace after Railway deploy

export default BACKEND_URL;
