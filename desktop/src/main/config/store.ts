// Config store — port of src/voicetype/config.py with identical JSON schema.
// Storage lives under a caller-supplied base dir (Electron userData), so this
// module stays electron-free and unit-testable.

import { mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync, existsSync, renameSync } from 'node:fs'
import { join } from 'node:path'
import type { AppConfig, ConfigSummary, GlossaryEntry } from '../../shared/types'
import { DEFAULT_BASE_URL } from '../../shared/types'
import {
  createAtRestCrypto,
  decryptWithPassword,
  encryptWithPassword,
  isEncryptedEnvelope,
  type AtRestCrypto
} from './crypto'

export class EncryptedConfigError extends Error {}
export class InvalidPasswordError extends Error {}
export class InvalidProfileNameError extends Error {}

// ---- defaults (field-for-field from config.py) -------------------------------

export function defaultConfig(): AppConfig {
  return {
    language: 'auto',
    polish: {
      base_url: DEFAULT_BASE_URL,
      api_key: '',
      model: 'gpt-4o',
      enabled: true,
      style: 'default'
    },
    asr: {
      base_url: DEFAULT_BASE_URL,
      api_key: '',
      model: 'whisper-1',
      language: 'auto',
      streaming_enabled: false
    },
    recording: {
      sample_rate: 16000,
      device: null,
      device_id: null,
      denoise_enabled: false,
      denoise_strength: 'medium',
      vad_enabled: false,
      vad_silence_duration_ms: 1500,
      vad_threshold: 0.02
    },
    output: {
      paste_delay_ms: 120,
      auto_paste: true,
      paste_mode: 'auto',
      continuous_mode: false
    },
    glossary: [],
    window: {
      show_on_start: true,
      always_on_top: true,
      auto_start: false,
      theme_mode: 'dark'
    },
    hotkey: {
      toggle_enabled: true,
      toggle_hotkey: 'right_alt'
    }
  }
}

const str = (v: unknown, fallback: string): string => (typeof v === 'string' ? v : fallback)
// Python's str() coercion in from_dict keeps numeric/boolean scalars.
const coerceStr = (v: unknown): string => {
  if (typeof v === 'string') return v
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  return ''
}
const bool = (v: unknown, fallback: boolean): boolean => (typeof v === 'boolean' ? v : fallback)
const num = (v: unknown, fallback: number): number => (typeof v === 'number' && Number.isFinite(v) ? v : fallback)

function section(data: unknown): Record<string, unknown> {
  return typeof data === 'object' && data !== null ? (data as Record<string, unknown>) : {}
}

/**
 * Rebuild an AppConfig from arbitrary JSON, keeping only known fields
 * (forward/backward compatibility) — port of AppConfig.from_dict.
 */
export function configFromDict(data: unknown): AppConfig {
  const d = section(data)
  const rec = section(d.recording)
  const def = defaultConfig()

  const polishData = 'polish' in d ? section(d.polish) : section(d.api)
  const glossary: GlossaryEntry[] = Array.isArray(d.glossary)
    ? (d.glossary as unknown[])
        .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
        .map((item) => ({
          source: coerceStr(item.source),
          replacement: coerceStr(item.replacement)
        }))
    : []

  return {
    language: str(d.language, def.language),
    polish: {
      base_url: str(polishData.base_url, def.polish.base_url),
      api_key: str(polishData.api_key, ''),
      model: str(polishData.model, def.polish.model),
      enabled: bool(polishData.enabled, def.polish.enabled),
      style: str(polishData.style, def.polish.style)
    },
    asr: {
      base_url: str(section(d.asr).base_url, def.asr.base_url),
      api_key: str(section(d.asr).api_key, ''),
      model: str(section(d.asr).model, def.asr.model),
      language: str(section(d.asr).language, def.asr.language),
      streaming_enabled: bool(section(d.asr).streaming_enabled, def.asr.streaming_enabled)
    },
    recording: {
      sample_rate: num(rec.sample_rate, def.recording.sample_rate),
      device: typeof rec.device === 'number' ? rec.device : null,
      device_id: str(rec.device_id, '') || null,
      denoise_enabled: bool(rec.denoise_enabled, def.recording.denoise_enabled),
      denoise_strength: str(rec.denoise_strength, def.recording.denoise_strength),
      vad_enabled: bool(rec.vad_enabled, def.recording.vad_enabled),
      vad_silence_duration_ms: num(rec.vad_silence_duration_ms, def.recording.vad_silence_duration_ms),
      vad_threshold: num(rec.vad_threshold, def.recording.vad_threshold)
    },
    output: {
      paste_delay_ms: num(section(d.output).paste_delay_ms, def.output.paste_delay_ms),
      auto_paste: bool(section(d.output).auto_paste, def.output.auto_paste),
      paste_mode: str(section(d.output).paste_mode, def.output.paste_mode),
      continuous_mode: bool(section(d.output).continuous_mode, def.output.continuous_mode)
    },
    glossary,
    window: {
      show_on_start: bool(section(d.window).show_on_start, def.window.show_on_start),
      always_on_top: bool(section(d.window).always_on_top, def.window.always_on_top),
      auto_start: bool(section(d.window).auto_start, def.window.auto_start),
      theme_mode: str(section(d.window).theme_mode, def.window.theme_mode)
    },
    hotkey: {
      toggle_enabled: bool(section(d.hotkey).toggle_enabled, def.hotkey.toggle_enabled),
      toggle_hotkey: str(section(d.hotkey).toggle_hotkey, def.hotkey.toggle_hotkey)
    }
  }
}

