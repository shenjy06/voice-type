// Foreground-window management — port of voicetype/window_manager.py.
// Cascade of strategies to work around Windows foreground-stealing limits:
// 1. AttachThreadInput + SetForegroundWindow
// 2. Alt tap + SetForegroundWindow
// 3. BringWindowToTop + Alt tap + SetForegroundWindow
//
// The whole sequence is async (paced with sleeps) and runs off the Electron
// main loop, mirroring how the Python app performed injection on a worker
// thread with time.sleep pacing.

import { sleep } from '../async'
import { getWin32, VK_MENU, KEYEVENTF_KEYUP } from './user32'

function tapAlt(): boolean {
  const api = getWin32()
  if (!api) return false
  const down = api.keybdEvent(VK_MENU, 0, 0)
  const up = api.keybdEvent(VK_MENU, 0, KEYEVENTF_KEYUP)
  return down !== 0 || up !== 0
}

export function getForegroundWindow(): number {
  return getWin32()?.getForegroundWindow() ?? 0
}

export async function setForegroundWindow(hwnd: number): Promise<boolean> {
  const api = getWin32()
  if (!api || !hwnd) return false
  if (!api.isWindow(hwnd)) return false

  // Strategy 1: attach input queues, then SetForegroundWindow.
  const ourTid = api.getCurrentThreadId()
  const pidBuf = new Uint32Array(1)
  const targetTid = api.getWindowThreadProcessId(hwnd, pidBuf)
  let attached = false
  try {
    if (ourTid !== targetTid && targetTid !== 0) {
      attached = api.attachThreadInput(targetTid, ourTid, true) !== 0
    }
    await sleep(10)
    if (api.setForegroundWindow(hwnd)) return true
  } catch {
    // fall through
  } finally {
    if (attached) api.detachThreadInput(targetTid, ourTid)
  }

  // Strategy 2: Alt tap + SetForegroundWindow.
  if (tapAlt()) {
    await sleep(20)
    if (api.setForegroundWindow(hwnd)) return true
  }

  // Strategy 3: BringWindowToTop (keeps maximized state) + Alt tap + SFW.
  try {
    api.bringWindowToTop(hwnd)
  } catch {
    // ignore
  }
  if (tapAlt()) {
    await sleep(20)
    if (api.setForegroundWindow(hwnd)) return true
  }
  return false
}
