// Electron main entry — port of voicetype/__main__.py bootstrap:
// single instance, config load, tray + hotkey + windows, first-run wizard,
// autostart, API warmup, clean shutdown.

import { app, Menu, nativeTheme, session, safeStorage, clipboard } from 'electron'
import { ConfigStore } from './config/store'
import { createAtRestCrypto } from './config/crypto'
import { HistoryStore } from './services/history'
import { invalidateGlossaryCache } from './services/glossary'
import { TextTyper } from './platform/typer'
import { WindowManager } from './windows'
import { TrayController } from './tray'
import { HotkeyManager } from './hotkey/manager'
import { AudioBridge } from './audio-bridge'
import { Application } from './app'
import { registerIpc } from './ipc'

const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  // Second instance: the first instance wakes and shows its window.
  app.quit()
}

let store: ConfigStore
let windows: WindowManager
let tray: TrayController | null = null
let hotkey: HotkeyManager | null = null
let application: Application
let debouncedSaveTimer: NodeJS.Timeout | null = null

app.on('second-instance', () => {
  const cfg = store.config
  windows?.ensureFloating({ alwaysOnTop: cfg.window.always_on_top, show: true })
})

void app.whenReady().then(() => {
  if (!gotLock) return
  Menu.setApplicationMenu(null)

  // Grant microphone access to our own pages without prompting.
  const permissionHandler = (_wc: unknown, permission: string, cb: (granted: boolean) => void): void => {
    cb(permission === 'media')
  }
  session.defaultSession.setPermissionRequestHandler(permissionHandler)
  session.defaultSession.setPermissionCheckHandler(() => true)

  const userData = app.getPath('userData')
  store = new ConfigStore(userData, createAtRestCrypto(safeStorage))
  windows = new WindowManager()
  const history = new HistoryStore(userData)
  const typer = new TextTyper({ readText: () => clipboard.readText(), writeText: (s) => clipboard.writeText(s) })
  const audio = new AudioBridge(windows, {
    onChunk: (pcm) => application.onAudioChunk(pcm),
    onLevel: (level) => application.onAudioLevel(level),
    onError: (message) => console.error('audio capture:', message)
  })

  tray = new TrayController(store.config, {
    onShowWindow: () => windows.ensureFloating({ alwaysOnTop: store.config.window.always_on_top, show: true }),
    onToggleRecording: () => application.toggle(),
    onRetry: () => application.retry(),
    onOpenSettings: () => windows.ensureSettings(),
    onOpenHistory: () => windows.ensureHistory(),
    onQuit: () => quit(),
    onUpdateConfig: (mutate) => application.handleQuickUpdate(mutate)
  })

  hotkey = new HotkeyManager(store.config.hotkey.toggle_hotkey, {
    onToggle: () => application.toggle(),
    onCancel: () => application.cancel()
  })

  application = new Application({
    store,
    windows,
    tray,
    history,
    typer,
    hotkey,
    audio,
    debouncedSave: () => {
      if (debouncedSaveTimer) clearTimeout(debouncedSaveTimer)
      debouncedSaveTimer = setTimeout(() => {
        debouncedSaveTimer = null
        store.save()
      }, 500)
    }
  })

  // Hotkey binding / autostart changes re-apply live.
  application.onHotkeyOrAutostartChange = () => {
    hotkey?.stop()
    if (store.config.hotkey.toggle_enabled) {
      hotkey = new HotkeyManager(store.config.hotkey.toggle_hotkey, {
        onToggle: () => application.toggle(),
        onCancel: () => application.cancel()
      })
      hotkey.start()
    }
    applyAutostart()
  }

  registerIpc({
    app: application,
    store,
    windows,
    audio,
    history,
    typer,
    onQuit: () => quit()
  })

  // Follow OS theme changes while in "system" mode.
  nativeTheme.on('updated', () => {
    if (store.config.window.theme_mode === 'system') {
      application.broadcastConfig()
    }
  })

  application.applyLanguage()
  tray.init()
  windows.ensureAudio()
  windows.ensureOverlay()
  windows.ensureFloating({
    alwaysOnTop: store.config.window.always_on_top,
    show: store.config.window.show_on_start
  })
  if (store.config.hotkey.toggle_enabled) hotkey.start()

  // First-run wizard: no API key configured → open settings.
  if (!application.isConfiguredNow()) {
    windows.ensureSettings()
  }

  applyAutostart()
  // Warm the TLS connections a moment after startup (mirrors __main__).
  setTimeout(() => application.warmupApis(), 1500)
})

function applyAutostart(): void {
  if (!app.isPackaged) return
  try {
    app.setLoginItemSettings({ openAtLogin: store.config.window.auto_start })
  } catch (e) {
    console.warn('setLoginItemSettings failed:', String(e))
  }
}

let quitting = false

function quit(): void {
  if (quitting) return
  quitting = true
  windows?.setQuitting()
  hotkey?.stop()
  tray?.destroy()
  store?.save()
  app.quit()
}

app.on('window-all-closed', () => {
  // Tray app semantics: stay alive unless quitting explicitly.
  if (quitting) app.quit()
})

app.on('before-quit', (e) => {
  if (!quitting) {
    e.preventDefault()
    quit()
    return
  }
  try {
    invalidateGlossaryCache()
  } catch {
    // ignore
  }
})
