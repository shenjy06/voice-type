// Hotkey string parsing — port of voicetype/hotkey_parser.py using virtual-key
// codes instead of pynput keys. Supported values: "right_alt", "vk:<n>"
// (Windows VK code), f1..f12, or a single character like "a"/"1".

export interface HotkeyBinding {
  kind: 'right_alt' | 'key'
  /** Windows virtual-key code for kind="key"; undefined for right_alt. */
  vk?: number
}

const F_KEY_VKS: Record<string, number> = {}
for (let i = 1; i <= 12; i++) F_KEY_VKS[`f${i}`] = 0x70 + (i - 1)

const CHAR_VKS: Record<string, number> = {
  ' ': 0x20,
  tab: 0x09,
  enter: 0x0d,
  capslock: 0x14,
  scrolllock: 0x91,
  pause: 0x13,
  insert: 0x2d,
  delete: 0x2e,
  home: 0x24,
  end: 0x23,
  pageup: 0x21,
  pagedown: 0x22
}

export function parseHotkey(hotkey: string): HotkeyBinding {
  const normalized = (hotkey || '').trim().toLowerCase()
  if (normalized === 'right_alt' || normalized === 'right-alt') return { kind: 'right_alt' }

  if (normalized.startsWith('vk:')) {
    const vkPart = normalized.slice(3)
    if (/^\d+$/.test(vkPart)) return { kind: 'key', vk: Number(vkPart) }
  }
  if (normalized.startsWith('0x') && /^[0-9a-f]+$/.test(normalized.slice(2))) {
    return { kind: 'key', vk: parseInt(normalized.slice(2), 16) }
  }
  if (F_KEY_VKS[normalized] !== undefined) return { kind: 'key', vk: F_KEY_VKS[normalized] }
  if (CHAR_VKS[normalized] !== undefined) return { kind: 'key', vk: CHAR_VKS[normalized] }
  if (normalized.length === 1) {
    const code = normalized.toUpperCase().charCodeAt(0)
    if (code >= '0'.charCodeAt(0) && code <= 'Z'.charCodeAt(0)) {
      return { kind: 'key', vk: code }
    }
  }
  return { kind: 'right_alt' }
}

export function bindingToString(binding: HotkeyBinding): string {
  if (binding.kind === 'right_alt' || binding.vk === undefined) return 'right_alt'
  return `vk:${binding.vk}`
}

/** Human-readable label for settings/tray display. */
export function hotkeyLabel(hotkey: string): string {
  const binding = parseHotkey(hotkey)
  if (binding.kind === 'right_alt') return 'Right Alt'
  const vk = binding.vk ?? 0
  for (const [name, code] of Object.entries(F_KEY_VKS)) {
    if (code === vk) return name.toUpperCase()
  }
  if (vk >= 0x30 && vk <= 0x5a) return String.fromCharCode(vk)
  return `VK 0x${vk.toString(16).toUpperCase()}`
}
