// Streaming real-time ASR — 1:1 port of voicetype/streaming_asr.py.
// WebSocket protocol (DashScope Realtime / OpenAI Realtime API):
//   1. Open <base_url>?model=<model> with Authorization + OpenAI-Beta headers.
//   2. Send session.update (pcm input, server_vad turn detection).
//   3. Stream input_audio_buffer.append events with base64 PCM16.
//   4. Live text arrives in conversation.item.input_audio_transcription.text
//      (DashScope puts the FULL transcript so far in `stash` — overwrite,
//      never append).
//   5. finalize() waits for completion events / response.done within a timeout.

import WebSocket from 'ws'
import { randomUUID } from 'node:crypto'

export interface StreamingTranscriberOptions {
  apiKey: string
  model: string
  baseUrl?: string
  language?: string
  sampleRate?: number
  onTextUpdate?: (text: string) => void
  onError?: (message: string) => void
}

const DEFAULT_BASE_URL = 'wss://dashscope.aliyuncs.com/api-ws/v1/realtime'

export class StreamingTranscriber {
  private readonly apiKey: string
  private readonly model: string
  private readonly baseUrl: string
  private readonly language: string
  private readonly sampleRate: number
  private readonly onTextUpdate?: (text: string) => void
  private readonly onError?: (message: string) => void

  private ws: WebSocket | null = null
  private finalText = ''
  private finished: (() => void) | null = null
  private sessionReady = false
  private started = false
  private closed = false
  private finishedPromise: Promise<void> | null = null

  constructor(opts: StreamingTranscriberOptions) {
    this.apiKey = opts.apiKey
    this.model = opts.model
    this.baseUrl = (opts.baseUrl || DEFAULT_BASE_URL).replace(/\/+$/, '')
    this.language = opts.language ?? 'auto'
    this.sampleRate = opts.sampleRate ?? 16000
    this.onTextUpdate = opts.onTextUpdate
    this.onError = opts.onError
  }

  /** Open the WebSocket and send session.update; waits (≤10s) for session.updated. */
  async start(): Promise<boolean> {
    if (this.started) return true
    if (!this.apiKey) {
      this.reportError('No API key configured for streaming ASR')
      return false
    }
    this.started = true

    const url = `${this.baseUrl}?model=${encodeURIComponent(this.model)}`
    try {
      this.ws = new WebSocket(url, {
        headers: {
          Authorization: `Bearer ${this.apiKey}`,
          'OpenAI-Beta': 'realtime=v1'
        },
        handshakeTimeout: 10_000
      })
    } catch (e) {
      this.reportError(`Failed to connect to streaming ASR: ${String(e)}`)
      return false
    }

    this.finishedPromise = new Promise<void>((resolve) => {
      this.finished = resolve
    })

    const ws = this.ws
    ws.on('open', () => {
      try {
        ws.send(JSON.stringify(this.sessionUpdateMessage()))
      } catch (e) {
        this.reportError(`Failed to send session.update: ${String(e)}`)
        this.closeWs()
        this.finished?.()
      }
    })
    ws.on('message', (data: WebSocket.RawData) => {
      this.handleMessage(String(data))
    })
    ws.on('error', (err: Error) => {
      if (!this.closed) {
        this.reportError(`Streaming ASR error: ${err.message}`)
        this.finished?.()
      }
    })
    ws.on('close', () => {
      this.sessionReady = false
      this.finished?.()
    })

    // Wait briefly for session.updated so callers can fall back to batch mode.
    const ready = await Promise.race([
      new Promise<boolean>((resolve) => {
        const check = setInterval(() => {
          if (this.sessionReady) {
            clearInterval(check)
            resolve(true)
          }
        }, 50)
        setTimeout(() => {
          clearInterval(check)
          resolve(false)
        }, 10_000)
      }),
      new Promise<false>((resolve) => {
        // Reject early when the socket errors out before ready.
        ws.once('error', () => resolve(false))
        ws.once('close', () => resolve(false))
      })
    ])

    if (!ready) {
      this.reportError('Timeout waiting for session.updated')
      this.closeWs()
      return false
    }
    return true
  }

