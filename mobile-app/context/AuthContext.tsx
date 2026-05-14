import React, { createContext, useContext, useState, useEffect } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { UserProfile } from '@/services/auth';

interface AuthContextType {
  user: UserProfile | null;
  loading: boolean;
  login: (user: UserProfile) => Promise<void>;
  logout: () => Promise<void>;
  updateUser: (updates: Partial<UserProfile>) => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null, loading: true,
  login: async () => {}, logout: async () => {}, updateUser: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    AsyncStorage.getItem('jeevansetu_user').then(data => {
      if (data) {
        try { setUser(JSON.parse(data)); } catch {}
      }
      setLoading(false);
    });
  }, []);

  const login = async (userData: UserProfile) => {
    setUser(userData);
    await AsyncStorage.setItem('jeevansetu_user', JSON.stringify(userData));
  };

  const logout = async () => {
    setUser(null);
    await AsyncStorage.removeItem('jeevansetu_user');
  };

  const updateUser = async (updates: Partial<UserProfile>) => {
    if (!user) return;
    const updated = { ...user, ...updates };
    setUser(updated);
    await AsyncStorage.setItem('jeevansetu_user', JSON.stringify(updated));
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, updateUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
