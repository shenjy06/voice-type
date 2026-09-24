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
  // ---- surface & elevation additions (native-app feel) ----
  /** Subtle raised surface (group headers, toolbar, tab strip). */
  bgSubtle: string
  /** Overlay/scrim behind modals. */
  scrim: string
  /** Hairline used for internal separators (weaker than `border`). */
  borderSubtle: string
  /** Soft accent wash for selected rows / active items. */
  accentSoft: string
  /** Ambient shadow colour, tuned per theme. */
  shadow: string
  /** Text on top of a saturated accent fill. */
  textOnAccent: string
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
  warningPressed: '#d97706',
  bgSubtle: '#1f2033',
  scrim: 'rgba(8, 9, 18, 0.6)',
  borderSubtle: '#2c2d42',
  accentSoft: 'rgba(124, 140, 255, 0.16)',
  shadow: 'rgba(0, 0, 0, 0.5)',
  textOnAccent: '#ffffff'
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
  warningPressed: '#92400e',
  bgSubtle: '#f1f5f9',
  scrim: 'rgba(15, 23, 42, 0.35)',
  borderSubtle: '#eef2f6',
  accentSoft: 'rgba(99, 102, 241, 0.1)',
  shadow: 'rgba(15, 23, 42, 0.12)',
  textOnAccent: '#ffffff'
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

// ---- design tokens -----------------------------------------------------------
// Theme-independent scales (spacing, radius, elevation, type, motion). Keeping
// them separate from the palette means a theme swap only repaints colours.

export const SPACE = {
  xs: '4px',
  sm: '6px',
  md: '10px',
  lg: '14px',
  xl: '20px'
} as const

export const RADIUS = {
  sm: '5px',
  md: '7px',
  lg: '10px',
  xl: '14px',
  pill: '999px'
} as const

const FONT_STACK =
  "'Segoe UI Variable Text', 'Segoe UI', 'Microsoft YaHei UI', 'Microsoft YaHei', system-ui, -apple-system, sans-serif"

export const FONT_SIZE = {
  xs: '11px',
  sm: '12px',
  md: '13px',
  lg: '15px',
  xl: '17px'
} as const

export const MOTION = {
  fast: '110ms',
  base: '170ms',
  slow: '260ms',
  ease: 'cubic-bezier(0.32, 0.72, 0, 1)'
} as const

/**
 * Design-token CSS variables. Elevation uses layered shadows (a tight ambient
 * one plus a wider soft one) which reads as far more "native" than a single
 * blurred box-shadow.
 */
export function designTokenCssVars(mode: 'dark' | 'light'): string {
  const p = paletteForMode(mode)
  const s = p.shadow
  const tokens: Record<string, string> = {
    'font-stack': FONT_STACK,
    'space-xs': SPACE.xs,
    'space-sm': SPACE.sm,
    'space-md': SPACE.md,
    'space-lg': SPACE.lg,
    'space-xl': SPACE.xl,
    'radius-sm': RADIUS.sm,
    'radius-md': RADIUS.md,
    'radius-lg': RADIUS.lg,
    'radius-xl': RADIUS.xl,
    'radius-pill': RADIUS.pill,
    'font-xs': FONT_SIZE.xs,
    'font-sm': FONT_SIZE.sm,
    'font-md': FONT_SIZE.md,
    'font-lg': FONT_SIZE.lg,
    'font-xl': FONT_SIZE.xl,
    'motion-fast': MOTION.fast,
    'motion-base': MOTION.base,
    'motion-slow': MOTION.slow,
    'motion-ease': MOTION.ease,
    // elevation scale
    'shadow-1': `0 1px 2px ${s}, 0 1px 3px ${s}`,
    'shadow-2': `0 2px 4px ${s}, 0 4px 12px ${s}`,
    'shadow-3': `0 4px 8px ${s}, 0 12px 28px ${s}`,
    'shadow-4': `0 8px 16px ${s}, 0 24px 48px ${s}`,
    'focus-ring': `0 0 0 3px ${mode === 'dark' ? 'rgba(124,140,255,0.35)' : 'rgba(99,102,241,0.28)'}`
  }
  return Object.entries(tokens)
    .map(([key, value]) => `--vt-${key}: ${value};`)
    .join(' ')
}

/** Palette + design tokens, for a single style attribute on <html>. */
export function themeCssVars(mode: 'dark' | 'light'): string {
  return `${paletteCssVars(mode)} ${designTokenCssVars(mode)}`
}