export function isConfigured(config: AppConfig): boolean {
  return Boolean(config.asr.api_key || config.polish.api_key)
}

export function isDefaultConfig(config: AppConfig): boolean {
  if (isConfigured(config)) return false
  const def = defaultConfig()
  return JSON.stringify(config) === JSON.stringify(def)
}

export function configSummary(config: AppConfig): ConfigSummary {
  const extras: string[] = []
  if (config.recording.denoise_enabled) extras.push(`denoise(${config.recording.denoise_strength})`)
  if (config.recording.vad_enabled) extras.push(`VAD(${config.recording.vad_silence_duration_ms}ms)`)
  return {
    stt: `${config.asr.model} (${config.asr.language})${config.asr.streaming_enabled ? ' +streaming' : ''}`,
    polish: config.polish.enabled ? `${config.polish.model} [${config.polish.style}]` : 'disabled',
    recording: extras.join(', '),
    output: `paste=${config.output.paste_mode}${config.output.auto_paste ? ' auto' : ''}`,
    glossary: config.glossary.length ? `${config.glossary.length} terms` : '',
    window: `top=${config.window.always_on_top} startup=${config.window.auto_start}`
  }
}

// ---- disk persistence --------------------------------------------------------

export class ConfigStore {
  readonly configDir: string
  private readonly configFile: string
  private readonly profilesDir: string
  private readonly activeProfileFile: string
  private readonly atRest: AtRestCrypto
  private _config: AppConfig
  private lastSavedJson = ''

  constructor(
    configDir: string,
    atRest: AtRestCrypto = createAtRestCrypto(null)
  ) {
    this.configDir = configDir
    this.configFile = join(configDir, 'config.json')
    this.profilesDir = join(configDir, 'profiles')
    this.activeProfileFile = join(configDir, 'active_profile')
    this.atRest = atRest
    this._config = this.load()
  }

  get config(): AppConfig {
    return this._config
  }

  /** Replace the in-memory config (deep copy semantics via JSON). */
  replaceWith(other: AppConfig): void {
    this._config = JSON.parse(JSON.stringify(other)) as AppConfig
  }

  /** Serialize with API keys at-rest encrypted (safeStorage/DPAPI). */
  toStorableDict(config: AppConfig = this._config): Record<string, unknown> {
    const dict = JSON.parse(JSON.stringify(config)) as AppConfig & Record<string, unknown>
    dict.polish = { ...config.polish, api_key: this.atRest.encrypt(config.polish.api_key) }
    dict.asr = { ...config.asr, api_key: this.atRest.encrypt(config.asr.api_key) }
    return dict as unknown as Record<string, unknown>
  }

  private load(): AppConfig {
    try {
      const raw = readFileSync(this.configFile, 'utf-8')
      const data = JSON.parse(raw) as Record<string, unknown>
      const config = configFromDict(data)
      config.polish.api_key = this.atRest.decrypt(config.polish.api_key)
      config.asr.api_key = this.atRest.decrypt(config.asr.api_key)
      return config
    } catch {
      return defaultConfig()
    }
  }

