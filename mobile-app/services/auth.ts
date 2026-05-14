import axios from 'axios';
import BACKEND_URL from '@/constants/api';

const authApi = axios.create({ baseURL: BACKEND_URL, timeout: 20000 });

export interface UserProfile {
  id: string;
  phone: string;
  full_name?: string;
  age?: number;
  gender?: string;
  created_at: string;
  updated_at?: string;
}

export const sendOTP = async (phone: string, country_code = '+91') => {
  const res = await authApi.post('/api/auth/send-otp', { phone, country_code });
  return res.data as { success: boolean; message: string };
};

export const verifyOTP = async (phone: string, otp: string) => {
  const res = await authApi.post('/api/auth/verify-otp', { phone, otp });
  return res.data as { user: UserProfile; is_new: boolean };
};

export const updateProfile = async (
  phone: string, full_name: string, age: number, gender: string
) => {
  const res = await authApi.post('/api/auth/update-profile', { phone, full_name, age, gender });
  return res.data as { success: boolean; user: UserProfile };
};

export const getProfile = async (phone: string) => {
  const res = await authApi.get(`/api/auth/profile/${encodeURIComponent(phone)}`);
  return res.data as { user: UserProfile; is_new: boolean };
};

export const updateLocation = async (phone: string, latitude: number, longitude: number) => {
  await authApi.post('/api/auth/update-location', { phone, latitude, longitude });
};
