import { Platform } from 'react-native';

const BACKEND_URL =
  Platform.OS === 'web'
    ? 'http://localhost:8000'
    : 'https://amused-luck-production.up.railway.app';

export default BACKEND_URL;
