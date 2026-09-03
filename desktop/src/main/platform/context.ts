// Cursor-context capture — port of voicetype/context.py.
// Reads the text around the cursor (Shift+Home → Ctrl+C → Shift+End → Ctrl+C)
// for context-aware polishing. Skipped entirely in terminal windows where
// Ctrl+C is SIGINT. Uses GetClipboardSequenceNumber (not a destructive
// marker) to detect whether Ctrl+C actually changed the clipboard.

import { clipboard } from 'electron'
import { sleep } from './async'
import { getWin32 } from './win32/user32'
import { sendCopyShortcut, selectToLineStart, selectToLineEnd, deselectRight, deselectLeft } from './win32/keyboard'
import { isTerminalWindow } from './win32/terminal-detect'

const MAX_CONTEXT_CHARS = 500

/**
 * Capture (before, after) line text around the cursor. Either may be empty.
 * `hwnd` is the window the user was typing into.
 */
export async function getCursorContext(hwnd: number): Promise<[string, string]> {
  if (isTerminalWindow(hwnd)) {
    console.info(`Skipping cursor context capture in terminal window (hwnd=${hwnd})`)
    return ['', '']
  }
  const api = getWin32()
  if (!api) return ['', '']

  let savedClipboard = ''
  try {
    savedClipboard = clipboard.readText() || ''
  } catch {
    // ignore
  }

  let before = ''
  let after = ''
  try {
    await selectToLineStart()
    before = await sendCopy(api)
    await deselectRight()

    await selectToLineEnd()
    after = await sendCopy(api)
    await deselectLeft()
  } catch (e) {
    console.warn('Failed to capture cursor context:', String(e))
  } finally {
    try {
      clipboard.writeText(savedClipboard)
    } catch {
      // best effort
    }
  }

  if (before.length > MAX_CONTEXT_CHARS) before = before.slice(-MAX_CONTEXT_CHARS)
  if (after.length > MAX_CONTEXT_CHARS) after = after.slice(0, MAX_CONTEXT_CHARS)
  console.info(`Cursor context: before=${before.length} chars, after=${after.length} chars`)
  return [before, after]
}

async function sendCopy(api: NonNullable<ReturnType<typeof getWin32>>): Promise<string> {
  const seqBefore = safeSeq(api)
  await sendCopyShortcut()
  const seqAfter = safeSeq(api)

  // No sequence change ⇒ the copy had no effect (unsupported editor or empty
  // selection). When the API is unavailable, read the clipboard unconditionally.
  if (seqBefore !== null && seqAfter !== null && seqBefore === seqAfter) {
    return ''
  }
  try {
    return clipboard.readText() || ''
  } catch {
    return ''
  }
}

function safeSeq(api: ReturnType<typeof getWin32>): number | null {
  try {
    return api ? api.getClipboardSequenceNumber() : null
  } catch {
    return null
  }
}

export { sleep }
