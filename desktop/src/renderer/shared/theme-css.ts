// Applies palette tokens as CSS custom properties on a root element.
// Mirrors theme.apply_dialog_theme in the Python app.

import { paletteCssVars } from '../../shared/theme'

export function applyThemeVars(root: HTMLElement, theme: 'dark' | 'light'): void {
  root.style.cssText = paletteCssVars(theme)
}
