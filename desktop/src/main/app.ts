// Application orchestrator — port of the Application class in
// voicetype/__main__.py. Owns the recording state machine
// (IDLE → RECORDING → PROCESSING → DONE/ERROR), audio buffering, the
// streaming/batch ASR switch, glossary+polish pipeline, history, clipboard
// output, continuous dictation, retry, VAD auto-stop, and the 300s watchdog.

import { clipboard, nativeTheme } from 'electron'
import type { AppConfig, HistoryEntry, RecorderState } from '../shared/types'
import { setLanguage, t, format } from '../shared/i18n'
import { paletteForMode } from '../shared/theme'
import type { ConfigStore } from './config/store'
import { isConfigured } from './config/store'
import { HistoryStore } from './services/history'
import { TextTyper } from './platform/typer'
import { getForegroundWindow } from './platform/win32/windows'
import { getCursorContext } from './platform/context'
import { Transcriber } from './services/asr'
import { StreamingTranscriber } from './services/streaming-asr'
import { TextPolisher } from './services/polisher'
import { applyGlossary, invalidateGlossaryCache } from './services/glossary'
import { encodeWavPcm16 } from './audio/wav'
import { VadDetector } from './audio/vad'
import type { WindowManager } from './windows'
import type { TrayController } from './tray'
import type { HotkeyManager } from './hotkey/manager'

const WATCHDOG_MS = 300_000

type AudioWindowBridge = {
  /** Tell the audio renderer to start/stop capture. Resolves to success. */
  start(opts: { sampleRate: number; deviceId: string | null }): Promise<boolean>
  stop(): Promise<void>
  /** Feed a PCM16 chunk received from the audio renderer. */
  onChunk(pcm: Buffer): void
  onLevel(level: number): void
  onError(message: string): void
}

export interface AppDeps {
  store: ConfigStore
  windows: WindowManager
  tray: TrayController
  history: HistoryStore
  typer: TextTyper
  hotkey: HotkeyManager
  audio: AudioWindowBridge
  /** Persist quick settings with a 500ms debounce. */
  debouncedSave(): void
}

export class Application {
  private readonly deps: AppDeps
  private state: RecorderState = 'idle'
  private recordingStartedAt = 0

  // per-recording session data
  private savedHwnd = 0
  private pcmChunks: Buffer[] = []
  private pcmBytes = 0
  private contextBefore = ''
  private contextAfter = ''
  private streamer: StreamingTranscriber | null = null
  private streamerUsable = false
  private vad: VadDetector | null = null
  private captureStopPromise: Promise<void> | null = null

  // failure retry state (audio + context kept for tray "retry last")
  private retryState: { wav: Buffer; before: string; after: string } | null = null

  // continuous dictation session
  private continuousActive = false

  private watchdog: NodeJS.Timeout | null = null
  private generation = 0 // guards async processing against stale completions

  constructor(deps: AppDeps) {
    this.deps = deps
  }

  get config(): AppConfig {
    return this.deps.store.config
  }

  // ---- theme / language ------------------------------------------------------

  resolvedTheme(): 'dark' | 'light' {
    const mode = this.config.window.theme_mode
    if (mode === 'system') return nativeTheme.shouldUseDarkColors ? 'dark' : 'light'
    return mode === 'light' ? 'light' : 'dark'
  }

  applyLanguage(): void {
    setLanguage(this.config.language, process.env.LANG || 'en-US')
    this.deps.tray.retranslate()
  }

  broadcastConfig(): void {
    this.applyLanguage()
    this.deps.windows.broadcast('evt', { type: 'config', config: this.config, theme: this.resolvedTheme() })
    this.deps.tray.applyConfig(this.config)
    this.applyHotkeyAndAutostart()
  }

  applyHotkeyAndAutostart(): void {
    // Hotkey binding changes require a manager restart (handled in index.ts
    // via the returned callback); autostart is applied directly.
    this.onHotkeyOrAutostartChange?.()
  }

  onHotkeyOrAutostartChange?: () => void

  // ---- state machine -----------------------------------------------------------

  getState(): RecorderState {
    return this.state
  }

  private setState(state: RecorderState, error?: string): void {
    this.state = state
    this.deps.tray.setState(state)
    this.deps.windows.send('floating', 'evt', {
      type: 'state',
      state,
      error,
      startedAt: state === 'recording' ? this.recordingStartedAt : 0
    })
    this.updateBubbleForState(state, error)
  }

  private updateBubbleForState(state: RecorderState, error?: string): void {
    if (state === 'recording') {
      this.showBubble(t('status.recording'))
    } else if (state === 'processing') {
      this.showBubble(t('status.transcribing'))
    } else if (state === 'error' && error) {
      this.showToast(format(t('msg.error_format'), { msg: error }))
    } else if (state === 'idle') {
      this.hideBubble()
    }
  }

  toggle(): void {
    if (this.state === 'recording') {
      void this.stopRecording()
    } else if (this.state === 'idle' || this.state === 'error') {
      void this.startRecording()
    }
    // PROCESSING: ignore (mirrors RecordingController).
  }