  /** Atomic write; skips when content is unchanged (mirrors config.save). */
  save(): void {
    const json = JSON.stringify(this.toStorableDict(), null, 2)
    if (json === this.lastSavedJson) return
    try {
      if (existsSync(this.configFile) && readFileSync(this.configFile, 'utf-8') === json) {
        this.lastSavedJson = json
        return
      }
    } catch {
      // unreadable existing file — proceed with the write
    }
    mkdirSync(this.configDir, { recursive: true })
    const tmp = this.configFile + '.tmp'
    writeFileSync(tmp, json, 'utf-8')
    renameSync(tmp, this.configFile)
    this.lastSavedJson = json
  }

  // ---- export / import -------------------------------------------------------

  exportTo(path: string, password: string | null = null): void {
    // Exports are portable: plaintext keys like the Python version, unless the
    // user supplied a password (then the portable Fernet envelope is used).
    const plain = JSON.stringify(this._config)
    const content = password ? JSON.stringify(encryptWithPassword(plain, password)) : JSON.stringify(this._config, null, 2)
    mkdirSync(join(path, '..'), { recursive: true })
    const tmp = path + '.tmp'
    writeFileSync(tmp, content, 'utf-8')
    renameSync(tmp, path)
  }

  /** Read + decrypt a config file. Throws EncryptedConfigError/InvalidPasswordError. */
  importFrom(path: string, password: string | null = null): AppConfig {
    const raw = readFileSync(path, 'utf-8')
    let data: unknown
    try {
      data = JSON.parse(raw)
    } catch (e) {
      throw new Error(`invalid JSON: ${String(e)}`)
    }
    if (isEncryptedEnvelope(data)) {
      if (password === null) throw new EncryptedConfigError(path)
      const plain = decryptWithPassword(data, password)
      if (plain === null) throw new InvalidPasswordError(path)
      data = JSON.parse(plain)
    }
    const config = configFromDict(data)
    config.polish.api_key = this.atRest.decrypt(config.polish.api_key)
    config.asr.api_key = this.atRest.decrypt(config.asr.api_key)
    return config
  }

  // ---- named profiles ----------------------------------------------------------

  listProfiles(): string[] {
    try {
      return readdirSync(this.profilesDir)
        .filter((f) => f.endsWith('.json'))
        .map((f) => f.slice(0, -5))
        .sort()
    } catch {
      return []
    }
  }

  saveProfile(name: string, config: AppConfig = this._config): void {
    validateProfileName(name)
    mkdirSync(this.profilesDir, { recursive: true })
    const plain = JSON.stringify(config)
    writeFileSync(join(this.profilesDir, `${name}.json`), plain, 'utf-8')
  }

  loadProfile(name: string): AppConfig {
    validateProfileName(name)
    return this.importFrom(join(this.profilesDir, `${name}.json`))
  }

  deleteProfile(name: string): void {
    validateProfileName(name)
    try {
      rmSync(join(this.profilesDir, `${name}.json`), { force: true })
    } catch {
      // already gone
    }
    if (this.getActiveProfile() === name) this.setActiveProfile(null)
  }

  getActiveProfile(): string | null {
    try {
      const name = readFileSync(this.activeProfileFile, 'utf-8').trim()
      return name || null
    } catch {
      return null
    }
  }

  setActiveProfile(name: string | null): void {
    mkdirSync(this.configDir, { recursive: true })
    if (name === null) {
      try {
        rmSync(this.activeProfileFile, { force: true })
      } catch {
        // ignore
      }
    } else {
      writeFileSync(this.activeProfileFile, name, 'utf-8')
    }
  }
}

export function validateProfileName(name: string): void {
  const stripped = name.trim()
  if (!stripped) throw new InvalidProfileNameError('profile name is empty')
  if (stripped === '.' || stripped === '..') throw new InvalidProfileNameError(`invalid profile name: ${stripped}`)
  if (stripped.includes('\\') || stripped.includes('/')) {
    throw new InvalidProfileNameError(`profile name must not contain path separators: ${stripped}`)
  }
  if (stripped !== name) throw new InvalidProfileNameError('profile name must not have surrounding whitespace')
}
