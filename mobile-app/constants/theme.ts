/**
 * Below are the colors that are used in the app. The colors are defined in the light and dark mode.
 * There are many other ways to style your app. For example, [Nativewind](https://www.nativewind.dev/), [Tamagui](https://tamagui.dev/), [unistyles](https://reactnativeunistyles.vercel.app), etc.
 */

import { Platform } from 'react-native';

const tintColorLight = '#005da7';
const tintColorDark = '#a3c9ff';

export const Colors = {
  light: {
    text: '#191c1d',
    background: '#f8f9fa',
    tint: tintColorLight,
    icon: '#707785',
    tabIconDefault: '#707785',
    tabIconSelected: tintColorLight,
    primary: '#005da7',
    primaryContainer: '#0076d1',
    onPrimary: '#ffffff',
    secondary: '#8c5000',
    secondaryContainer: '#fe9400',
    tertiary: '#bc000a',
    tertiaryContainer: '#e2241f',
    error: '#ba1a1a',
    onError: '#ffffff',
    card: '#ffffff',
    border: '#e1e3e4',
  },
  dark: {
    text: '#e1e3e4',
    background: '#191c1d',
    tint: tintColorDark,
    icon: '#c0c7d5',
    tabIconDefault: '#c0c7d5',
    tabIconSelected: tintColorDark,
    primary: '#a3c9ff',
    primaryContainer: '#004883',
    onPrimary: '#001c39',
    secondary: '#ffb874',
    secondaryContainer: '#6a3b00',
    tertiary: '#ffb4aa',
    tertiaryContainer: '#930005',
    error: '#ffdad6',
    onError: '#93000a',
    card: '#2e3132',
    border: '#404753',
  },
};

export const Fonts = Platform.select({
  ios: {
    /** iOS `UIFontDescriptorSystemDesignDefault` */
    sans: 'system-ui',
    /** iOS `UIFontDescriptorSystemDesignSerif` */
    serif: 'ui-serif',
    /** iOS `UIFontDescriptorSystemDesignRounded` */
    rounded: 'ui-rounded',
    /** iOS `UIFontDescriptorSystemDesignMonospaced` */
    mono: 'ui-monospace',
  },
  default: {
    sans: 'normal',
    serif: 'serif',
    rounded: 'normal',
    mono: 'monospace',
  },
  web: {
    sans: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
    serif: "Georgia, 'Times New Roman', serif",
    rounded: "'SF Pro Rounded', 'Hiragino Maru Gothic ProN', Meiryo, 'MS PGothic', sans-serif",
    mono: "SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
  },
});
