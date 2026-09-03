// Global hotkey manager — port of voicetype/ui/system_tray.py HotkeyManager.
//
// right_alt binding: a quick tap of Right Alt toggles recording; Right Alt+C
// cancels; Right Alt + any other key is a combo and does nothing. A 4-state
// machine (IDLE/WAITING/COMBO/CANCELLED) survives Windows reporting Right-Alt
// release as generic Alt. Left Alt is ignored entirely.
//
// Single-key bindings (F9 etc.) use a low-level hook with repeat suppression.
// Uses uiohook-napi; if the native module can't load, falls back to Electron
// globalShortcut for plain vk bindings (right_alt is unavailable then).

import { globalShortcut } from 'electron'

export interface HotkeyEvents {
  onToggle: () => void
  onCancel: () => void
}

// Windows VK codes (libuiohook vcodes mirror VK codes on Windows).
const VK_RMENU = 0xa5 // Right Alt
const VK_MENU = 0x12 // generic Alt
const VK_LMENU = 0xa4 // Left Alt
const VK_C = 0x43

const enum RaState {
  IDLE = 0,
  WAITING,
  COMBO,
  CANCELLED
}

type UiohookModule = {
  uIOhook: {
    on(event: 'keydown' | 'keyup', listener: (e: { keycode: number }) => void): void
    start(): void
    stop(): void
  }
}

export class HotkeyManager {
  private events: HotkeyEvents
  private hotkey: string
  private uiohook: UiohookModule | null = null
  private uiohookFailed = false
  private running = false

  // Right-Alt state machine.
  private raState: RaState = RaState.IDLE
  private raLastVk: number | null = null
  // Single-key repeat suppression.
  private singleKeyPressed = false

  constructor(hotkey: string, events: HotkeyEvents) {
    this.hotkey = hotkey
    this.events = events
  }

  isRightAltBinding(): boolean {
    return this.parse().kind === 'right_alt'
  }

  private parse(): { kind: 'right_alt' | 'key'; vk?: number } {
    const normalized = this.hotkey.trim().toLowerCase()
    if (normalized === 'right_alt' || normalized === 'right-alt') return { kind: 'right_alt' }
    if (normalized.startsWith('vk:') && /^\d+$/.test(normalized.slice(3))) {
      return { kind: 'key', vk: Number(normalized.slice(3)) }
    }
    const fMatch = normalized.match(/^f([1-9]|1[0-2])$/)
    if (fMatch) return { kind: 'key', vk: 0x70 + Number(fMatch[1]) - 1 }
    if (normalized.length === 1) {
      return { kind: 'key', vk: normalized.toUpperCase().charCodeAt(0) }
    }
    return { kind: 'right_alt' }
  }

  start(): void {
    if (this.running) return
    this.running = true
    const binding = this.parse()

    if (binding.kind === 'right_alt') {
      this.startRightAltHook()
    } else if (binding.vk !== undefined) {
      this.startSingleKey(binding.vk)
    }
  }

  stop(): void {
    if (!this.running) return
    this.running = false
    try {
      this.uiohook?.uIOhook.stop()
    } catch {
      // ignore
    }
    try {
      globalShortcut.unregisterAll()
    } catch {
      // ignore
    }
    this.raState = RaState.IDLE
    this.raLastVk = null
    this.singleKeyPressed = false
  }

  private startRightAltHook(): void {
    if (!this.loadUiohook()) {
      console.error('right_alt hotkey unavailable (uiohook-napi failed to load) — global hotkey disabled')
      return
    }
    const hook = this.uiohook!.uIOhook
    hook.on('keydown', (e) => this.onPress(e.keycode))
    hook.on('keyup', (e) => this.onRelease(e.keycode))
    hook.start()
  }

  private startSingleKey(vk: number): void {
    if (this.loadUiohook()) {
      const hook = this.uiohook!.uIOhook
      hook.on('keydown', (e) => {
        if (e.keycode === vk && !this.singleKeyPressed) {
          this.singleKeyPressed = true
          this.events.onToggle()
        }
      })
      hook.on('keyup', (e) => {
        if (e.keycode === vk) this.singleKeyPressed = false
      })
      hook.start()
      return
    }

    // Fallback: Electron globalShortcut (registered accelerator, no repeat).
    if (this.uiohookFailed && vk >= 0x70 && vk <= 0x7b) {
      const accel = `F${vk - 0x70 + 1}`
      try {
        globalShortcut.register(accel, () => this.events.onToggle())
        return
      } catch (e) {
        console.error(`globalShortcut.register(${accel}) failed:`, String(e))
      }
    }
    console.error('Single-key hotkey unavailable (uiohook-napi failed to load)')
  }

  private loadUiohook(): boolean {
    if (this.uiohook) return true
    if (this.uiohookFailed) return false
    try {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      this.uiohook = require('uiohook-napi') as UiohookModule
      return true
    } catch (e) {
      this.uiohookFailed = true
      console.error('Failed to load uiohook-napi:', String(e))
      return false
    }
  }

  // ---- Right-Alt state machine (ported from _RightAltState) -------------------

  private onPress(vk: number): void {
    if (vk === VK_RMENU) {
      if (this.raState === RaState.IDLE) {
        this.raState = RaState.WAITING
        this.raLastVk = VK_RMENU
      }
      return
    }
    if (vk === VK_MENU || vk === VK_LMENU) {
      // Generic/Left Alt press: clear the tracker so a later left-Alt release
      // can never toggle.
      if (this.raLastVk === VK_RMENU) this.raLastVk = null
      return
    }
    if (this.raState === RaState.WAITING) {
      if (vk === VK_C) {
        this.raState = RaState.CANCELLED
        this.events.onCancel()
      } else {
        this.raState = RaState.COMBO
      }
    }
  }

  private onRelease(vk: number): void {
    const isAlt = vk === VK_RMENU || vk === VK_MENU || vk === VK_LMENU
    // Windows often delivers the Right-Alt release as generic Alt.
    const matchingToggle = isAlt && this.raLastVk === VK_RMENU

    if (!matchingToggle) {
      if (isAlt && this.raState !== RaState.IDLE) {
        // Alt released mid-gesture without a matching press: reset so the
        // machine can't get stuck in WAITING.
        this.raState = RaState.IDLE
        this.raLastVk = null
      }
      return
    }

    const state = this.raState
    this.raState = RaState.IDLE
    this.raLastVk = null

    if (state === RaState.WAITING) {
      // Pure tap.
      this.events.onToggle()
    }
    // COMBO / CANCELLED: no toggle.
  }
}
