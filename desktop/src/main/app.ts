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
  /**
   * True from the moment capture starts until the audio window confirms it
   * stopped. Kept separate from `state` because stopRecording() flips the
   * state to 'processing' before capture teardown finishes, and any audio
   * still in flight during that window must not be dropped.
   */
  private capturing = false

  // failure retry state (audio + context kept for tray "retry last")
  private retryState: { wav: Buffer; before: string; after: string } | null = null

  // continuous dictation session
  private continuousActive = false

  // Unsaved settings-preview overrides (null = use the stored config).
  private previewThemeMode: string | null = null
  private previewLanguage: string | null = null

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
    const mode = this.previewThemeMode ?? this.config.window.theme_mode
    if (mode === 'system') return nativeTheme.shouldUseDarkColors ? 'dark' : 'light'
    return mode === 'light' ? 'light' : 'dark'
  }

  applyLanguage(): void {
    setLanguage(this.previewLanguage ?? this.config.language, process.env.LANG || 'en-US')
    this.deps.tray.retranslate()
  }

  broadcastConfig(): void {
    this.applyLanguage()
    // A real save/broadcast always supersedes any pending preview.
    this.previewThemeMode = null
    this.previewLanguage = null
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
    // Drop anything still in flight: a cancel is an explicit discard, unlike
    // the implicit teardown in stopRecording().
    this.capturing = false
    void this.stopCapture()
    this.streamer?.abort()
    this.streamer = null
    this.streamerUsable = false
    this.pcmChunks = []
    this.pcmBytes = 0
    if (gen === this.generation) {
      this.setState('idle')
      this.hideCaption()
    }
  }

  // ---- recording ---------------------------------------------------------------

  async startRecording(): Promise<boolean> {
    if (this.state === 'recording' || this.state === 'processing') return false
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
      return false
    }
    this.capturing = true

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
    return true
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
      // Flip `capturing` only once the audio window confirms the stop, so
      // in-flight chunks keep buffering instead of being discarded.
      this.captureStopPromise = this.deps.audio
        .stop()
        .catch(() => undefined)
        .then(() => {
          this.capturing = false
        })
        .finally(() => {
          this.captureStopPromise = null
        })
    }
    return this.captureStopPromise
  }

  // ---- audio bridge callbacks ----------------------------------------------------

  onAudioChunk(pcm: Buffer): void {
    // Accept chunks while capture is live, even after state moved to
    // 'processing': stopCapture() is async, so the tail of the utterance
    // arrives after the state flip and would otherwise be truncated.
    if (!this.capturing) return
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
        // Retain the WAV *before* the network call, mirroring Python's
        // take_audio_path(): a failed transcription is precisely the case the
        // user wants to retry, so the audio must survive the failure. On a
        // retry-flow failure the existing state is kept as-is.
        this.retryState = { wav, before: this.contextBefore, after: this.contextAfter }
        this.showBubble(t('status.transcribing'))
        transcript = await new Transcriber(cfg).transcribe(wav, cfg.recording.sample_rate)
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

      // Continuous dictation: restart after a successful paste. startRecording()
      // reports whether capture actually began, so a failed restart doesn't
      // leave the flag set while the app sits in 'error'.
      if (this.continuousActive && cfg.output.continuous_mode && this.state === 'idle') {
        this.continuousActive = false // a restart re-arms it on success
        void this.startRecording().then((started) => {
          if (started) this.continuousActive = true
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
    this.pcmBytes = 0
    this.streamer = null
    this.streamerUsable = false
    if (gen !== this.generation) return
    const message = err instanceof Error ? err.message : String(err)
    console.error('Processing failed:', message)
    // Whether retry is offered depends on the retained audio, not on the
    // failure kind: streaming runs keep no WAV, batch runs do.
    const retryable = this.retryState !== null
    this.deps.tray.setRetryAvailable(retryable)
    this.hideCaption()
    this.setState('error', message)
    const hint = retryable ? t('msg.error_retry_hint') : t('msg.error_format')
    const shown = timedOut ? 'timeout' : message
    this.showToast(format(hint, { msg: shown }))
    this.deps.tray.showNotification(t('error.title'), format(hint, { msg: shown }))
  }

  /** Tray "retry last": re-run the pipeline on the retained audio. */
  retry(): void {
    const retryState = this.retryState
    // A failed run leaves the state at 'error', so both idle and error are
    // valid here — checking only 'idle' made the tray item a no-op.
    if (!retryState || (this.state !== 'idle' && this.state !== 'error')) {
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
    // Live preview without persisting. store.config must never be mutated
    // here, or the previewed value would leak into the next debounced save.
    const cfg = this.config
    const themeMode = next.theme_mode && next.theme_mode !== cfg.window.theme_mode ? next.theme_mode : null
    const language = next.language && next.language !== cfg.language ? next.language : null
    if (!themeMode && !language) return

    this.previewThemeMode = themeMode
    this.previewLanguage = language
    if (language) setLanguage(language, process.env.LANG || 'en-US')

    const preview: AppConfig = JSON.parse(JSON.stringify(cfg)) as AppConfig
    if (themeMode) preview.window.theme_mode = themeMode
    if (language) preview.language = language
    this.deps.windows.broadcast('evt', { type: 'config', config: preview, theme: this.resolvedTheme() })
    if (language) this.deps.tray.retranslate()
  }

  /** Drop any unsaved preview overrides (called on save and on dialog cancel). */
  clearPreview(): void {
    if (!this.previewThemeMode && !this.previewLanguage) return
    this.previewThemeMode = null
    this.previewLanguage = null
    this.broadcastConfig()
  }

  handleQuickUpdate(mutate: (config: AppConfig) => void): void {
    mutate(this.config)
    // Cheap and content-keyed, so invalidating unconditionally is safe and
    // keeps a future quick-toggle for glossary/runtime fields from serving
    // stale compiled patterns.
    invalidateGlossaryCache()
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
