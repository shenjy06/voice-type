// Applies palette tokens as CSS custom properties on a root element.
// Mirrors theme.apply_dialog_theme in the Python app, extended with the
// theme-independent design tokens (spacing/radius/elevation/motion).

import { themeCssVars } from '../../shared/theme'

export function applyThemeVars(root: HTMLElement, theme: 'dark' | 'light'): void {
  root.style.cssText = themeCssVars(theme)
}