  cancel(): void {
    if (this.state !== 'recording' && this.state !== 'processing') return
    const gen = ++this.generation
    this.continuousActive = false
    this.retryState = null
    this.deps.tray.setRetryAvailable(false)
    void this.stopCapture()
    this.streamer?.abort()
    this.streamer = null
    this.pcmChunks = []
    this.pcmBytes = 0
    if (gen === this.generation) {
      this.setState('idle')
      this.hideCaption()
    }
  }

  // ---- recording ---------------------------------------------------------------

  async startRecording(): Promise<void> {
    if (this.state === 'recording' || this.state === 'processing') return
    const cfg = this.config
    this.savedHwnd = getForegroundWindow()
    this.pcmChunks = []
    this.pcmBytes = 0
    this.contextBefore = ''
    this.contextAfter = ''
    this.recordingStartedAt = Date.now()

    this.vad = new VadDetector({
      enabled: cfg.recording.vad_enabled,
      threshold: cfg.recording.vad_threshold,
      silenceDurationMs: cfg.recording.vad_silence_duration_ms,
      onSilence: () => {
        // Audio-thread analogue: VAD fires from the level IPC path.
        if (this.state === 'recording') void this.stopRecording()
      }
    })

    const ok = await this.deps.audio.start({
      sampleRate: cfg.recording.sample_rate,
      deviceId: cfg.recording.device_id
    })
    if (!ok) {
      this.showToast(t('error.no_audio'))
      this.setState('error', t('error.no_audio_detail'))
      return
    }

    if (cfg.output.continuous_mode) this.continuousActive = true

    // Streaming ASR (non-fatal on failure — fall back to file mode).
    this.streamer = null
    this.streamerUsable = false
    if (cfg.asr.streaming_enabled && cfg.asr.api_key) {
      const streamer = new StreamingTranscriber({
        apiKey: cfg.asr.api_key,
        model: cfg.asr.model,
        language: cfg.asr.language,
        sampleRate: cfg.recording.sample_rate,
        onTextUpdate: (text) => {
          this.deps.windows.send('overlay', 'evt', { type: 'caption', text })
        },
        onError: (message) => console.warn('streaming:', message)
      })
      const started = await streamer.start()
      if (started) {
        this.streamer = streamer
        this.streamerUsable = true
        this.showCaption(t('caption.listening'))
      } else {
        this.showToast(t('msg.streaming_fallback'))
      }
    }

    this.setState('recording')

    // Context capture mirrors __main__: background task, doesn't block.
    void getCursorContext(this.savedHwnd).then(([before, after]) => {
      this.contextBefore = before
      this.contextAfter = after
    })
  }

  async stopRecording(): Promise<void> {
    if (this.state !== 'recording') return
    this.setState('processing')
    const gen = ++this.generation

    await this.stopCapture()
    if (gen !== this.generation) return // cancelled while stopping

    const streamer = this.streamer
    this.streamer = null
    void this.processRecording(gen, streamer)
  }

  private stopCapture(): Promise<void> {
    if (!this.captureStopPromise) {
      this.captureStopPromise = this.deps.audio.stop().finally(() => {
        this.captureStopPromise = null
      })
    }
    return this.captureStopPromise
  }

  // ---- audio bridge callbacks ----------------------------------------------------

  onAudioChunk(pcm: Buffer): void {
    if (this.state !== 'recording') return
    this.pcmChunks.push(pcm)
    this.pcmBytes += pcm.length
    if (this.streamerUsable && this.streamer) {
      this.streamer.sendAudio(pcm)
    }
  }

  onAudioLevel(level: number): void {
    if (this.state === 'recording') {
      this.deps.windows.send('floating', 'evt', { type: 'level', level })
      this.vad?.update(level, Date.now())
    }
  }

  // ---- processing pipeline ---------------------------------------------------------

  private async processRecording(
    gen: number,
    streamer: StreamingTranscriber | null,
    retry?: { wav: Buffer; before: string; after: string }
  ): Promise<void> {
    const cfg = this.config
    const startedAt = Date.now()

    // Watchdog: never let processing hang the UI (mirrors the 300s timer).
    this.watchdog = setTimeout(() => {
      this.onProcessingError(gen, new Error('timeout'), true)
    }, WATCHDOG_MS)

    try {
      let transcript: string
      if (retry) {
        transcript = await new Transcriber(cfg).transcribe(retry.wav, cfg.recording.sample_rate)
      } else if (streamer) {
        this.showBubble(t('status.transcribing'))
        transcript = await streamer.finalize(10_000)
      } else {
        this.showBubble(t('status.saving'))
        const wav = encodeWavPcm16(Buffer.concat(this.pcmChunks), cfg.recording.sample_rate)
        this.pcmChunks = []
        if (wav.length <= 44) {
          throw new Error(t('error.no_audio_detail'))
        }
        this.showBubble(t('status.transcribing'))
        transcript = await new Transcriber(cfg).transcribe(wav, cfg.recording.sample_rate)
        // Keep the WAV for the tray retry path (freed on success).
        this.retryState = { wav, before: this.contextBefore, after: this.contextAfter }
      }

      if (gen !== this.generation) return
      if (!transcript.trim()) throw new Error(t('error.no_audio_detail'))

      let text = applyGlossary(transcript, cfg.glossary)

      if (cfg.polish.enabled && cfg.polish.api_key) {
        this.showBubble(t('status.polishing'))
        const polisher = new TextPolisher(cfg)
        text = await polisher.polish(text, this.contextBefore, this.contextAfter)
      }
      if (gen !== this.generation) return

      this.deps.history.add(text)
      await this.outputText(text)
      if (gen !== this.generation) return

      clearTimeout(this.watchdog)
      this.watchdog = null
      this.retryState = null
      this.deps.tray.setRetryAvailable(false)
      this.hideCaption()
      this.setState('idle')

      // Continuous dictation: restart after a successful paste.
      if (this.continuousActive && cfg.output.continuous_mode && this.state === 'idle') {
        this.continuousActive = false // session restart clears the flag
        void this.startRecording().then(() => {
          this.continuousActive = true
        })
      }
      void startedAt
    } catch (err) {
      this.onProcessingError(gen, err, false, streamer)
    }
  }

