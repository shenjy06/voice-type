// Single preload shared by all windows. Exposes a typed, promise-based API
// surface plus an event bus — no Node primitives leak into the renderers.

import { contextBridge, ipcRenderer } from 'electron'

export interface EvtMessage {
  type: string
  // config events
  config?: unknown
  theme?: 'dark' | 'light'
  // state events
  state?: 'idle' | 'recording' | 'processing' | 'error'
  error?: string
  startedAt?: number
  level?: number
  // overlay events
  text?: string
  message?: string
  // audio control events
  sampleRate?: number
  deviceId?: string | null
}

const api = {
  // ---- config ----
  getConfig: (): Promise<unknown> => ipcRenderer.invoke('config:get'),
  saveConfig: (next: unknown): Promise<void> => ipcRenderer.invoke('config:save', next),
  previewSettings: (next: { theme_mode?: string; language?: string }): Promise<void> =>
    ipcRenderer.invoke('config:preview', next),
  exportConfig: (password: string | null): Promise<{ ok: boolean; path?: string; canceled?: boolean; error?: string }> =>
    ipcRenderer.invoke('config:export', password),
  importConfig: (
    password?: string
  ): Promise<{
    ok: boolean
    config?: unknown
    summary?: unknown
    canceled?: boolean
    needsPassword?: boolean
    invalidPassword?: boolean
    error?: string
  }> => ipcRenderer.invoke('config:import', password ? { password } : {}),

  // ---- profiles ----
  listProfiles: (): Promise<{ profiles: string[]; active: string | null }> => ipcRenderer.invoke('profiles:list'),
  saveProfile: (name: string): Promise<{ ok: boolean; profiles?: string[]; active?: string | null; error?: string }> =>
    ipcRenderer.invoke('profiles:save', name),
  loadProfile: (name: string): Promise<{ ok: boolean; config?: unknown; error?: string }> =>
    ipcRenderer.invoke('profiles:load', name),
  deleteProfile: (name: string): Promise<{ ok: boolean; profiles?: string[]; active?: string | null; error?: string }> =>
    ipcRenderer.invoke('profiles:delete', name),

  // ---- models ----
  fetchModels: (kind: 'asr' | 'polish'): Promise<{ ok: boolean; models?: string[]; error?: string }> =>
    ipcRenderer.invoke('models:fetch', kind),

  // ---- history ----
  historyList: (): Promise<Array<{ created_at: string; text: string }>> => ipcRenderer.invoke('history:list'),
  historyClear: (): Promise<void> => ipcRenderer.invoke('history:clear'),
  historyCopy: (text: string): Promise<void> => ipcRenderer.invoke('history:copy', text),
  historyPaste: (text: string): Promise<void> => ipcRenderer.invoke('history:paste', text),

  // ---- glossary CSV ----
  exportGlossaryCsv: (
    entries: Array<{ source: string; replacement: string }>
  ): Promise<{ ok: boolean; canceled?: boolean; error?: string }> =>
    ipcRenderer.invoke('glossary:export-csv', entries),
  importGlossaryCsv: (): Promise<{
    ok: boolean
    entries?: Array<{ source: string; replacement: string }>
    canceled?: boolean
    error?: string
  }> => ipcRenderer.invoke('glossary:import-csv'),

  // ---- control ----
  toggleRecording: (): Promise<void> => ipcRenderer.invoke('ui:toggle'),
  cancelRecording: (): Promise<void> => ipcRenderer.invoke('ui:cancel'),
  showSettings: (): Promise<void> => ipcRenderer.invoke('ui:show-settings'),
  showFloating: (): Promise<void> => ipcRenderer.invoke('ui:show-floating'),
  quitApp: (): Promise<void> => ipcRenderer.invoke('app:quit'),
  warmupApis: (): Promise<void> => ipcRenderer.invoke('warmup:apis'),

  // ---- audio window protocol ----
  captureStarted: (): Promise<void> => ipcRenderer.invoke('audio:capture-started'),
  captureError: (message: string): Promise<void> => ipcRenderer.invoke('audio:capture-error', message),
  captureStopped: (): Promise<void> => ipcRenderer.invoke('audio:capture-stopped'),
  sendChunk: (pcm: ArrayBuffer): void => ipcRenderer.send('audio:chunk', pcm),
  sendLevel: (level: number): void => ipcRenderer.send('audio:level', level),

  // ---- event bus ----
  onEvt: (listener: (msg: EvtMessage) => void): (() => void) => {
    const wrapped = (_e: unknown, msg: EvtMessage): void => listener(msg)
    ipcRenderer.on('evt', wrapped)
    return () => ipcRenderer.removeListener('evt', wrapped)
  }
}

contextBridge.exposeInMainWorld('api', api)

export type Api = typeof api
