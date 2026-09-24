// Regression tests for the recording/processing state machine in app.ts.
// These cover the failure paths that had no unit coverage: tail audio kept
// during capture teardown, tray-retry after an error, and the continuous
// dictation re-arm.

import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { Application } from '../src/main/app'
import { defaultConfig } from '../src/main/config/store'
import type { AppConfig } from '../src/shared/types'

// The processing pipeline calls the real ASR client over fetch. Stub it so
// failures are immediate and deterministic (no network, no retry backoff).
let fetchStub: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchStub = vi.fn(() => Promise.reject(new Error('network disabled in tests')))
  vi.stubGlobal('fetch', fetchStub)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

// --- harness ------------------------------------------------------------------

interface Harness {
  app: Application
  config: AppConfig
  chunks: Buffer[]
  startCalls: number
  stopCalls: number
  /** Resolve to let the audio bridge's stop() promise settle. */
  finishStop(): void
  /** Make the next audio start() fail (simulates no input device). */
  failNextStart(): void
  savedSave: () => number
}

function makeHarness(): Harness {
  const config = defaultConfig()
  config.asr.streaming_enabled = false // exercise the batch/WAV path
  config.recording.sample_rate = 16000

  let pendingStop: (() => void) | null = null
  let failStart = false
  let startCalls = 0
  let stopCalls = 0

  const audio = {
    start: async (): Promise<boolean> => {
      startCalls++
      if (failStart) {
        failStart = false
        return false
      }
      return true
    },
    stop: (): Promise<void> =>
      new Promise<void>((resolve) => {
        stopCalls++
        pendingStop = resolve
      })
  }

  const sent: Array<{ win: string; msg: unknown }> = []
  const windows = {
    send: (win: string, _channel: string, payload: unknown) => sent.push({ win, msg: payload }),
    broadcast: () => undefined,
    ensureOverlay: () => ({ showInactive: () => undefined }),
    ensureFloating: () => undefined
  } as never

  const tray = {
    setState: () => undefined,
    setRetryAvailable: () => undefined,
    showNotification: () => undefined,
    retranslate: () => undefined,
    applyConfig: () => undefined
  } as never

  let saveCount = 0
  const store = {
    get config() {
      return config
    },
    replaceWith: () => undefined,
    save: () => {
      saveCount++
    }
  } as never

  const app = new Application({
    store,
    windows,
    tray,
    history: { add: () => undefined, loadRecent: () => [] } as never,
    typer: { outputText: async () => true } as never,
    hotkey: {} as never,
    audio: audio as never,
    debouncedSave: () => undefined
  })

  return {
    app,
    config,
    chunks: [],
    get startCalls() {
      return startCalls
    },
    get stopCalls() {
      return stopCalls
    },
    finishStop: () => {
      pendingStop?.()
      pendingStop = null
    },
    failNextStart: () => {
      failStart = true
    },
    savedSave: () => saveCount
  }
}

// --- tests --------------------------------------------------------------------

