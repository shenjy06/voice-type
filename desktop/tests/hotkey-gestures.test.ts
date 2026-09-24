// Right-Alt gesture machine (double-tap / push-to-talk) from hotkey/manager.ts.
// The uiohook keydown/keyup handlers are not reachable in a unit test (native
// module), so the tests drive the private onPress/onRelease state machine
// directly with vitest fake timers.

import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { HotkeyManager, type HotkeyEvents } from '../src/main/hotkey/manager'

// Windows VK codes (mirroring the module's private constants).
const VK_RMENU = 0xa5 // Right Alt
const VK_MENU = 0x12 // generic Alt
const VK_C = 0x43

interface Spies {
  onToggle: ReturnType<typeof vi.fn>
  onCancel: ReturnType<typeof vi.fn>
  onRawToggle: ReturnType<typeof vi.fn>
  onPttStart: ReturnType<typeof vi.fn>
  onPttStop: ReturnType<typeof vi.fn>
  /** Drive the machine the way the hook callbacks do. */
  press(vk: number): void
  release(vk: number): void
}

function makeManager(gestures: { doubleTap?: boolean; pushToTalk?: boolean }): Spies {
  const events = {
    onToggle: vi.fn(),
    onCancel: vi.fn(),
    onRawToggle: vi.fn(),
    onPttStart: vi.fn(),
    onPttStop: vi.fn()
  } as HotkeyEvents
  const mgr = new HotkeyManager('right_alt', events, gestures)
  return {
    ...events,
    press: (vk: number) => (mgr as unknown as { onPress(v: number): void }).onPress(vk),
    release: (vk: number) => (mgr as unknown as { onRelease(v: number): void }).onRelease(vk)
  }
}

describe('Right-Alt gesture machine', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('plain tap toggles when gestures are off', () => {
    const m = makeManager({})
    m.press(VK_RMENU)
    m.release(VK_RMENU)
    expect(m.onToggle).toHaveBeenCalledTimes(1)
    expect(m.onRawToggle).not.toHaveBeenCalled()
  })

  it('fires the first tap immediately even when double-tap is enabled', () => {
    // Same semantics as the Python HotkeyManager: no 350ms delayed toggle.
    const m = makeManager({ doubleTap: true })
    m.press(VK_RMENU)
    m.release(VK_RMENU)
    expect(m.onToggle).toHaveBeenCalledTimes(1)
    expect(m.onRawToggle).not.toHaveBeenCalled()
  })

  it('a second quick tap inside the window fires raw toggle', () => {
    const m = makeManager({ doubleTap: true })
    m.press(VK_RMENU)
    m.release(VK_RMENU)
    m.press(VK_RMENU)
    m.release(VK_RMENU)
    expect(m.onRawToggle).toHaveBeenCalledTimes(1)
    // The first tap already toggled; the second became the raw gesture.
    expect(m.onToggle).toHaveBeenCalledTimes(1)
  })

  it('a slow second tap is two toggles, not a double tap', () => {
    const m = makeManager({ doubleTap: true })
    m.press(VK_RMENU)
    m.release(VK_RMENU)
    vi.advanceTimersByTime(500) // first tap's window expires
    m.press(VK_RMENU)
    m.release(VK_RMENU)
    expect(m.onRawToggle).not.toHaveBeenCalled()
    expect(m.onToggle).toHaveBeenCalledTimes(2)
  })

  it('a third quick tap starts a fresh window, not another raw toggle', () => {
    const m = makeManager({ doubleTap: true })
    m.press(VK_RMENU)
    m.release(VK_RMENU) // tap 1 → toggle
    m.press(VK_RMENU)
    m.release(VK_RMENU) // tap 2 → raw
    m.press(VK_RMENU)
    m.release(VK_RMENU) // tap 3 → toggle (fresh window)
    expect(m.onRawToggle).toHaveBeenCalledTimes(1)
    expect(m.onToggle).toHaveBeenCalledTimes(2)
  })

  it('long press starts and release ends push-to-talk', () => {
    const m = makeManager({ pushToTalk: true })
    m.press(VK_RMENU)
    expect(m.onPttStart).not.toHaveBeenCalled()
    vi.advanceTimersByTime(299)
    expect(m.onPttStart).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(m.onPttStart).toHaveBeenCalledTimes(1)
    m.release(VK_RMENU)
    expect(m.onPttStop).toHaveBeenCalledTimes(1)
    expect(m.onToggle).not.toHaveBeenCalled()
  })

  it('release before the hold threshold is a normal tap', () => {
    const m = makeManager({ pushToTalk: true })
    m.press(VK_RMENU)
    vi.advanceTimersByTime(100)
    m.release(VK_RMENU)
    expect(m.onPttStart).not.toHaveBeenCalled()
    expect(m.onToggle).toHaveBeenCalledTimes(1)
    expect(m.onPttStop).not.toHaveBeenCalled()
  })

  it('Windows reporting the release as generic Alt still ends push-to-talk', () => {
    const m = makeManager({ pushToTalk: true })
    m.press(VK_RMENU)
    vi.advanceTimersByTime(400)
    m.release(VK_MENU)
    expect(m.onPttStop).toHaveBeenCalledTimes(1)
  })

  it('a combo cancels push-to-talk candidacy', () => {
    const m = makeManager({ pushToTalk: true })
    m.press(VK_RMENU)
    m.press(VK_C)
    m.release(VK_C)
    vi.advanceTimersByTime(400)
    expect(m.onCancel).toHaveBeenCalledTimes(1)
    expect(m.onPttStart).not.toHaveBeenCalled()
    expect(m.onPttStop).not.toHaveBeenCalled()
  })
})
