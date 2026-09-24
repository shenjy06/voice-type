// Global hotkey manager — port of voicetype/ui/system_tray.py HotkeyManager.
//
// right_alt binding: a quick tap of Right Alt toggles recording; Right Alt+C
// cancels; Right Alt + any other key is a combo and does nothing. Two optional
// gestures extend the tap (both off by default, gated by config): a double
// tap within 350ms fires onRawToggle (record without polishing), and holding
// the key for 300ms fires onPttStart/onPttStop (push-to-talk). A 5-state
// machine (IDLE/WAITING/COMBO/CANCELLED/PTT) survives Windows reporting
// Right-Alt release as generic Alt. Left Alt is ignored entirely.
//
// Single-key bindings (F9 etc.) use a low-level hook with repeat suppression.
// Uses uiohook-napi; if the native module can't load, falls back to Electron
// globalShortcut for plain vk bindings (right_alt is unavailable then).

import { globalShortcut } from 'electron'

export interface HotkeyEvents {
  onToggle: () => void
  onCancel: () => void
  /** right_alt double-tap: record one take with polishing skipped. */
  onRawToggle?: () => void
  /** right_alt long-press push-to-talk: hold starts, release stops. */
  onPttStart?: () => void
  onPttStop?: () => void
}

export interface HotkeyGestures {
  /** Enable the double-tap → onRawToggle gesture (config hotkey.double_tap_action). */
  doubleTap?: boolean
  /** Enable the long-press → push-to-talk gesture (config hotkey.push_to_talk). */
  pushToTalk?: boolean
}

// Windows VK codes (libuiohook vcodes mirror VK codes on Windows).
const VK_RMENU = 0xa5 // Right Alt
const VK_MENU = 0x12 // generic Alt
const VK_LMENU = 0xa4 // Left Alt
const VK_C = 0x43

// Gesture thresholds (kept in sync with the Python HotkeyManager).
const DOUBLE_TAP_WINDOW_MS = 350
const PTT_HOLD_MS = 300

const enum RaState {
  IDLE = 0,
  WAITING,
  COMBO,
  CANCELLED,
  PTT
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
  private readonly gestures: Required<HotkeyGestures>
  private uiohook: UiohookModule | null = null
  private uiohookFailed = false
  private running = false

  // Right-Alt state machine.
  private raState: RaState = RaState.IDLE
  private raLastVk: number | null = null
  // Long-press detection: fires onPttStart when the key is still held.
  private pttTimer: NodeJS.Timeout | null = null
  // Double-tap detection: timestamp of the last completed tap release. The
  // first tap fires onToggle immediately (same semantics as the Python
  // port); a second tap released within the window fires onRawToggle.
  private raLastTapAt = 0
  // Single-key repeat suppression.
  private singleKeyPressed = false

  constructor(hotkey: string, events: HotkeyEvents, gestures: HotkeyGestures = {}) {
    this.hotkey = hotkey
    this.events = events
    this.gestures = { doubleTap: gestures.doubleTap ?? false, pushToTalk: gestures.pushToTalk ?? false }
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
    this.raLastTapAt = 0
    this.clearPttTimer()
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

  private clearPttTimer(): void {
    if (this.pttTimer) {
      clearTimeout(this.pttTimer)
      this.pttTimer = null
    }
  }

  private onPress(vk: number): void {
    if (vk === VK_RMENU) {
      if (this.raState === RaState.IDLE) {
        this.raState = RaState.WAITING
        this.raLastVk = VK_RMENU
        if (this.gestures.pushToTalk) {
          this.pttTimer = setTimeout(() => {
            this.pttTimer = null
            if (this.raState === RaState.WAITING) {
              this.raState = RaState.PTT
              this.events.onPttStart?.()
            }
          }, PTT_HOLD_MS)
        }
      }
      return
    }
    if (vk === VK_MENU || vk === VK_LMENU) {
      // Generic/Left Alt press: clear the tracker so a later left-Alt release
      // can never toggle. During PTT the tracker must survive, or the
      // Right-Alt release would no longer match and onPttStop would be lost.
      if (this.raState === RaState.WAITING && this.raLastVk === VK_RMENU) this.raLastVk = null
      return
    }
    if (this.raState === RaState.WAITING) {
      // A combo ends any long-press candidacy.
      this.clearPttTimer()
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
        // machine can't get stuck — but don't strand an active PTT take.
        const wasPtt = this.raState === RaState.PTT
        this.raState = RaState.IDLE
        this.raLastVk = null
        this.clearPttTimer()
        if (wasPtt) this.events.onPttStop?.()
      }
      return
    }

    const state = this.raState
    this.raState = RaState.IDLE
    this.raLastVk = null
    this.clearPttTimer()

    if (state === RaState.PTT) {
      // Long-press release ends push-to-talk; never counts as a tap.
      this.events.onPttStop?.()
      return
    }

    if (state === RaState.WAITING) {
      // Pure tap: fires onToggle immediately. When double-tap is enabled, a
      // second tap released within the window becomes the raw gesture
      // instead (matching the Python HotkeyManager semantics).
      const now = Date.now()
      if (this.gestures.doubleTap && now - this.raLastTapAt <= DOUBLE_TAP_WINDOW_MS) {
        this.raLastTapAt = 0
        this.events.onRawToggle?.()
        return
      }
      this.raLastTapAt = now
      this.events.onToggle()
    }
    // COMBO / CANCELLED: no toggle.
  }
}
