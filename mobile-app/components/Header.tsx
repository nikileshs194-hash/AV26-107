import { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TouchableWithoutFeedback, Platform } from 'react-native';
import { MaterialIcons, Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { Colors } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { useAuth } from '@/context/AuthContext';

interface HeaderProps {
  city?: string;
}

export default function Header({ city }: HeaderProps) {
  const colorScheme = useColorScheme() ?? 'light';
  const theme = Colors[colorScheme];
  const isDark = colorScheme === 'dark';
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  const initials = user?.full_name
    ? user.full_name.trim().split(/\s+/).map(n => n[0]).join('').toUpperCase().slice(0, 2)
    : (user?.phone?.slice(-2) ?? '?');

  const firstName = user?.full_name?.split(' ')[0] ?? '';

  return (
    <View style={styles.container}>
      {/* Location */}
      <View style={styles.locationContainer}>
        <View style={[styles.locationIconBox, { backgroundColor: theme.primary + '18' }]}>
          <MaterialIcons name="location-on" size={16} color={theme.primary} />
        </View>
        <View style={{ flex: 1, marginLeft: 8 }}>
          <Text style={[styles.locationLabel, { color: theme.icon }]}>Current Location</Text>
          <Text style={[styles.locationText, { color: theme.text }]} numberOfLines={1}>
            {city || 'Locating…'}
          </Text>
        </View>
      </View>

      {/* Avatar + dropdown */}
      <View style={styles.avatarWrap}>
        <TouchableOpacity onPress={() => setMenuOpen(v => !v)} activeOpacity={0.8}>
          <LinearGradient
            colors={['#2563eb', '#1d4ed8']}
            style={styles.avatarCircle}
            start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
          >
            <Text style={styles.avatarInitials}>{initials}</Text>
          </LinearGradient>
          {menuOpen && (
            <View style={styles.menuDot} />
          )}
        </TouchableOpacity>

        {menuOpen && (
          <>
            <TouchableWithoutFeedback onPress={() => setMenuOpen(false)}>
              <View style={[styles.backdrop, Platform.OS === 'web' ? { position: 'fixed' as any } : { position: 'absolute', top: -1000, left: -1000, right: -1000, bottom: -1000 }]} />
            </TouchableWithoutFeedback>
            <View style={[styles.menu, { backgroundColor: isDark ? '#1e293b' : '#fff', borderColor: isDark ? 'rgba(255,255,255,0.1)' : '#f1f5f9' }]}>
              {/* User info */}
              <View style={styles.menuHeader}>
                <LinearGradient
                  colors={['#2563eb', '#1d4ed8']}
                  style={styles.menuAvatar}
                  start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
                >
                  <Text style={styles.menuAvatarText}>{initials}</Text>
                </LinearGradient>
                <View style={{ flex: 1 }}>
                  {user?.full_name && (
                    <Text style={[styles.menuName, { color: isDark ? '#f1f5f9' : '#0f172a' }]} numberOfLines={1}>
                      {user.full_name}
                    </Text>
                  )}
                  <Text style={[styles.menuPhone, { color: isDark ? '#94a3b8' : '#64748b' }]}>
                    {user?.phone}
                  </Text>
                </View>
              </View>

              <View style={[styles.menuDivider, { backgroundColor: isDark ? 'rgba(255,255,255,0.08)' : '#f1f5f9' }]} />

              {/* Logout */}
              <TouchableOpacity
                style={styles.menuItem}
                onPress={() => { setMenuOpen(false); logout(); }}
                activeOpacity={0.7}
              >
                <View style={styles.menuItemIconBox}>
                  <Ionicons name="log-out-outline" size={16} color="#ef4444" />
                </View>
                <Text style={styles.menuItemText}>Log Out</Text>
              </TouchableOpacity>
            </View>
          </>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 24,
    zIndex: 100,
  },
  locationContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    marginRight: 12,
  },
  locationIconBox: {
    width: 34, height: 34, borderRadius: 10,
    alignItems: 'center', justifyContent: 'center',
    flexShrink: 0,
  },
  locationLabel: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 10, letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  locationText: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 18, letterSpacing: -0.3,
  },
  avatarWrap: {
    position: 'relative',
    zIndex: 100,
  },
  avatarCircle: {
    width: 42, height: 42, borderRadius: 14,
    alignItems: 'center', justifyContent: 'center',
    shadowColor: '#2563eb', shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.35, shadowRadius: 8, elevation: 5,
  },
  avatarInitials: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 15, color: '#fff',
  },
  menuDot: {
    position: 'absolute', bottom: 0, right: 0,
    width: 10, height: 10, borderRadius: 5,
    backgroundColor: '#22c55e',
    borderWidth: 2, borderColor: '#fff',
  },
  backdrop: {
    top: 0, left: 0, right: 0, bottom: 0,
    zIndex: 99,
  },
  menu: {
    position: 'absolute',
    top: 52, right: 0,
    borderRadius: 18,
    paddingVertical: 6,
    minWidth: 210,
    borderWidth: 1,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.12,
    shadowRadius: 20,
    elevation: 12,
    zIndex: 200,
  },
  menuHeader: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: 14, paddingTop: 10, paddingBottom: 12,
  },
  menuAvatar: {
    width: 36, height: 36, borderRadius: 10,
    alignItems: 'center', justifyContent: 'center',
  },
  menuAvatarText: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 13, color: '#fff',
  },
  menuName: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14, marginBottom: 1,
  },
  menuPhone: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 12,
  },
  menuDivider: {
    height: 1,
    marginBottom: 4,
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  menuItemIconBox: {
    width: 28, height: 28, borderRadius: 8,
    backgroundColor: '#fef2f2',
    alignItems: 'center', justifyContent: 'center',
  },
  menuItemText: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 14,
    color: '#ef4444',
  },
});
