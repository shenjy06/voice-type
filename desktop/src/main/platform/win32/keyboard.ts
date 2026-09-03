// Low-level keyboard injection helpers (keybd_event pacing identical to the
// Python implementation in typer.py / context.py).

import { sleep } from '../async'
import { getWin32, KEYEVENTF_KEYUP, VK_CONTROL, VK_SHIFT } from './user32'

export async function keyTap(vk: number, downMs = 20): Promise<boolean> {
  const api = getWin32()
  if (!api) return false
  if (!api.keybdEvent(vk, 0, 0)) return false
  await sleep(downMs)
  return api.keybdEvent(vk, 0, KEYEVENTF_KEYUP) !== 0
}

export async function keyDown(vk: number): Promise<boolean> {
  const api = getWin32()
  if (!api) return false
  return api.keybdEvent(vk, 0, 0) !== 0
}

export async function keyUp(vk: number): Promise<boolean> {
  const api = getWin32()
  if (!api) return false
  return api.keybdEvent(vk, 0, KEYEVENTF_KEYUP) !== 0
}

/** Ctrl+C — used by cursor-context capture. */
export async function sendCopyShortcut(): Promise<void> {
  await keyDown(VK_CONTROL)
  await sleep(20)
  await keyTap(0x43, 20) // VK_C
  await keyUp(VK_CONTROL)
  await sleep(150)
}

/** Shift+Home / Shift+End selection helpers for context capture. */
export async function selectToLineStart(): Promise<void> {
  await keyDown(VK_SHIFT)
  await sleep(10)
  await keyTap(0x24, 10) // VK_HOME
  await keyUp(VK_SHIFT)
  await sleep(50)
}

export async function selectToLineEnd(): Promise<void> {
  await keyDown(VK_SHIFT)
  await sleep(10)
  await keyTap(0x23, 10) // VK_END
  await keyUp(VK_SHIFT)
  await sleep(50)
}

export async function deselectRight(): Promise<void> {
  await keyTap(0x27, 10) // VK_RIGHT
  await sleep(20)
}

export async function deselectLeft(): Promise<void> {
  await keyTap(0x25, 10) // VK_LEFT
  await sleep(20)
}