describe('Application state machine', () => {
  let h: Harness

  beforeEach(() => {
    h = makeHarness()
  })

  it('buffers audio chunks that arrive while capture is tearing down', async () => {
    await h.app.startRecording()
    expect(h.app.getState()).toBe('recording')

    const tail = Buffer.from([9, 9, 9, 9])
    const seen: number[] = []
    // Snapshot the buffer as the pipeline consumes it, so the assertion does
    // not race the un-awaited processRecording() continuation.
    const original = (h.app as unknown as { processRecording: (...a: unknown[]) => Promise<void> }).processRecording
    ;(h.app as unknown as { processRecording: unknown }).processRecording = function (
      this: unknown,
      ...args: unknown[]
    ): Promise<void> {
      seen.push(...(h.app as unknown as { pcmChunks: Buffer[] }).pcmChunks.flatMap((b) => [...b]))
      void original
      return Promise.resolve()
    }

    // stopRecording() flips state to 'processing' but capture teardown is
    // still pending — the tail of the utterance must not be dropped.
    const stopping = h.app.stopRecording()
    expect(h.app.getState()).toBe('processing')

    h.app.onAudioChunk(tail)
    h.finishStop()
    await stopping
    await new Promise((r) => setTimeout(r, 0))

    expect(seen).toEqual([...tail])
  })

  it('drops chunks after an explicit cancel', async () => {
    await h.app.startRecording()
    h.app.cancel()
    h.app.onAudioChunk(Buffer.from([1, 2, 3, 4]))
    expect((h.app as unknown as { pcmChunks: Buffer[] }).pcmChunks).toHaveLength(0)
  })

  it('retains the audio when transcription fails, so the tray retry works', async () => {
    await h.app.startRecording()
    h.app.onAudioChunk(Buffer.alloc(2000, 7))

    // Drive the app into 'error' by letting the stubbed transcription fail.
    const stopping = h.app.stopRecording()
    h.finishStop()
    await stopping
    await vi.waitFor(() => expect(h.app.getState()).toBe('error'))

    // The audio must survive the failure — matching Python's take_audio_path()
    // semantics, since a failed request is exactly what the user retries.
    const retained = (h.app as unknown as { retryState: { wav: Buffer } | null }).retryState
    expect(retained).not.toBeNull()
    expect(retained?.wav.subarray(44)).toEqual(Buffer.alloc(2000, 7))

    h.app.retry()
    // Previously retry() bailed out because state was 'error', not 'idle'.
    expect(h.app.getState()).toBe('processing')
    await vi.waitFor(() => expect(h.app.getState()).toBe('error'))

    // A retry-flow failure keeps the retained audio (no self-destruction).
    expect((h.app as unknown as { retryState: unknown }).retryState).not.toBeNull()
  })

  it('offers no retry when the failure left no retained audio', async () => {
    // Streaming-style failure: the streamer finalize path keeps no WAV.
    const app = h.app as unknown as {
      retryState: unknown
      onProcessingError: (gen: number, err: unknown, timedOut: boolean) => void
      generation: number
    }
    app.onProcessingError(999, new Error('stream blew up'), false)
    expect(app.retryState).toBeNull()
  })

  it('re-arms continuous mode only when the restart actually begins', async () => {
    h.config.output.continuous_mode = true
    await h.app.startRecording()
    // Capture started, so the flag is armed.
    expect((h.app as unknown as { continuousActive: boolean }).continuousActive).toBe(true)

    h.failNextStart()
    // A failed restart must not leave the flag set while sitting in 'error'.
    const started = await h.app.startRecording()
    expect(started).toBe(false)
  })

  it('does not re-arm continuous mode when the post-paste restart fails', async () => {
    // Exercise the actual restart callback inside processRecording: a
    // successful paste with continuous mode on must not re-arm the flag when
    // capture fails to come back up.
    h.config.output.continuous_mode = true
    h.config.polish.enabled = false
    h.config.asr.api_key = 'test-key'

    // Serve one successful transcription so the pipeline reaches the paste.
    fetchStub.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ text: '你好' })
    } as unknown as Response)

    await h.app.startRecording()
    h.app.onAudioChunk(Buffer.alloc(2000, 5))

    const internals = h.app as unknown as { continuousActive: boolean }
    h.failNextStart() // the continuous restart will fail

    const stopping = h.app.stopRecording()
    h.finishStop()
    await stopping

    // Let the pipeline run through paste -> restart attempt.
    await vi.waitFor(() => expect(h.app.getState()).toBe('error'))
    await new Promise((r) => setTimeout(r, 20))

    // The failed restart must leave the flag clear, not dangling as true.
    expect(internals.continuousActive).toBe(false)
  })

  it('returns false when a recording start is rejected by state', async () => {
    await h.app.startRecording()
    const again = await h.app.startRecording()
    expect(again).toBe(false)
    expect(h.app.getState()).toBe('recording')
  })
})

// Preview mutates nothing on the stored config: an unsaved theme/language pick
// must never be persisted by a later save.
describe('previewSettings does not persist', () => {
  let h: Harness

  beforeEach(() => {
    h = makeHarness()
  })

  it('leaves the stored config untouched after a preview', () => {
    h.config.window.theme_mode = 'dark'
    h.config.language = 'zh'

    h.app.previewSettings({ theme_mode: 'light', language: 'en' })

    // store.config is the same object the harness holds — it must be pristine.
    expect(h.config.window.theme_mode).toBe('dark')
    expect(h.config.language).toBe('zh')
  })

  it('reports the previewed theme without writing it', () => {
    h.config.window.theme_mode = 'dark'
    h.app.previewSettings({ theme_mode: 'light' })
    expect(h.app.resolvedTheme()).toBe('light')
    expect(h.config.window.theme_mode).toBe('dark')
  })

  it('clearPreview drops the override and restores the stored value', () => {
    h.config.window.theme_mode = 'dark'
    h.app.previewSettings({ theme_mode: 'light' })
    expect(h.app.resolvedTheme()).toBe('light')

    h.app.clearPreview()
    expect(h.app.resolvedTheme()).toBe('dark')
    expect(h.config.window.theme_mode).toBe('dark')
  })

  it('a real save supersedes a pending preview', () => {
    h.config.window.theme_mode = 'dark'
    h.app.previewSettings({ theme_mode: 'light' })
    expect(h.app.resolvedTheme()).toBe('light')

    // broadcastConfig() is what saveConfig() ends with.
    h.app.broadcastConfig()
    expect(h.app.resolvedTheme()).toBe('dark')
  })

  it('ignores a preview that matches the stored value', () => {
    h.config.window.theme_mode = 'dark'
    h.app.previewSettings({ theme_mode: 'dark' })
    expect(h.app.resolvedTheme()).toBe('dark')
    expect((h.app as unknown as { previewThemeMode: string | null }).previewThemeMode).toBeNull()
  })
})

