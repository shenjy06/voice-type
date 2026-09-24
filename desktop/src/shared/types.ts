// Shared types + constants mirroring the Python AppConfig schema (config.json)
// so exported/imported config files stay interoperable between both apps.
// Field names MUST match src/voicetype/config.py exactly.

export const DEFAULT_BASE_URL = 'https://api.openai.com/v1'
export const DEFAULT_STREAMING_BASE_URL = 'wss://dashscope.aliyuncs.com/api-ws/v1/realtime'

export interface PolishApiConfig {
  base_url: string
  api_key: string
  model: string
  enabled: boolean
  style: string
}

export interface AsrConfig {
  base_url: string
  api_key: string
  model: string
  language: string
  streaming_enabled: boolean
}

export interface RecordingConfig {
  sample_rate: number
  /** Python-side sounddevice int index — kept for schema parity, unused here. */
  device: number | null
  /** Electron-side WebRTC deviceId (Electron-specific extension). */
  device_id: string | null
  denoise_enabled: boolean
  denoise_strength: string
  vad_enabled: boolean
  vad_silence_duration_ms: number
  vad_threshold: number
  archive_audio: boolean
  archive_retention_days: number
}

export interface OutputConfig {
  paste_delay_ms: number
  auto_paste: boolean
  paste_mode: string
  continuous_mode: boolean
}

export interface GlossaryEntry {
  source: string
  replacement: string
}

export interface WindowConfig {
  show_on_start: boolean
  always_on_top: boolean
  auto_start: boolean
  theme_mode: string
  /** Show the live caption panel while streaming ASR is active. */
  show_caption: boolean
}

export interface HotkeyConfig {
  toggle_enabled: boolean
  toggle_hotkey: string
  /** Double-tap gesture on right_alt: 'none' | 'raw' (skip polish once). */
  double_tap_action: 'none' | 'raw'
  /** Long-press gesture on right_alt: hold-to-talk. */
  push_to_talk: boolean
}

export interface VoiceCommandItem {
  phrase: string
  action: string
}

export interface CommandsConfig {
  enabled: boolean
  items: VoiceCommandItem[]
}

export interface SceneRule {
  match: string
  profile: string
}

export interface ScenesConfig {
  enabled: boolean
  rules: SceneRule[]
}

export interface AppConfig {
  language: string
  polish: PolishApiConfig
  asr: AsrConfig
  recording: RecordingConfig
  output: OutputConfig
  glossary: GlossaryEntry[]
  window: WindowConfig
  hotkey: HotkeyConfig
  commands: CommandsConfig
  scenes: ScenesConfig
}

// ---- enum-ish constants (mirror voicetype/constants.py) ---------------------

export const PASTE_MODES = ['auto', 'ctrl_v', 'ctrl_shift_v', 'clipboard'] as const
export const PASTE_MODE_AUTO = 'auto'
export const PASTE_MODE_CTRL_V = 'ctrl_v'
export const PASTE_MODE_CTRL_SHIFT_V = 'ctrl_shift_v'
export const PASTE_MODE_CLIPBOARD = 'clipboard'

export const ASR_LANGUAGES = ['auto', 'zh', 'en', 'ja', 'ko', 'fr', 'de', 'es'] as const

export const POLISH_STYLES = ['default', 'formal', 'casual', 'concise'] as const

export const THEME_MODES = ['dark', 'light', 'system'] as const

export const LANGUAGES = ['auto', 'en', 'zh'] as const

// ---- runtime state shared over IPC ------------------------------------------

export type RecorderState = 'idle' | 'recording' | 'processing' | 'error'

export interface OutputDevice {
  deviceId: string
  label: string
  isDefault: boolean
}

export interface HistoryEntry {
  created_at: string
  text: string
  audio_path?: string
  duration_ms?: number
  processing_ms?: number
}

export interface HistoryStats {
  total: number
  total_chars: number
  total_duration_ms: number
  today_count: number
  today_chars: number
  week_count: number
  week_chars: number
  est_minutes_saved: number
}

export interface ConfigSummary {
  stt: string
  polish: string
  recording: string
  output: string
  glossary: string
  window: string
}
