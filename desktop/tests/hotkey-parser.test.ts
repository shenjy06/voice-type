import { describe, expect, it } from 'vitest'
import { parseHotkey, bindingToString, hotkeyLabel } from '../src/main/hotkey/hotkey-parser'

describe('parseHotkey', () => {
  it('parses right_alt in its variants', () => {
    expect(parseHotkey('right_alt')).toEqual({ kind: 'right_alt' })
    expect(parseHotkey(' Right-Alt ')).toEqual({ kind: 'right_alt' })
    expect(parseHotkey('')).toEqual({ kind: 'right_alt' }) // unknown → default
  })

  it('parses vk: codes and hex codes', () => {
    expect(parseHotkey('vk:119')).toEqual({ kind: 'key', vk: 119 })
    expect(parseHotkey('0x78')).toEqual({ kind: 'key', vk: 0x78 })
    expect(parseHotkey('vk:abc')).toEqual({ kind: 'right_alt' })
  })

  it('parses f-keys and single characters', () => {
    expect(parseHotkey('f9')).toEqual({ kind: 'key', vk: 0x78 })
    expect(parseHotkey('F1')).toEqual({ kind: 'key', vk: 0x70 })
    expect(parseHotkey('a')).toEqual({ kind: 'key', vk: 65 })
    expect(parseHotkey('5')).toEqual({ kind: 'key', vk: 53 })
    expect(parseHotkey('capslock')).toEqual({ kind: 'key', vk: 0x14 })
  })
})

describe('bindingToString / hotkeyLabel', () => {
  it('round-trips bindings', () => {
    expect(bindingToString(parseHotkey('right_alt'))).toBe('right_alt')
    expect(bindingToString(parseHotkey('f9'))).toBe('vk:120')
    expect(hotkeyLabel('right_alt')).toBe('Right Alt')
    expect(hotkeyLabel('f9')).toBe('F9')
    expect(hotkeyLabel('a')).toBe('A')
  })
})
