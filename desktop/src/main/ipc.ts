// IPC registration — every renderer↔main channel in one place.
// Invoke channels return values; the 'evt' channel carries broadcasts and the
// audio control protocol (see audio-bridge.ts).

import { ipcMain, dialog, clipboard, app, BrowserWindow } from 'electron'
import { join } from 'node:path'
import { readFileSync, writeFileSync } from 'node:fs'
import type { Application } from './app'
import type { AudioBridge } from './audio-bridge'
import type { ConfigStore } from './config/store'
import { InvalidPasswordError, EncryptedConfigError } from './config/store'
import type { WindowManager } from './windows'
import { fetchModels, Transcriber } from './services/asr'
import { TextPolisher } from './services/polisher'
import { HistoryStore } from './services/history'
import { TextTyper } from './platform/typer'
import { configSummary } from './config/store'
import { getForegroundWindow } from './platform/win32/windows'
import type { AppConfig } from '../shared/types'

interface IpcDeps {
  app: Application
  store: ConfigStore
  windows: WindowManager
  audio: AudioBridge
  history: HistoryStore
  typer: TextTyper
  onQuit(): void
}

export function registerIpc(deps: IpcDeps): void {
  const { app: application, store, windows, audio, history, typer } = deps

  ipcMain.handle('config:get', () => store.config)

  ipcMain.handle('config:save', (_e, next: AppConfig) => {
    application.saveConfig(next)
  })

  ipcMain.handle('config:preview', (_e, next: { theme_mode?: string; language?: string }) => {
    application.previewSettings(next)
  })

  ipcMain.handle('config:export', async (e, password: string | null) => {
    const win = windowFromSender(e.sender.id, windows)
    const result = await dialog.showSaveDialog(win, {
      title: 'Export Config',
      defaultPath: join(app.getPath('documents'), 'voice-type-config.json'),
      filters: [{ name: 'JSON', extensions: ['json'] }]
    })
    if (result.canceled || !result.filePath) return { ok: false, canceled: true }
    try {
      store.exportTo(result.filePath, password || null)
      return { ok: true, path: result.filePath }
    } catch (err) {
      return { ok: false, error: String(err) }
    }
  })

  // Remember the picked import path so a password retry doesn't re-open the
  // file dialog (mirrors the Python dialog flow).
  let importPath: string | null = null

  ipcMain.handle('config:import', async (e, opts: { password?: string } = {}) => {
    const win = windowFromSender(e.sender.id, windows)
    if (!importPath) {
      const result = await dialog.showOpenDialog(win, {
        title: 'Import Config',
        filters: [{ name: 'JSON', extensions: ['json'] }],
        properties: ['openFile']
      })
      if (result.canceled || !result.filePaths.length) {
        return { ok: false, canceled: true }
      }
      importPath = result.filePaths[0]
    }
    try {
      const config = store.importFrom(importPath, opts.password ?? null)
      const summary = configSummary(config)
      importPath = null
      return { ok: true, config, summary }
    } catch (err) {
      if (err instanceof EncryptedConfigError) {
        return { ok: false, needsPassword: true }
      }
      if (err instanceof InvalidPasswordError) {
        return { ok: false, invalidPassword: true }
      }
      importPath = null
      return { ok: false, error: String(err) }
    }
  })

  ipcMain.handle('profiles:list', () => ({ profiles: store.listProfiles(), active: store.getActiveProfile() }))

  ipcMain.handle('profiles:save', (_e, name: string) => {
    try {
      store.saveProfile(name)
      store.setActiveProfile(name)
      return { ok: true, profiles: store.listProfiles(), active: store.getActiveProfile() }
    } catch (err) {
      return { ok: false, error: String(err) }
    }
  })

  ipcMain.handle('profiles:load', (_e, name: string) => {
    try {
      return { ok: true, config: store.loadProfile(name) }
    } catch (err) {
      return { ok: false, error: String(err) }
    }
  })

  ipcMain.handle('profiles:delete', (_e, name: string) => {
    try {
      store.deleteProfile(name)
      return { ok: true, profiles: store.listProfiles(), active: store.getActiveProfile() }
    } catch (err) {
      return { ok: false, error: String(err) }
    }
  })

  ipcMain.handle('models:fetch', async (_e, kind: 'asr' | 'polish') => {
    const cfg = store.config
    const section = kind === 'asr' ? cfg.asr : cfg.polish
    try {
      const models = await fetchModels(section.api_key, section.base_url)
      return { ok: true, models }
    } catch (err) {
      return { ok: false, error: String(err) }
    }
  })

  ipcMain.handle('history:list', () => application.historyEntries())

  // ---- glossary CSV import/export (UTF-8 BOM, matching the Python app) ------

  ipcMain.handle('glossary:export-csv', async (e, entries: Array<{ source: string; replacement: string }>) => {
    const win = windowFromSender(e.sender.id, windows)
    const result = await dialog.showSaveDialog(win, {
      title: 'Export Glossary CSV',
      defaultPath: join(app.getPath('documents'), 'glossary.csv'),
      filters: [{ name: 'CSV', extensions: ['csv'] }]
    })
    if (result.canceled || !result.filePath) return { ok: false, canceled: true }
    try {
      const lines = ['source,replacement']
      for (const entry of entries) {
        lines.push(csvEscape(entry.source) + ',' + csvEscape(entry.replacement))
      }
      writeFileSync(result.filePath, '\ufeff' + lines.join('\r\n') + '\r\n', 'utf-8')
      return { ok: true }
    } catch (err) {
      return { ok: false, error: String(err) }
    }
  })

  ipcMain.handle('glossary:import-csv', async (e) => {
    const win = windowFromSender(e.sender.id, windows)
    const result = await dialog.showOpenDialog(win, {
      title: 'Import Glossary CSV',
      filters: [{ name: 'CSV', extensions: ['csv'] }],
      properties: ['openFile']
    })
    if (result.canceled || !result.filePaths.length) return { ok: false, canceled: true }
    try {
      const raw = readFileSync(result.filePaths[0], 'utf-8').replace(/^\ufeff/, '')
      const entries: Array<{ source: string; replacement: string }> = []
      for (const row of parseCsv(raw)) {
        if (row.length < 2) continue
        const [source, replacement] = row
        if (source.toLowerCase() === 'source' && replacement.toLowerCase() === 'replacement') continue
        if (!source.trim() || !replacement.trim()) continue
        entries.push({ source: source.trim(), replacement: replacement.trim() })
      }
      if (!entries.length) return { ok: false, error: 'empty' }
      return { ok: true, entries }
    } catch (err) {
      return { ok: false, error: String(err) }
    }
  })

  ipcMain.handle('history:clear', () => {
    history.clear()
  })

  ipcMain.handle('history:copy', (_e, text: string) => {
    clipboard.writeText(text)
  })

  ipcMain.handle('history:paste', async (_e, text: string) => {
    const hwnd = getForegroundWindow()
    await typer.outputText(text, hwnd, {
      pasteDelayMs: store.config.output.paste_delay_ms,
      pasteMode: store.config.output.paste_mode
    })
  })

  // ---- control channels (floating window buttons, windows, quit) -------------

  ipcMain.handle('ui:toggle', () => application.toggle())
  ipcMain.handle('ui:cancel', () => application.cancel())
  ipcMain.handle('ui:show-settings', () => {
    windows.ensureSettings()
  })
  ipcMain.handle('ui:show-floating', () => {
    const cfg = store.config
    windows.ensureFloating({ alwaysOnTop: cfg.window.always_on_top, show: true })
  })
  ipcMain.handle('app:quit', () => deps.onQuit())

  // ---- warmup (mirrors _warmup_api_connections) -------------------------------

  ipcMain.handle('warmup:apis', () => {
    if (store.config.asr.api_key) void new Transcriber(store.config).warmup()
    if (store.config.polish.enabled && store.config.polish.api_key) {
      void new TextPolisher(store.config).warmup()
    }
  })

  // ---- audio window protocol ---------------------------------------------------

  ipcMain.handle('audio:capture-started', () => audio.handleCaptureStarted())
  ipcMain.handle('audio:capture-error', (_e, message: string) => audio.handleCaptureError(message))
  ipcMain.handle('audio:capture-stopped', () => audio.handleCaptureStopped())
  ipcMain.on('audio:chunk', (_e, pcm: ArrayBuffer) => audio.handleChunk(pcm))
  ipcMain.on('audio:level', (_e, level: number) => audio.handleLevel(level))
}

function windowFromSender(senderId: number, windows: WindowManager): Electron.BrowserWindow {
  const win = BrowserWindow.getAllWindows().find((w) => w.webContents.id === senderId)
  return win ?? windows.ensureSettings()
}

function csvEscape(value: string): string {
  if (/[",\r\n]/.test(value)) return '"' + value.replace(/"/g, '""') + '"'
  return value
}

/** Minimal CSV parser handling quoted fields (RFC 4180 subset). */
function parseCsv(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let inQuotes = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"'
          i++
        } else {
          inQuotes = false
        }
      } else {
        field += c
      }
    } else if (c === '"') {
      inQuotes = true
    } else if (c === ',') {
      row.push(field)
      field = ''
    } else if (c === '\r') {
      // skip; handled with \n
    } else if (c === '\n') {
      row.push(field)
      rows.push(row)
      row = []
      field = ''
    } else {
      field += c
    }
  }
  if (field || row.length) {
    row.push(field)
    rows.push(row)
  }
  return rows
}
