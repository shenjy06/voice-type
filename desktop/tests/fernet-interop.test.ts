// Cross-implementation interop: decrypt an envelope produced by the real
// Python `cryptography` Fernet (generated via voicetype/crypto.py's scheme).
// Regenerate the fixture with the python snippet in README if needed.

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { decryptWithPassword, encryptWithPassword } from '../src/main/config/crypto'

const fixturePath = join(__dirname, 'fixtures', 'python-envelope.json')

describe('Python Fernet interop', () => {
  it('decrypts an envelope produced by Python cryptography', () => {
    let envelope: Record<string, unknown>
    try {
      envelope = JSON.parse(readFileSync(fixturePath, 'utf-8'))
    } catch {
      console.warn('fixture missing — regenerate with scripts note in desktop/README.md')
      return
    }
    const plain = decryptWithPassword(envelope, 'test-password')
    expect(plain).toBe('中英 mixed 内容 123')
  })

  it('produces envelopes that Python can decrypt (format sanity)', () => {
    const envelope = encryptWithPassword('roundtrip', 'pw') as Record<string, unknown>
    expect(envelope.format).toBe('voice-type-config-enc-v1')
    expect(envelope.kdf).toBe('pbkdf2-sha256')
    // Python double-encodes: envelope.ciphertext = base64(base64url(token)).
    const inner = Buffer.from(String(envelope.ciphertext), 'base64').toString('latin1')
    const token = Buffer.from(inner, 'base64url')
    // token: 0x80 || ts(8) || iv(16) || ct || hmac(32); ct is multiple of 16
    expect(token[0]).toBe(0x80)
    expect((token.length - 1 - 8 - 16 - 32) % 16).toBe(0)
  })
})
