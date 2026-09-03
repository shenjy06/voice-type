// Light/dark palettes — token values ported 1:1 from src/voicetype/ui/theme.py.
// Renderers consume these as CSS custom properties; main uses them for tray
// icon drawing.

export interface Palette {
  bgDialog: string
  bgCard: string
  bgInput: string
  bgHover: string
  border: string
  borderHover: string
  borderFocus: string
  textPrimary: string
  textSecondary: string
  textDisabled: string
  textTitle: string
  accent: string
  accentHover: string
  accentPressed: string
  danger: string
  dangerHover: string
  dangerLight: string
  success: string
  warning: string
  warningHover: string
  warningPressed: string
}

export const DARK_PALETTE: Palette = {
  bgDialog: '#1a1b26',
  bgCard: '#24253a',
  bgInput: '#16172a',
  bgHover: '#2e2f48',
  border: '#3a3b52',
  borderHover: '#5a5b72',
  borderFocus: '#7c8cff',
  textPrimary: '#e5e7eb',
  textSecondary: '#9ca3af',
  textDisabled: '#6b7280',
  textTitle: '#c7c9ff',
  accent: '#7c8cff',
  accentHover: '#8b9aff',
  accentPressed: '#6366f1',
  danger: '#ef4444',
  dangerHover: '#dc2626',
  dangerLight: '#f87171',
  success: '#22c55e',
  warning: '#f59e0b',
  warningHover: '#fbbf24',
  warningPressed: '#d97706'
}

export const LIGHT_PALETTE: Palette = {
  bgDialog: '#f8fafc',
  bgCard: '#ffffff',
  bgInput: '#ffffff',
  bgHover: '#f1f5f9',
  border: '#e2e8f0',
  borderHover: '#cbd5e1',
  borderFocus: '#6366f1',
  textPrimary: '#1e293b',
  textSecondary: '#64748b',
  textDisabled: '#cbd5e1',
  textTitle: '#4f46e5',
  accent: '#6366f1',
  accentHover: '#4f46e5',
  accentPressed: '#4338ca',
  danger: '#ef4444',
  dangerHover: '#dc2626',
  dangerLight: '#f87171',
  success: '#16a34a',
  warning: '#d97706',
  warningHover: '#b45309',
  warningPressed: '#92400e'
}

export function paletteForMode(mode: 'dark' | 'light'): Palette {
  return mode === 'light' ? LIGHT_PALETTE : DARK_PALETTE
}

const toKebab = (key: string) => key.replace(/[A-Z]/g, (c) => '-' + c.toLowerCase())

/** Produce a "var-name: value; ..." string for a style attribute or stylesheet. */
export function paletteCssVars(mode: 'dark' | 'light'): string {
  const p = paletteForMode(mode)
  return Object.entries(p)
    .map(([key, value]) => `--vt-${toKebab(key)}: ${value};`)
    .join(' ')
}
