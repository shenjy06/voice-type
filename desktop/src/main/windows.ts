// Window management for the five renderer views.
// floating  — frameless, always-on-top, draggable recording widget
// overlay   — transparent click-through layer hosting bubble/caption/toast
// settings  — normal window (hidden, not destroyed, on close)
// history   — normal window (hidden, not destroyed, on close)
// audio     — hidden persistent capture window

import { BrowserWindow, screen } from 'electron'
import { join } from 'node:path'

export type WindowName = 'floating' | 'overlay' | 'settings' | 'history' | 'audio'

function preloadPath(): string {
  return join(__dirname, '../preload/index.js')
}

function htmlPath(name: WindowName): string {
  // electron-vite outputs renderer entries next to out/renderer/<name>/index.html
  if (process.env.ELECTRON_RENDERER_URL) {
    return `${process.env.ELECTRON_RENDERER_URL}/${name}/index.html`
  }
  return join(__dirname, '../renderer', name, 'index.html')
}

const DEFAULT_PRELOAD = { preload: preloadPath(), contextIsolation: true, nodeIntegration: false }

export class WindowManager {
  private windows = new Map<WindowName, BrowserWindow>()
  private quitting = false

  setQuitting(): void {
    this.quitting = true
  }

  get(name: WindowName): BrowserWindow | undefined {
    return this.windows.get(name)
  }

  ensureFloating(opts: { alwaysOnTop: boolean; show: boolean }): BrowserWindow {
    let win = this.windows.get('floating')
    if (win && !win.isDestroyed()) {
      win.setAlwaysOnTop(opts.alwaysOnTop, 'screen-saver')
      if (opts.show) win.show()
      return win
    }
    const { workArea } = screen.getPrimaryDisplay()
    win = new BrowserWindow({
      width: 260,
      height: 156,
      x: workArea.x + workArea.width - 260 - 32,
      y: workArea.y + workArea.height - 156 - 72,
      show: false,
      frame: false,
      resizable: false,
      maximizable: false,
      fullscreenable: false,
      skipTaskbar: true,
      alwaysOnTop: opts.alwaysOnTop,
      transparent: true,
      hasShadow: false,
      webPreferences: DEFAULT_PRELOAD
    })
    win.setMenu(null)
    win.loadURL(htmlPath('floating'))
    win.on('close', (e) => {
      // Closing the floating widget hides it (app keeps running in tray).
      if (!this.quitting) {
        e.preventDefault()
        win?.hide()
      }
    })
    this.windows.set('floating', win)
    if (opts.show) {
      win.once('ready-to-show', () => win?.show())
    }
    return win
  }

  ensureOverlay(): BrowserWindow {
    let win = this.windows.get('overlay')
    if (win && !win.isDestroyed()) return win
    const { workArea } = screen.getPrimaryDisplay()
    win = new BrowserWindow({
      width: 560,
      height: 260,
      x: workArea.x + Math.floor((workArea.width - 560) / 2),
      y: workArea.y + workArea.height - 260 - 48,
      show: false,
      frame: false,
      resizable: false,
      maximizable: false,
      fullscreenable: false,
      skipTaskbar: true,
      alwaysOnTop: true,
      transparent: true,
      hasShadow: false,
      focusable: false,
      webPreferences: { ...DEFAULT_PRELOAD, backgroundThrottling: false }
    })
    win.setMenu(null)
    // Purely informational layer: never take focus or steal clicks.
    win.setIgnoreMouseEvents(true, { forward: true })
    win.loadURL(htmlPath('overlay'))
    this.windows.set('overlay', win)
    return win
  }

  ensureSettings(): BrowserWindow {
    let win = this.windows.get('settings')
    if (win && !win.isDestroyed()) {
      win.show()
      win.focus()
      return win
    }
    win = new BrowserWindow({
      width: 600,
      height: 740,
      show: false,
      title: 'Voice Type — Settings',
      minWidth: 560,
      minHeight: 620,
      webPreferences: DEFAULT_PRELOAD
    })
    win.setMenu(null)
    win.loadURL(htmlPath('settings'))
    win.on('close', (e) => {
      if (!this.quitting) {
        e.preventDefault()
        win?.hide()
      }
    })
    this.windows.set('settings', win)
    return win
  }

  ensureHistory(): BrowserWindow {
    let win = this.windows.get('history')
    if (win && !win.isDestroyed()) {
      win.show()
      win.focus()
      return win
    }
    const { workArea } = screen.getPrimaryDisplay()
    win = new BrowserWindow({
      width: 640,
      height: 420,
      x: workArea.x + Math.floor((workArea.width - 640) / 2),
      y: workArea.y + Math.floor((workArea.height - 420) / 2),
      show: false,
      title: 'Voice Type — History',
      minWidth: 480,
      minHeight: 320,
      webPreferences: DEFAULT_PRELOAD
    })
    win.setMenu(null)
    win.loadURL(htmlPath('history'))
    win.on('close', (e) => {
      if (!this.quitting) {
        e.preventDefault()
        win?.hide()
      }
    })
    this.windows.set('history', win)
    return win
  }

  ensureAudio(): BrowserWindow {
    let win = this.windows.get('audio')
    if (win && !win.isDestroyed()) return win
    win = new BrowserWindow({
      width: 1,
      height: 1,
      show: false,
      skipTaskbar: true,
      webPreferences: { ...DEFAULT_PRELOAD, backgroundThrottling: false }
    })
    win.loadURL(htmlPath('audio'))
    this.windows.set('audio', win)
    return win
  }

  broadcast(channel: string, payload?: unknown): void {
    for (const win of this.windows.values()) {
      if (win.isDestroyed()) continue
      win.webContents.send(channel, payload)
    }
  }

  send(name: WindowName, channel: string, payload?: unknown): void {
    const win = this.windows.get(name)
    if (win && !win.isDestroyed()) {
      win.webContents.send(channel, payload)
    }
  }

  destroyAll(): void {
    for (const win of this.windows.values()) {
      if (!win.isDestroyed()) win.destroy()
    }
    this.windows.clear()
  }
}
