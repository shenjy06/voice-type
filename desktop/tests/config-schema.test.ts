import { describe, expect, it } from 'vitest'
import { configFromDict, defaultConfig, configSummary, validateProfileName, InvalidProfileNameError } from '../src/main/config/store'

describe('configFromDict', () => {
  it('returns defaults for an empty object', () => {
    expect(configFromDict({})).toEqual(defaultConfig())
  })

  it('keeps known fields and drops unknown ones', () => {
    const config = configFromDict({
      language: 'zh',
      asr: { model: 'whisper-large', future_field: true },
      recording: { sample_rate: 44100, bogus: 1 }
    })
    expect(config.language).toBe('zh')
    expect(config.asr.model).toBe('whisper-large')
    expect((config.asr as unknown as Record<string, unknown>).future_field).toBeUndefined()
    expect(config.recording.sample_rate).toBe(44100)
    expect(config.polish).toEqual(defaultConfig().polish)
  })

  it('falls back to the legacy "api" section for polish', () => {
    const config = configFromDict({
      api: { base_url: 'https://legacy.example/v1', api_key: 'k', model: 'm' }
    })
    expect(config.polish.base_url).toBe('https://legacy.example/v1')
    expect(config.polish.api_key).toBe('k')
  })

  it('parses glossary entries and coerces field types', () => {
    const config = configFromDict({
      glossary: [
        { source: 'a', replacement: 'b' },
        { source: 42, replacement: null },
        'garbage'
      ]
    })
    expect(config.glossary).toEqual([
      { source: 'a', replacement: 'b' },
      { source: '42', replacement: '' }
    ])
  })

  it('handles non-dict sections safely', () => {
    const config = configFromDict({ asr: 'broken', output: 5, window: [] })
    expect(config.asr).toEqual(defaultConfig().asr)
    expect(config.output).toEqual(defaultConfig().output)
    expect(config.window).toEqual(defaultConfig().window)
  })

  it('round-trips through JSON like the Python export format', () => {
    const original = defaultConfig()
    original.recording.device_id = 'abc'
    original.glossary.push({ source: 'k', replacement: 'v' })
    const restored = configFromDict(JSON.parse(JSON.stringify(original)))
    expect(restored).toEqual(original)
  })
})

describe('configSummary', () => {
  it('summarizes without API keys', () => {
    const config = defaultConfig()
    config.asr.model = 'whisper-1'
    config.asr.streaming_enabled = true
    config.polish.enabled = false
    config.glossary.push({ source: 'a', replacement: 'b' })
    const summary = configSummary(config)
    expect(summary.stt).toBe('whisper-1 (auto) +streaming')
    expect(summary.polish).toBe('disabled')
    expect(summary.glossary).toBe('1 terms')
  })
})

describe('validateProfileName', () => {
  it('accepts ordinary names', () => {
    expect(() => validateProfileName('work')).not.toThrow()
    expect(() => validateProfileName('我的 档案-1')).not.toThrow()
  })

  it('rejects traversal and empty names', () => {
    expect(() => validateProfileName('')).toThrow(InvalidProfileNameError)
    expect(() => validateProfileName('..')).toThrow(InvalidProfileNameError)
    expect(() => validateProfileName('a/b')).toThrow(InvalidProfileNameError)
    expect(() => validateProfileName('a\\b')).toThrow(InvalidProfileNameError)
    expect(() => validateProfileName(' x ')).toThrow(InvalidProfileNameError)
  })
})
