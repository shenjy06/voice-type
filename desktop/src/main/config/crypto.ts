// Password-envelope encryption compatible with src/voicetype/crypto.py.
// Envelope format "voice-type-config-enc-v1": PBKDF2-HMAC-SHA256 (600k
// iterations) derives a Fernet key; the Fernet token is
// base64url(0x80 || ts(8, BE) || iv(16) || AES-128-CBC(PKCS7) || HMAC-SHA256).
// Also exposes at-rest protection for API keys via Electron safeStorage
// (DPAPI on Windows) with a "v0:" base64 fallback mirroring the Python app.

import {
  createCipheriv,
  createDecipheriv,
  createHmac,
  pbkdf2Sync,
  randomBytes,
  randomUUID
} from 'node:crypto'

export const ENC_FORMAT = 'voice-type-config-enc-v1'
export const PBKDF2_ITERATIONS = 600_000
export const SALT_BYTES = 16

const FERNET_VERSION = 0x80

function deriveKey(password: string, salt: Buffer): Buffer {
  return pbkdf2Sync(password, salt, PBKDF2_ITERATIONS, 32, 'sha256')
}

function b64urlEncode(buf: Buffer): string {
  return buf.toString('base64url')
}

function b64urlDecode(s: string): Buffer {
  return Buffer.from(s, 'base64url')
}

// ---- Fernet (token format compatible with `cryptography.fernet.Fernet`) ----
// NOTE: Python's crypto.py stores base64(Fernet_token) in the envelope, where
// a Fernet token is itself base64url — so the envelope carries a DOUBLE
// base64 encoding. encrypt/decrypt here mirror both layers for interop.

function fernetEncrypt(key32: Buffer, plaintext: Buffer): Buffer {
  const signingKey = key32.subarray(0, 16)
  const encryptionKey = key32.subarray(16, 32)
  const iv = randomBytes(16)
  const cipher = createCipheriv('aes-128-cbc', encryptionKey, iv)
  const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final()])
  const ts = Buffer.alloc(8)
  ts.writeUInt32BE(Math.floor(Date.now() / 1000) >>> 0, 4) // seconds since epoch, BE64
  const hmac = createHmac('sha256', signingKey)
    .update(Buffer.concat([Buffer.from([FERNET_VERSION]), ts, iv, ciphertext]))
    .digest()
  return Buffer.concat([Buffer.from([FERNET_VERSION]), ts, iv, ciphertext, hmac])
}

/** Decode an envelope "ciphertext" field (double base64) to raw token bytes. */
function decodeToken(ciphertextB64: string): Buffer | null {
  try {
    const inner = Buffer.from(ciphertextB64, 'base64').toString('latin1')
    return Buffer.from(inner, 'base64url')
  } catch {
    return null
  }
}

/** Encode raw token bytes to the envelope's double-base64 form.
 * The inner layer must be PADDED urlsafe base64 (Fernet's own format) —
 * Python's base64.urlsafe_b64decode rejects unpadded input. */
function encodeToken(token: Buffer): string {
  let inner = b64urlEncode(token)
  const pad = (4 - (inner.length % 4)) % 4
  if (pad) inner += '='.repeat(pad)
  return Buffer.from(inner, 'utf-8').toString('base64')
}

function fernetDecrypt(key32: Buffer, token: Buffer): Buffer | null {
  if (token.length < 1 + 8 + 16 + 16 + 32 || token[0] !== FERNET_VERSION) return null
  const signingKey = key32.subarray(0, 16)
  const encryptionKey = key32.subarray(16, 32)
  const body = token.subarray(0, token.length - 32)
  const mac = token.subarray(token.length - 32)
  const expected = createHmac('sha256', signingKey).update(body).digest()
  if (mac.length !== expected.length || !timingSafeEqual(mac, expected)) return null
  const iv = body.subarray(9, 25)
  const ciphertext = body.subarray(25)
  try {
    const decipher = createDecipheriv('aes-128-cbc', encryptionKey, iv)
    return Buffer.concat([decipher.update(ciphertext), decipher.final()])
  } catch {
    return null
  }
}

function timingSafeEqual(a: Buffer, b: Buffer): boolean {
  if (a.length !== b.length) return false
  let diff = 0
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i]
  return diff === 0
}

// ---- envelope API (mirrors crypto.py encrypt_with_password / decrypt...) ----

export function isEncryptedEnvelope(data: unknown): data is Record<string, unknown> {
  return (
    typeof data === 'object' &&
    data !== null &&
    (data as Record<string, unknown>).format === ENC_FORMAT
  )
}

export function encryptWithPassword(plaintext: string, password: string): Record<string, unknown> {
  const salt = randomBytes(SALT_BYTES)
  const key = deriveKey(password, salt)
  const token = fernetEncrypt(key, Buffer.from(plaintext, 'utf-8'))
  return {
    format: ENC_FORMAT,
    kdf: 'pbkdf2-sha256',
    iterations: PBKDF2_ITERATIONS,
    // Standard base64 with padding — Python's base64.b64decode is strict
    // about the alphabet, so base64url here would break interop.
    salt: salt.toString('base64'),
    ciphertext: encodeToken(token)
  }
}

/** Returns the plaintext, or null on a wrong password / malformed envelope. */
export function decryptWithPassword(envelope: Record<string, unknown>, password: string): string | null {
  try {
    const salt = Buffer.from(String(envelope.salt), 'base64')
    const token = decodeToken(String(envelope.ciphertext))
    if (!token) return null
    const key = deriveKey(password, salt)
    const plain = fernetDecrypt(key, token)
    return plain ? plain.toString('utf-8') : null
  } catch {
    return null
  }
}

// ---- at-rest secret protection ----------------------------------------------
// Injected Electron safeStorage keeps this module electron-free and testable.
// Ciphertext format mirrors crypto.py: "v1:" DPAPI (safeStorage) or "v0:"
// base64 fallback; unsuffixed values pass through as plaintext.

export interface AtRestCrypto {
  encrypt(plaintext: string): string
  decrypt(ciphertext: string): string
}

export function createAtRestCrypto(safeStorage: {
  isEncryptionAvailable(): boolean
  encryptString(s: string): Buffer
  decryptString(b: Buffer): string
} | null): AtRestCrypto {
  return {
    encrypt(plaintext: string): string {
      if (!plaintext) return ''
      const store = safeStorage
      if (store) {
        try {
          if (store.isEncryptionAvailable()) {
            return 'v1:' + store.encryptString(plaintext).toString('base64')
          }
        } catch {
          // fall through to v0 obfuscation
        }
      }
      return 'v0:' + Buffer.from(plaintext, 'utf-8').toString('base64')
    },
    decrypt(ciphertext: string): string {
      if (!ciphertext) return ''
      const store = safeStorage
      try {
        if (ciphertext.startsWith('v1:')) {
          if (!store) return ''
          return store.decryptString(Buffer.from(ciphertext.slice(3), 'base64'))
        }
        if (ciphertext.startsWith('v0:')) {
          return Buffer.from(ciphertext.slice(3), 'base64').toString('utf-8')
        }
      } catch {
        return ''
      }
      return ciphertext
    }
  }
}

// Unused but kept for potential future salt needs — avoids importing os.urandom.
export const newId = (): string => randomUUID()
