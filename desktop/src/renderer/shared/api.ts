// Renderer-side typed access to the preload bridge.
import type { EvtMessage } from '../../preload/index'
import type { AppConfig, HistoryEntry } from '../../shared/types'

export type { EvtMessage }

export interface ImportResult {
  ok: boolean
  config?: AppConfig
  summary?: Record<string, string>
  canceled?: boolean
  needsPassword?: boolean
  invalidPassword?: boolean
  error?: string
}

export interface VoiceTypeApi {
  getConfig(): Promise<AppConfig>
  saveConfig(next: AppConfig): Promise<void>
  previewSettings(next: { theme_mode?: string; language?: string }): Promise<void>
  exportConfig(password: string | null): Promise<{ ok: boolean; path?: string; canceled?: boolean; error?: string }>
  importConfig(password?: string): Promise<ImportResult>

  listProfiles(): Promise<{ profiles: string[]; active: string | null }>
  saveProfile(name: string): Promise<{ ok: boolean; profiles?: string[]; active?: string | null; error?: string }>
  loadProfile(name: string): Promise<{ ok: boolean; config?: AppConfig; error?: string }>
  deleteProfile(name: string): Promise<{ ok: boolean; profiles?: string[]; active?: string | null; error?: string }>

  fetchModels(kind: 'asr' | 'polish'): Promise<{ ok: boolean; models?: string[]; error?: string }>

  historyList(): Promise<HistoryEntry[]>
  historyClear(): Promise<void>
  historyCopy(text: string): Promise<void>
  historyPaste(text: string): Promise<void>

  exportGlossaryCsv(
    entries: Array<{ source: string; replacement: string }>
  ): Promise<{ ok: boolean; canceled?: boolean; error?: string }>
  importGlossaryCsv(): Promise<{
    ok: boolean
    entries?: Array<{ source: string; replacement: string }>
    canceled?: boolean
    error?: string
  }>

  toggleRecording(): Promise<void>
  cancelRecording(): Promise<void>
  showSettings(): Promise<void>
  showFloating(): Promise<void>
  quitApp(): Promise<void>
  warmupApis(): Promise<void>

  captureStarted(): Promise<void>
  captureError(message: string): Promise<void>
  captureStopped(): Promise<void>
  sendChunk(pcm: ArrayBuffer): void
  sendLevel(level: number): void

  onEvt(listener: (msg: EvtMessage) => void): () => void
}

declare global {
  interface Window {
    api: VoiceTypeApi
  }
}

export {}
