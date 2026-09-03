import { describe, expect, it } from 'vitest'
import {
  decryptWithPassword,
  encryptWithPassword,
  isEncryptedEnvelope,
  createAtRestCrypto
} from '../src/main/config/crypto'

describe('password envelope', () => {
  it('round-trips a config payload', () => {
    const plain = JSON.stringify({ language: 'zh', glossary: [{ source: 'a', replacement: 'b' }] })
    const envelope = encryptWithPassword(plain, 'hunter2')
    expect(isEncryptedEnvelope(envelope)).toBe(true)
    expect(decryptWithPassword(envelope, 'hunter2')).toBe(plain)
  })

  it('rejects a wrong password', () => {
    const envelope = encryptWithPassword('secret', 'right')
    expect(decryptWithPassword(envelope, 'wrong')).toBeNull()
  })

  it('rejects a tampered ciphertext (HMAC check)', () => {
    const envelope = encryptWithPassword('secret', 'pw')
    const token = Buffer.from(String(envelope.ciphertext), 'base64')
    token[token.length - 3] ^= 0xff
    envelope.ciphertext = token.toString('base64')
    expect(decryptWithPassword(envelope, 'pw')).toBeNull()
  })

  it('stores kdf parameters for forward compatibility', () => {
    const envelope = encryptWithPassword('x', 'pw') as Record<string, unknown>
    expect(envelope.format).toBe('voice-type-config-enc-v1')
    expect(envelope.kdf).toBe('pbkdf2-sha256')
    expect(envelope.iterations).toBe(600_000)
    expect(Buffer.from(String(envelope.salt), 'base64')).toHaveLength(16)
  })
})

describe('at-rest crypto', () => {
  it('uses v0 base64 when safeStorage is unavailable', () => {
    const crypto = createAtRestCrypto(null)
    const stored = crypto.encrypt('sk-secret')
    expect(stored.startsWith('v0:')).toBe(true)
    expect(crypto.decrypt(stored)).toBe('sk-secret')
  })

  it('round-trips through safeStorage when available', () => {
    const fake = {
      isEncryptionAvailable: () => true,
      encryptString: (s: string) => Buffer.from(`enc(${s})`),
      decryptString: (b: Buffer) => {
        const text = b.toString('utf-8')
        if (!text.startsWith('enc(') || !text.endsWith(')')) throw new Error('bad blob')
        return text.slice(4, -1)
      }
    }
    const crypto = createAtRestCrypto(fake)
    const stored = crypto.encrypt('sk-secret')
    expect(stored.startsWith('v1:')).toBe(true)
    expect(crypto.decrypt(stored)).toBe('sk-secret')
  })

  it('passes legacy unsuffixed plaintext through and handles failures', () => {
    const crypto = createAtRestCrypto(null)
    expect(crypto.decrypt('sk-legacy')).toBe('sk-legacy')
    expect(crypto.decrypt('')).toBe('')
    expect(crypto.encrypt('')).toBe('')
  })
})
