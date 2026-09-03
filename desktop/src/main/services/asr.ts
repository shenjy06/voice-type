// Batch speech-to-text via an OpenAI-compatible /audio/transcriptions API —
// port of voicetype/asr.py + api_client.py. Uses fetch with multipart FormData
// instead of the openai SDK; retry/backoff semantics are identical.

import { HttpError, retryCall } from './retry'
import type { AppConfig } from '../../shared/types'

// Prompt hint for auto-detect mode to improve Chinese-English mixed recognition.
const AUTO_DETECT_PROMPT = '以下是普通话和English混合的句子。'

async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, { ...init, signal: controller.signal })
  } finally {
    clearTimeout(timer)
  }
}

/** Fetch the provider's model list (GET /models) for the settings refresh button. */
export async function fetchModels(apiKey: string, baseUrl: string, timeoutMs = 10_000): Promise<string[]> {
  const base = baseUrl.replace(/\/+$/, '')
  const res = await fetchWithTimeout(
    `${base}/models`,
    { headers: { Authorization: `Bearer ${apiKey}` } },
    timeoutMs
  )
  if (!res.ok) throw new HttpError(res.status, `HTTP ${res.status}`)
  const data = (await res.json()) as { data?: Array<{ id?: string }> }
  return (data.data ?? [])
    .map((m) => m.id ?? '')
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b))
}

export class Transcriber {
  private readonly apiKey: string
  private readonly baseUrl: string
  private readonly model: string
  private readonly language: string

  constructor(config: AppConfig) {
    this.apiKey = config.asr.api_key
    this.baseUrl = config.asr.base_url.replace(/\/+$/, '')
    this.model = config.asr.model
    this.language = config.asr.language
  }

  /** Best-effort connection warmup so the first real call skips TLS setup. */
  async warmup(): Promise<void> {
    try {
      await fetchModels(this.apiKey, this.baseUrl, 4000)
    } catch {
      // swallow — warmup is opportunistic
    }
  }

  async transcribe(wav: Buffer, sampleRate: number): Promise<string> {
    const form = () => {
      const fd = new FormData()
      // Rebuild the Blob per attempt: a failed request may have consumed part
      // of the stream (mirrors asr.py reopening the file per attempt).
      fd.append('file', new Blob([new Uint8Array(wav)], { type: 'audio/wav' }), 'recording.wav')
      fd.append('model', this.model)
      const lang = this.language
      if (lang && lang !== 'auto') {
        fd.append('language', lang)
      } else {
        fd.append('prompt', AUTO_DETECT_PROMPT)
      }
      // Some providers infer chunk duration from these optional fields.
      fd.append('response_format', 'json')
      void sampleRate
      return fd
    }

    const text = await retryCall(async () => {
      const res = await fetchWithTimeout(
        `${this.baseUrl}/audio/transcriptions`,
        { method: 'POST', headers: { Authorization: `Bearer ${this.apiKey}` }, body: form() },
        30_000
      )
      if (!res.ok) throw new HttpError(res.status, `transcription HTTP ${res.status}`)
      const data = (await res.json()) as { text?: string }
      return data.text ?? ''
    })

    const trimmed = text.trim()
    return trimmed
  }
}
