import { describe, expect, it } from 'vitest'
import { encodeWavPcm16 } from '../src/main/audio/wav'
import { VadDetector } from '../src/main/audio/vad'

describe('encodeWavPcm16', () => {
  it('writes a valid 44-byte RIFF header followed by the PCM data', () => {
    const pcm = Buffer.from([1, 0, 2, 0, 3, 0])
    const wav = encodeWavPcm16(pcm, 16000)
    expect(wav.length).toBe(44 + pcm.length)
    expect(wav.toString('ascii', 0, 4)).toBe('RIFF')
    expect(wav.toString('ascii', 8, 12)).toBe('WAVE')
    expect(wav.readUInt32LE(24)).toBe(16000)
    expect(wav.readUInt16LE(22)).toBe(1) // mono
    expect(wav.readUInt16LE(34)).toBe(16) // 16-bit
    expect(wav.readUInt32LE(40)).toBe(pcm.length)
    expect(wav.subarray(44)).toEqual(pcm)
  })

  it('accepts Int16Array input', () => {
    const pcm = new Int16Array([100, -100, 3000])
    const wav = encodeWavPcm16(pcm, 44100)
    expect(wav.readUInt32LE(24)).toBe(44100)
    expect(wav.length).toBe(44 + 6)
    expect(wav.readInt16LE(44)).toBe(100)
    expect(wav.readInt16LE(46)).toBe(-100)
  })
})

describe('VadDetector', () => {
  const make = (silenceMs = 1500) => {
    let fired = 0
    const detector = new VadDetector({
      enabled: true,
      threshold: 0.02,
      silenceDurationMs: silenceMs,
      onSilence: () => fired++
    })
    return { detector, fired: () => fired }
  }

  it('does not fire before any speech is detected', () => {
    const { detector, fired } = make()
    detector.update(0.0, 0)
    detector.update(0.0, 5000)
    expect(fired()).toBe(0)
  })

  it('fires once after speech followed by sustained silence', () => {
    const { detector, fired } = make(1500)
    detector.update(0.5, 0) // speech
    detector.update(0.0, 1000) // silence begins
    detector.update(0.0, 1400) // not yet 1500ms
    expect(fired()).toBe(0)
    detector.update(0.0, 1501)
    expect(fired()).toBe(1)
    detector.update(0.0, 9000) // latched — no repeat
    expect(fired()).toBe(1)
  })

  it('resets the silence timer when speech resumes', () => {
    const { detector, fired } = make(1000)
    detector.update(0.5, 0)
    detector.update(0.0, 800)
    detector.update(0.5, 900) // speech again — timer restarts
    detector.update(0.0, 1500)
    expect(fired()).toBe(0)
    detector.update(0.0, 1901)
    expect(fired()).toBe(1)
  })

  it('ignores sub-threshold blips after first speech', () => {
    const { detector, fired } = make(1000)
    detector.update(0.5, 0)
    detector.update(0.01, 500)
    detector.update(0.0, 1500)
    expect(fired()).toBe(1)
  })

  it('no-ops when disabled', () => {
    let fired = 0
    const detector = new VadDetector({
      enabled: false,
      threshold: 0.02,
      silenceDurationMs: 100,
      onSilence: () => fired++
    })
    detector.update(0.5, 0)
    detector.update(0.0, 9999)
    expect(fired).toBe(0)
  })
})