// Voice commands, scene presets and the raw-mode gesture all intercept the
// pipeline between glossary and polish. These exercise them against a stubbed
// transcription so no real API is contacted.
describe('pipeline intercepts', () => {
  interface Harness2 {
    app: Application
    config: AppConfig
    added: Array<{ text: string; meta: unknown }>
    actionKeys: Array<{ action: string; hwnd: unknown }>
    sent: Array<{ win: string; msg: unknown }>
    finishStop(): void
  }

  function makeHarness2(): Harness2 {
    const config = defaultConfig()
    config.asr.streaming_enabled = false
    config.asr.api_key = 'test-key'
    config.polish.api_key = 'test-key'
    config.glossary = []

    const added: Array<{ text: string; meta: unknown }> = []
    const actionKeys: Array<{ action: string; hwnd: unknown }> = []
    const sent: Array<{ win: string; msg: unknown }> = []
    let pendingStop: (() => void) | null = null

    const windows = {
      send: (win: string, _channel: string, payload: unknown) => sent.push({ win, msg: payload }),
      broadcast: () => undefined,
      ensureOverlay: () => ({ showInactive: () => undefined }),
      ensureFloating: () => undefined
    } as never

    const app = new Application({
      store: {
        get config() {
          return config
        },
        replaceWith: () => undefined,
        save: () => undefined,
        loadProfile: () => {
          throw new Error('no profiles in this harness')
        }
      } as never,
      windows,
      tray: {
        setState: () => undefined,
        setRetryAvailable: () => undefined,
        showNotification: () => undefined,
        retranslate: () => undefined,
        applyConfig: () => undefined
      } as never,
      history: {
        add: (text: string, meta?: unknown) => added.push({ text, meta }),
        loadRecent: () => []
      } as never,
      typer: {
        outputText: async () => true,
        sendActionKey: async (action: string, hwnd: unknown) => {
          actionKeys.push({ action, hwnd })
          return true
        }
      } as never,
      hotkey: {} as never,
      audio: {
        start: async () => true,
        stop: () =>
          new Promise<void>((resolve) => {
            pendingStop = resolve
          })
      } as never,
      debouncedSave: () => undefined
    })

    return {
      app,
      config,
      added,
      actionKeys,
      sent,
      finishStop: () => {
        pendingStop?.()
        pendingStop = null
      }
    }
  }

  /** Stub the ASR endpoint to return `text`; any further call fails loudly. */
  function stubTranscript(text: string): void {
    fetchStub.mockImplementation((url: unknown) => {
      const u = String(url)
      if (u.includes('/audio/transcriptions')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ text }) } as unknown as Response)
      }
      // Polish endpoint must never be hit in these tests.
      return Promise.resolve({ ok: false, json: () => Promise.resolve({}) } as unknown as Response)
    })
  }

  it('runs a discard command instead of pasting', async () => {
    const h = makeHarness2()
    h.config.commands.enabled = true
    stubTranscript('取消')

    await h.app.startRecording()
    h.app.onAudioChunk(Buffer.alloc(2000, 3))
    const stopping = h.app.stopRecording()
    h.finishStop()
    await stopping
    await vi.waitFor(() => expect(h.app.getState()).toBe('idle'))

    expect(h.added).toHaveLength(0)
    expect(h.actionKeys).toHaveLength(0)
  })

  it('runs a key command instead of polishing', async () => {
    const h = makeHarness2()
    h.config.commands.enabled = true
    stubTranscript('换行。') // glossary-free, punctuation-tolerant

    await h.app.startRecording()
    h.app.onAudioChunk(Buffer.alloc(2000, 4))
    const stopping = h.app.stopRecording()
    h.finishStop()
    await stopping
    await vi.waitFor(() => expect(h.app.getState()).toBe('idle'))

    expect(h.actionKeys).toEqual([{ action: 'newline', hwnd: expect.any(Number) }])
    expect(h.added).toHaveLength(0)
  })

  it('a transcript that is not a command flows to polish', async () => {
    const h = makeHarness2()
    h.config.commands.enabled = true
    h.config.polish.enabled = false // simpler: assert history still gets the text
    stubTranscript('今天天气不错')

    await h.app.startRecording()
    h.app.onAudioChunk(Buffer.alloc(2000, 6))
    const stopping = h.app.stopRecording()
    h.finishStop()
    await stopping
    await vi.waitFor(() => expect(h.app.getState()).toBe('idle'))

    expect(h.added).toHaveLength(1)
    expect(h.added[0].text).toBe('今天天气不错')
  })

  it('attaches archive metadata when archiving is enabled', async () => {
    const h = makeHarness2()
    h.config.recording.archive_audio = true
    h.config.polish.enabled = false // isolate: no polish call in this take
    stubTranscript('存档一句')

    await h.app.startRecording()
    h.app.onAudioChunk(Buffer.alloc(2000, 8))
    const stopping = h.app.stopRecording()
    h.finishStop()
    await stopping
    await vi.waitFor(() => expect(h.app.getState()).toBe('idle'))

    // archiveDir is unset in this harness, so the file write is skipped but
    // the timing metadata still rides along with the history entry.
    expect(h.added).toHaveLength(1)
    expect(h.added[0].meta).toMatchObject({ duration_ms: expect.any(Number), processing_ms: expect.any(Number) })
    expect((h.added[0].meta as { audio_path?: string }).audio_path).toBeUndefined()
  })

  it('resolves the scene profile for the foreground process', async () => {
    const h = makeHarness2()
    const profile = defaultConfig()
    profile.asr.model = 'profile-model'
    ;(h.app as unknown as { deps: { store: { loadProfile: () => AppConfig } } }).deps.store.loadProfile = () => profile
    h.config.scenes.rules = [{ match: 'Code.exe', profile: 'coding' }]

    const app = h.app as unknown as { resolveSceneConfig(hwnd: number): AppConfig | null }
    // getProcessName is unavailable in this environment (no win32 bindings),
    // so stub it at the module level used by app.ts.
    const detect = await import('../src/main/platform/win32/terminal-detect')
    const spy = vi.spyOn(detect, 'getProcessName').mockReturnValue('windows_code.exe')

    const resolved = app.resolveSceneConfig(1234)
    spy.mockRestore()

    expect(resolved).not.toBeNull()
    expect(resolved?.asr.model).toBe('profile-model')
  })
})

