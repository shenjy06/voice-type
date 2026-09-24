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
  VK_RETURN,
  VK_SHIFT,
  VK_TAB,
  VK_V,
  VK_Z
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

  // Voice-command key actions: newline=Shift+Enter, enter=Return,
  // undo=Ctrl+Z, tab=Tab (same mapping as the Python typer).
  private static readonly ACTION_KEYS: Record<string, { modifiers: number[]; key: number }> = {
    newline: { modifiers: [VK_SHIFT], key: VK_RETURN },
    enter: { modifiers: [], key: VK_RETURN },
    undo: { modifiers: [VK_CONTROL], key: VK_Z },
    tab: { modifiers: [], key: VK_TAB }
  }

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
   * Send a voice-command key action (newline/enter/undo/tab) into the
   * previously-foreground window. Returns false for unknown actions or when
   * the injection fails.
   */
  async sendActionKey(action: string, savedHwnd: number): Promise<boolean> {
    const spec = TextTyper.ACTION_KEYS[action]
    if (!spec) return false
    const run = this.chain.then(() => this._sendActionKey(spec, savedHwnd))
    this.chain = run.catch(() => undefined)
    return run
  }

  private async _sendActionKey(
    spec: { modifiers: number[]; key: number },
    savedHwnd: number
  ): Promise<boolean> {
    if (savedHwnd) {
      const restored = await setForegroundWindow(savedHwnd)
      if (!restored) console.warn(`Failed to restore foreground window (hwnd=${savedHwnd})`)
    }
    await sleep(50)

    const api = getWin32()
    if (!api) return false
    try {
      // Same modifier-clearing / Esc-tap prelude as the paste path: the Alt
      // tap from the foreground restore leaves menu bars armed in some apps.
      for (const vk of [VK_MENU, VK_SHIFT, VK_CONTROL]) {
        api.keybdEvent(vk, 0, KEYEVENTF_KEYUP)
      }
      api.keybdEvent(VK_ESCAPE, 0, 0)
      api.keybdEvent(VK_ESCAPE, 0, KEYEVENTF_KEYUP)
      await sleep(20)

      for (const mod of spec.modifiers) {
        if (!api.keybdEvent(mod, 0, 0)) return false
        await sleep(20)
      }
      if (!api.keybdEvent(spec.key, 0, 0)) return false
      await sleep(20)
      if (!api.keybdEvent(spec.key, 0, KEYEVENTF_KEYUP)) return false
      await sleep(20)
      for (const mod of [...spec.modifiers].reverse()) {
        if (!api.keybdEvent(mod, 0, KEYEVENTF_KEYUP)) return false
        await sleep(20)
      }
      return true
    } catch (e) {
      console.warn('Action key injection raised:', String(e))
      return false
    }
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
