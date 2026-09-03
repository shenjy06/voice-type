// Bounded retry with exponential backoff — port of voicetype/retry.py.
// Retries connection/timeout failures and 429/5xx responses; 4xx auth or
// bad-request errors propagate immediately for fast user feedback.

export interface RetriableErrorShape {
  status?: number
  code?: string
  message?: string
}

const DEFAULT_MAX_ATTEMPTS = 3
const DEFAULT_BASE_DELAY = 0.5 // seconds; doubled each attempt, capped
const DEFAULT_MAX_DELAY = 4.0

/** True for network failures and HTTP 429/5xx. */
export function isRetriableHttpError(err: unknown): boolean {
  if (err instanceof TypeError) return true // fetch network failure
  const e = err as RetriableErrorShape
  if (typeof e?.status === 'number') return e.status === 429 || e.status >= 500
  const code = e?.code ?? ''
  if (code === 'ECONNREFUSED' || code === 'ETIMEDOUT' || code === 'ECONNRESET' || code === 'ENOTFOUND') {
    return true
  }
  return err instanceof Error && err.name === 'AbortError' // timeout
}

export class HttpError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'HttpError'
    this.status = status
  }
}

export async function retryCall<T>(
  fn: () => Promise<T>,
  opts: {
    maxAttempts?: number
    baseDelay?: number
    maxDelay?: number
    sleep?: (s: number) => Promise<void>
    isRetriable?: (err: unknown) => boolean
  } = {}
): Promise<T> {
  const maxAttempts = opts.maxAttempts ?? DEFAULT_MAX_ATTEMPTS
  const baseDelay = opts.baseDelay ?? DEFAULT_BASE_DELAY
  const maxDelay = opts.maxDelay ?? DEFAULT_MAX_DELAY
  const sleep = opts.sleep ?? ((s: number) => new Promise<void>((r) => setTimeout(r, s * 1000)))
  const isRetriable = opts.isRetriable ?? isRetriableHttpError

  let lastErr: unknown
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn()
    } catch (err) {
      lastErr = err
      if (!isRetriable(err) || attempt >= maxAttempts) throw err
      const delay = Math.min(baseDelay * 2 ** (attempt - 1), maxDelay)
      sleep(delay)
    }
  }
  throw lastErr
}