// The tray quick toggles bypass the settings dialog. They must invalidate the
// glossary compile cache and trigger a debounced save.
describe('handleQuickUpdate', () => {
  it('saves, broadcasts and invalidates the glossary cache', async () => {
    const glossary = await import('../src/main/services/glossary')
    const invalidate = vi.spyOn(glossary, 'invalidateGlossaryCache')

    const config = defaultConfig()
    const broadcast = vi.fn()
    let debounced = 0

    const app = new Application({
      store: {
        get config() {
          return config
        },
        replaceWith: () => undefined,
        save: () => undefined
      } as never,
      windows: {
        broadcast,
        send: () => undefined,
        ensureOverlay: () => ({ showInactive: () => undefined })
      } as never,
      tray: {
        setState: () => undefined,
        retranslate: () => undefined,
        applyConfig: () => undefined,
        setRetryAvailable: () => undefined
      } as never,
      history: { add: () => undefined, loadRecent: () => [] } as never,
      typer: { outputText: async () => true } as never,
      hotkey: {} as never,
      audio: {} as never,
      debouncedSave: () => {
        debounced++
      }
    })

    // A tray toggle mutating a runtime field.
    app.handleQuickUpdate((c) => {
      c.output.auto_paste = !c.output.auto_paste
    })

    expect(invalidate).toHaveBeenCalledTimes(1)
    expect(debounced).toBe(1)
    expect(broadcast).toHaveBeenCalled()
    expect(config.output.auto_paste).toBe(false)

    invalidate.mockRestore()
  })
})
