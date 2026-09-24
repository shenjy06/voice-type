// Verifies the string that applyThemeVars() assigns to <html>.style.cssText.
// That assignment is the only thing standing between the stylesheets and an
// unstyled UI, and it fails silently if malformed, so we assert on its exact
// shape: valid declarations, complete token coverage, and no duplicates.
//
// (The DOM assignment itself is a one-liner over this string, so testing the
// string is testing the meaningful part — no jsdom dependency needed.)

import { describe, expect, it } from 'vitest'
import { themeCssVars } from '../src/shared/theme'

/** Parse a `--a: b; --c: d;` string into a name→value map, rejecting malformed input. */
function parseVars(css: string): Map<string, string> {
  const out = new Map<string, string>()
  for (const raw of css.split(';')) {
    const decl = raw.trim()
    if (!decl) continue
    const idx = decl.indexOf(':')
    if (idx <= 0) throw new Error(`malformed declaration: ${JSON.stringify(decl)}`)
    const name = decl.slice(0, idx).trim()
    const value = decl.slice(idx + 1).trim()
    if (!name.startsWith('--vt-')) throw new Error(`unexpected variable: ${name}`)
    if (!value) throw new Error(`empty value for ${name}`)
    if (out.has(name)) throw new Error(`duplicate variable: ${name}`)
    out.set(name, value)
  }
  return out
}

describe('themeCssVars output', () => {
  for (const mode of ['dark', 'light'] as const) {
    it(`parses into valid, unique declarations (${mode})`, () => {
      const vars = parseVars(themeCssVars(mode))
      expect(vars.size).toBeGreaterThan(40)
    })

    it(`covers the full token surface (${mode})`, () => {
      const vars = parseVars(themeCssVars(mode))
      for (const name of [
        '--vt-bg-dialog',
        '--vt-bg-subtle',
        '--vt-scrim',
        '--vt-border-subtle',
        '--vt-accent-soft',
        '--vt-shadow',
        '--vt-text-on-accent',
        '--vt-font-stack',
        '--vt-space-md',
        '--vt-radius-lg',
        '--vt-motion-ease',
        '--vt-shadow-1',
        '--vt-shadow-4',
        '--vt-focus-ring'
      ]) {
        expect(vars.has(name), `${name} 缺失`).toBe(true)
      }
    })
  }

  it('uses identical variable names in both themes', () => {
    const dark = [...parseVars(themeCssVars('dark')).keys()].sort()
    const light = [...parseVars(themeCssVars('light')).keys()].sort()
    // A name present in one theme but not the other means a token silently
    // disappears when the user switches theme.
    expect(light).toEqual(dark)
  })

  it('varies the theme-dependent tokens but not the scales', () => {
    const dark = parseVars(themeCssVars('dark'))
    const light = parseVars(themeCssVars('light'))
    expect(dark.get('--vt-bg-dialog')).not.toBe(light.get('--vt-bg-dialog'))
    expect(dark.get('--vt-accent')).not.toBe(light.get('--vt-accent'))
    expect(dark.get('--vt-radius-lg')).toBe(light.get('--vt-radius-lg'))
    expect(dark.get('--vt-space-md')).toBe(light.get('--vt-space-md'))
    expect(dark.get('--vt-motion-base')).toBe(light.get('--vt-motion-base'))
  })

  it('is a single flat declaration list (assignable via cssText)', () => {
    const css = themeCssVars('dark')
    // No braces / selectors: this string is assigned to style.cssText, not
    // parsed as a stylesheet.
    expect(css).not.toContain('{')
    expect(css).not.toContain('}')
    expect(css.endsWith(';')).toBe(true)
  })
})