  private onProcessingError(gen: number, err: unknown, timedOut: boolean, streamer?: StreamingTranscriber | null): void {
    if (this.watchdog) {
      clearTimeout(this.watchdog)
      this.watchdog = null
    }
    streamer?.abort()
    this.pcmChunks = []
    if (gen !== this.generation) return
    const message = err instanceof Error ? err.message : String(err)
    console.error('Processing failed:', message)
    this.deps.tray.setRetryAvailable(this.retryState !== null)
    this.hideCaption()
    this.setState('error', message)
    if (timedOut) {
      this.showToast(format(t('msg.error_retry_hint'), { msg: 'timeout' }))
    } else {
      this.showToast(format(t('msg.error_retry_hint'), { msg: message }))
    }
    this.deps.tray.showNotification(t('error.title'), format(t('msg.error_retry_hint'), { msg: message }))
  }

  /** Tray "retry last": re-run the pipeline on the retained audio. */
  retry(): void {
    const retryState = this.retryState
    if (!retryState || this.state !== 'idle') {
      this.showToast(t('msg.retry_unavailable'))
      return
    }
    this.setState('processing')
    const gen = ++this.generation
    void this.processRecording(gen, null, retryState)
  }

  // ---- output ---------------------------------------------------------------------

  private async outputText(text: string): Promise<void> {
    const cfg = this.config
    if (cfg.output.auto_paste) {
      const ok = await this.deps.typer.outputText(text, this.savedHwnd, {
        pasteDelayMs: cfg.output.paste_delay_ms,
        pasteMode: cfg.output.paste_mode
      })
      if (!ok) this.showToast(t('msg.paste_failed_copied'))
    } else {
      clipboard.writeText(text)
    }
  }

  // ---- overlay helpers ---------------------------------------------------------------

  showBubble(text: string): void {
    this.deps.windows.ensureOverlay().showInactive()
    this.deps.windows.send('overlay', 'evt', { type: 'bubble', text })
  }

  hideBubble(): void {
    this.deps.windows.send('overlay', 'evt', { type: 'bubble-hide' })
  }

  showCaption(text: string): void {
    this.deps.windows.ensureOverlay().showInactive()
    this.deps.windows.send('overlay', 'evt', { type: 'caption', text })
  }

  hideCaption(): void {
    this.deps.windows.send('overlay', 'evt', { type: 'caption-hide' })
  }

  showToast(message: string): void {
    this.deps.windows.ensureOverlay().showInactive()
    this.deps.windows.send('overlay', 'evt', { type: 'toast', message })
  }

  // ---- config mutation entry points -----------------------------------------------------

  saveConfig(next: AppConfig): void {
    this.deps.store.replaceWith(next)
    this.deps.store.save()
    invalidateGlossaryCache()
    this.broadcastConfig()
  }

  previewSettings(next: { theme_mode?: string; language?: string }): void {
    // Live preview without persisting; cancel re-broadcasts the stored config.
    const cfg = this.config
    let changed = false
    if (next.theme_mode && next.theme_mode !== cfg.window.theme_mode) {
      cfg.window.theme_mode = next.theme_mode
      changed = true
    }
    if (next.language && next.language !== cfg.language) {
      cfg.language = next.language
      changed = true
    }
    if (changed) {
      this.applyLanguage()
      this.deps.windows.broadcast('evt', { type: 'config', config: cfg, theme: this.resolvedTheme() })
    }
  }

  handleQuickUpdate(mutate: (config: AppConfig) => void): void {
    mutate(this.config)
    this.deps.debouncedSave()
    this.broadcastConfig()
  }

  isConfiguredNow(): boolean {
    return isConfigured(this.config)
  }

  historyEntries(): HistoryEntry[] {
    return this.deps.history.loadRecent()
  }

  warmupApis(): void {
    if (!this.config.asr.api_key) return
    void new Transcriber(this.config).warmup()
    if (this.config.polish.enabled && this.config.polish.api_key) {
      void new TextPolisher(this.config).warmup()
    }
  }
}
