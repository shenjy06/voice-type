// Guards the design-token contract: every --vt-* variable referenced by any
// stylesheet must actually be emitted by themeCssVars(). A typo or a token
// dropped from the palette fails silently in the UI (the declaration just
// resolves to nothing), so this test is the only automated check that the
// stylesheets and the token emitter agree.

import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { themeCssVars, DARK_PALETTE, LIGHT_PALETTE, SPACE, RADIUS, MOTION, FONT_SIZE } from '../src/shared/theme'

const RENDERER = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'renderer')

function collectCssFiles(dir: string): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) out.push(...collectCssFiles(full))
    else if (name.endsWith('.css')) out.push(full)
  }
  return out
}

/** All `var(--vt-x)` / `--vt-x:` names referenced across the renderer CSS. */
function referencedTokens(): Set<string> {
  const names = new Set<string>()
  for (const file of collectCssFiles(RENDERER)) {
    const css = readFileSync(file, 'utf-8')
    for (const m of css.matchAll(/var\(\s*(--vt-[a-z0-9-]+)/gi)) names.add(m[1])
    // Local definitions inside a stylesheet are self-provided.
    for (const m of css.matchAll(/^\s*(--vt-[a-z0-9-]+)\s*:/gim)) names.add(m[1])
  }
  return names
}

describe('design token contract', () => {
  for (const mode of ['dark', 'light'] as const) {
    it(`emits every --vt-* referenced by the stylesheets (${mode})`, () => {
      const emitted = new Set(
        [...themeCssVars(mode).matchAll(/(--vt-[a-z0-9-]+)\s*:/gi)].map((m) => m[1])
      )
      const missing = [...referencedTokens()].filter((t) => !emitted.has(t)).sort()
      expect(missing, `未定义的 token: ${missing.join(', ')}`).toEqual([])
    })
  }

  it('keeps both palettes structurally identical', () => {
    const dark = Object.keys(DARK_PALETTE).sort()
    const light = Object.keys(LIGHT_PALETTE).sort()
    expect(light).toEqual(dark)
  })

  it('has no empty token values', () => {
    for (const [mode, palette] of [
      ['dark', DARK_PALETTE],
      ['light', LIGHT_PALETTE]
    ] as const) {
      for (const [key, value] of Object.entries(palette)) {
        expect(value, `${mode}.${key} 为空`).toBeTruthy()
      }
    }
  })

  it('emits the design scales', () => {
    const css = themeCssVars('dark')
    for (const name of [
      ...Object.keys(SPACE).map((k) => `--vt-space-${k.toLowerCase()}`),
      ...Object.keys(RADIUS).map((k) => `--vt-radius-${k.toLowerCase()}`),
      ...Object.keys(MOTION).map((k) => `--vt-motion-${k.toLowerCase()}`),
      ...Object.keys(FONT_SIZE).map((k) => `--vt-font-${k.toLowerCase()}`),
      '--vt-shadow-1',
      '--vt-shadow-4',
      '--vt-focus-ring',
      '--vt-font-stack'
    ]) {
      expect(css, `缺少 ${name}`).toContain(`${name}:`)
    }
  })

  it('produces a different focus ring per theme', () => {
    expect(themeCssVars('dark')).not.toBe(themeCssVars('light'))
  })
})
