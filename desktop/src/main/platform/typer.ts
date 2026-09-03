// Text output via clipboard paste — port of voicetype/typer.py.
// Restores the saved foreground window, preserves/restores the clipboard, and
// sends Ctrl+V (or Ctrl+Shift+V for terminals) via keybd_event with all the
// modifier-clearing / Esc-tapping quirks of the original.

import { sleep } from './async'
import {
  getWin32,
  KEYEVENTF_KEYUP,
  VK_CONTROL,
  VK_ESCAPE,
  VK_MENU,
  VK_SHIFT,
  VK_V
} from './win32/user32'
import { setForegroundWindow } from './win32/windows'
import { isTerminalWindow } from './win32/terminal-detect'
import { PASTE_MODE_CLIPBOARD, PASTE_MODE_CTRL_SHIFT_V, PASTE_MODE_CTRL_V } from '../../shared/types'

export interface ClipboardAdapter {
  readText(): string
  writeText(text: string): void
}

export interface OutputOptions {
  pasteDelayMs: number
  pasteMode: string
}

export class TextTyper {
  private readonly clipboard: ClipboardAdapter
  // Serialize clipboard operations so the delayed restore cannot race a new
  // copy (Windows clipboard access is not thread-safe).
  private chain: Promise<unknown> = Promise.resolve()

  constructor(clipboard: ClipboardAdapter) {
    this.clipboard = clipboard
  }

  /**
   * Paste `text` into the previously-foreground window.
   * Returns true when the text was pasted (or intentionally clipboard-only).
   */
  async outputText(text: string, savedHwnd: number, opts: OutputOptions): Promise<boolean> {
    if (!text) return false
    // Chain invocations so concurrent outputs can't interleave clipboard ops.
    const run = this.chain.then(() => this._output(text, savedHwnd, opts))
    this.chain = run.catch(() => undefined)
    return run
  }

  private async _output(text: string, savedHwnd: number, opts: OutputOptions): Promise<boolean> {
    if (savedHwnd) {
      const restored = await setForegroundWindow(savedHwnd)
      if (!restored) console.warn(`Failed to restore foreground window (hwnd=${savedHwnd})`)
    }
    await sleep(opts.pasteDelayMs)

    let originalClipboard: string | null = null
    try {
      originalClipboard = this.clipboard.readText()
    } catch (e) {
      console.warn('Failed to read clipboard:', String(e))
    }

    try {
      this.clipboard.writeText(text)
    } catch (e) {
      console.warn('Clipboard copy failed:', String(e))
      if (originalClipboard !== null && originalClipboard !== text) {
        try {
          this.clipboard.writeText(originalClipboard)
        } catch {
          // best effort
        }
      }
      return false
    }

    if (opts.pasteMode === PASTE_MODE_CLIPBOARD) {
      return true
    }

    const useTerminalPaste = await this.useTerminalPaste(opts.pasteMode, savedHwnd)
    const success = await this.sendPaste(useTerminalPaste)
    if (!success) {
      console.error(`Paste shortcut injection failed (mode=${opts.pasteMode})`)
      return false
    }

    // Restore the original clipboard after the target app has read it.
    if (originalClipboard !== null && originalClipboard !== text) {
      void sleep(1000).then(() => {
        try {
          this.clipboard.writeText(originalClipboard as string)
        } catch (e) {
          console.warn('Failed to restore clipboard:', String(e))
        }
      })
    }
    return true
  }

  private async useTerminalPaste(pasteMode: string, hwnd: number): Promise<boolean> {
    if (pasteMode === PASTE_MODE_CTRL_SHIFT_V) return true
    if (pasteMode === PASTE_MODE_CTRL_V) return false
    // auto (or unknown): terminals need Ctrl+Shift+V.
    return isTerminalWindow(hwnd)
  }

  /**
   * Send the paste shortcut. Before the keys, all modifiers are force-released
   * and Esc is tapped: the Alt-tap used to restore the foreground window
   * leaves menu bars activated in some apps, where "V" would trigger a menu
   * mnemonic instead of pasting. keybd_event's return value is checked so a
   * UIPI-blocked paste surfaces as failure ("copied instead" toast).
   */
  private async sendPaste(useTerminalPaste: boolean): Promise<boolean> {
    const api = getWin32()
    if (!api) return false
    try {
      // Best-effort cleanup — never blocks the actual paste.
      for (const vk of [VK_MENU, VK_SHIFT, VK_CONTROL]) {
        api.keybdEvent(vk, 0, KEYEVENTF_KEYUP)
      }
      api.keybdEvent(VK_ESCAPE, 0, 0)
      api.keybdEvent(VK_ESCAPE, 0, KEYEVENTF_KEYUP)
      await sleep(20)

      if (!api.keybdEvent(VK_CONTROL, 0, 0)) return false
      await sleep(20)
      if (useTerminalPaste) {
        if (!api.keybdEvent(VK_SHIFT, 0, 0)) return false
        await sleep(20)
      }
      if (!api.keybdEvent(VK_V, 0, 0)) return false
      await sleep(20)
      if (!api.keybdEvent(VK_V, 0, KEYEVENTF_KEYUP)) return false
      await sleep(20)
      if (useTerminalPaste) {
        if (!api.keybdEvent(VK_SHIFT, 0, KEYEVENTF_KEYUP)) return false
        await sleep(20)
      }
      if (!api.keybdEvent(VK_CONTROL, 0, KEYEVENTF_KEYUP)) return false
      return true
    } catch (e) {
      console.warn('Paste key injection raised:', String(e))
      return false
    }
  }
}