  /** Enqueue a PCM16 chunk for sending. Non-blocking. */
  sendAudio(pcm: Buffer): void {
    const ws = this.ws
    if (!this.started || !ws || ws.readyState !== WebSocket.OPEN) return
    const event = {
      event_id: `audio_${randomUUID().slice(0, 12)}`,
      type: 'input_audio_buffer.append',
      audio: pcm.toString('base64')
    }
    try {
      ws.send(JSON.stringify(event))
    } catch (e) {
      // Mirror the Python sender thread: a failed chunk is logged and dropped.
      console.warn('Failed to send audio chunk:', String(e))
    }
  }

  /** Stop sending audio and wait for the final transcript (≤ timeout). */
  async finalize(timeoutMs = 10_000): Promise<string> {
    if (!this.finishedPromise) return this.finalText
    await Promise.race([this.finishedPromise, new Promise<void>((r) => setTimeout(r, timeoutMs))])
    this.closeWs()
    return this.finalText
  }

  /** Abort without waiting for the transcript (cancel path). */
  abort(): void {
    this.closeWs()
    this.finished?.()
  }

  // ---- protocol ---------------------------------------------------------------

  private sessionUpdateMessage(): Record<string, unknown> {
    const inputAudioTranscription: Record<string, unknown> = {}
    if (this.language && this.language !== 'auto') {
      inputAudioTranscription.language = this.language
    }
    return {
      event_id: `session_${randomUUID().slice(0, 12)}`,
      type: 'session.update',
      session: {
        modalities: ['text'],
        input_audio_format: 'pcm',
        sample_rate: this.sampleRate,
        input_audio_transcription: inputAudioTranscription,
        turn_detection: {
          type: 'server_vad',
          threshold: 0.2,
          silence_duration_ms: 800
        }
      }
    }
  }

  private handleMessage(message: string): void {
    let data: Record<string, unknown>
    try {
      data = JSON.parse(message) as Record<string, unknown>
    } catch {
      return
    }
    const eventType = String(data.type ?? '')

    if (eventType === 'session.updated') {
      this.sessionReady = true
    } else if (eventType === 'conversation.item.input_audio_transcription.text') {
      // DashScope: live transcript; `stash` holds the full text so far.
      const text = String(data.stash || data.text || data.delta || '')
      if (text) {
        this.finalText = text
        this.onTextUpdate?.(this.finalText)
      }
    } else if (eventType === 'conversation.item.input_audio_transcription.completed') {
      const text = String(data.text || data.stash || data.transcript || '')
      if (text) {
        this.finalText = text
        this.onTextUpdate?.(this.finalText)
      }
      this.finished?.()
    } else if (eventType === 'conversation.item.created') {
      // Fallback: some providers carry the transcript in the created item.
      const item = (data.item ?? {}) as { content?: Array<{ transcript?: string }> }
      for (const content of item.content ?? []) {
        const transcript = content.transcript ?? ''
        if (transcript) {
          this.finalText = this.finalText ? `${this.finalText} ${transcript}` : transcript
          this.onTextUpdate?.(this.finalText)
          this.finished?.()
        }
      }
    } else if (eventType === 'response.audio_transcript.done') {
      const transcript = String(data.transcript ?? '')
      if (transcript) {
        this.finalText = transcript
        this.onTextUpdate?.(transcript)
      }
      this.finished?.()
    } else if (eventType === 'response.done') {
      this.finished?.()
    } else if (eventType === 'error') {
      const err = (data.error ?? {}) as { message?: unknown }
      this.reportError(`Streaming ASR provider error: ${String(err.message ?? message)}`)
    }
  }

  private closeWs(): void {
    this.closed = true
    const ws = this.ws
    this.ws = null
    if (ws) {
      try {
        ws.close()
      } catch {
        // already closed
      }
    }
  }

  private reportError(message: string): void {
    console.error('Streaming ASR:', message)
    this.onError?.(message)
  }
}
