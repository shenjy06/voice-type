// HistoryStore archive metadata, pruning and stats aggregation —
// services/history.ts runs on a JSON file, so tests use a tmp dir.

import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { existsSync, mkdtempSync, rmSync, writeFileSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { HistoryStore } from '../src/main/services/history'

let dir: string

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'voicetype-history-'))
})
afterEach(() => {
  rmSync(dir, { recursive: true, force: true })
})

describe('HistoryStore archive + stats', () => {
  it('keeps optional archive metadata on entries', () => {
    const store = new HistoryStore(dir)
    store.add('first', { audio_path: '/a/1.wav', duration_ms: 1200.4, processing_ms: 300.7 })
    const entry = store.loadRecent()[0]
    expect(entry.audio_path).toBe('/a/1.wav')
    expect(entry.duration_ms).toBe(1200)
    expect(entry.processing_ms).toBe(301)
  })

  it('omits metadata when not provided', () => {
    const store = new HistoryStore(dir)
    store.add('plain')
    const entry = store.loadRecent()[0]
    expect(entry.audio_path).toBeUndefined()
    expect(entry.duration_ms).toBeUndefined()
    expect(entry.processing_ms).toBeUndefined()
  })

  it('prunes expired WAVs and strips dangling audio_path', () => {
    const archiveDir = join(dir, 'audio-archive')
    mkdirSync(archiveDir, { recursive: true })
    const old = join(archiveDir, 'old.wav')
    const fresh = join(archiveDir, 'new.wav')
    writeFileSync(old, 'x')
    writeFileSync(fresh, 'x')

    const store = new HistoryStore(dir)
    store.add('with old audio', { audio_path: old })
    store.add('with fresh audio', { audio_path: fresh })
    store.add('with dangling audio', { audio_path: join(archiveDir, 'gone.wav') })

    // Retention 0: everything in the archive is expired.
    store.pruneArchive(0, archiveDir)

    const entries = store.loadRecent()
    expect(existsSync(old)).toBe(false)
    expect(existsSync(fresh)).toBe(false)
    expect(entries.every((e) => e.audio_path === undefined)).toBe(true)
  })

  it('keeps fresh WAVs within the retention window', () => {
    const archiveDir = join(dir, 'audio-archive')
    mkdirSync(archiveDir, { recursive: true })
    const fresh = join(archiveDir, 'new.wav')
    writeFileSync(fresh, 'x')

    const store = new HistoryStore(dir)
    store.add('text', { audio_path: fresh })
    store.pruneArchive(7, archiveDir)

    expect(existsSync(fresh)).toBe(true)
    expect(store.loadRecent()[0].audio_path).toBe(fresh)
  })

  it('aggregates stats with today/week buckets and time saved', () => {
    const store = new HistoryStore(dir)
    const now = new Date()
    const iso = (d: Date): string => d.toISOString().replace(/\.\d{3}Z$/, 'Z')
    const daysAgo = (n: number): string => iso(new Date(now.getTime() - n * 86_400_000))

    store.add('today text', { duration_ms: 1000 })
    store.add('older text', { duration_ms: 2000, audio_path: '/x.wav' })
    // Rewrite timestamps so buckets are deterministic.
    const file = join(dir, 'history.json')
    const entries = store.loadRecent()
    entries[1].created_at = daysAgo(3)
    writeFileSync(file, JSON.stringify({ entries }))

    const reloaded = new HistoryStore(dir)
    const stats = reloaded.stats()
    expect(stats.total).toBe(2)
    expect(stats.total_chars).toBe('today text'.length + 'older text'.length)
    expect(stats.total_duration_ms).toBe(3000)
    expect(stats.today_count).toBe(1)
    expect(stats.week_count).toBe(2)
    expect(stats.est_minutes_saved).toBeCloseTo(Math.round((20 / 200) * 10) / 10, 5)
  })

  it('returns zeroed stats for an empty history', () => {
    const store = new HistoryStore(dir)
    const stats = store.stats()
    expect(stats.total).toBe(0)
    expect(stats.total_chars).toBe(0)
    expect(stats.est_minutes_saved).toBe(0)
  })
})
