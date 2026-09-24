// History storage — JSON file equivalent of voicetype/history.py.
// The Python app used SQLite+WAL for a capped 20-entry list; a JSON file with
// identical semantics (latest first, trim at 2× limit) avoids a native SQLite
// dependency. Entries keep the {created_at, text} shape (plus optional audio
// archive metadata) so exports stay conceptually compatible.

import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type { HistoryEntry, HistoryStats } from '../../shared/types'

const DEFAULT_HISTORY_LIMIT = 20

/** Optional per-entry metadata: archived audio + timing. */
export interface HistoryMeta {
  audio_path?: string
  duration_ms?: number
  processing_ms?: number
}

export class HistoryStore {
  private readonly filePath: string
  private readonly limit: number
  private entries: HistoryEntry[] = []
  private loaded = false

  constructor(configDir: string, limit = DEFAULT_HISTORY_LIMIT) {
    this.filePath = join(configDir, 'history.json')
    this.limit = limit
  }

  private load(): void {
    if (this.loaded) return
    try {
      const data = JSON.parse(readFileSync(this.filePath, 'utf-8')) as { entries?: HistoryEntry[] }
      // Old entries carry only {created_at, text}; newer fields stay absent.
      this.entries = Array.isArray(data.entries) ? data.entries : []
    } catch {
      this.entries = []
    }
    this.loaded = true
  }

  private persist(): void {
    mkdirSync(join(this.filePath, '..'), { recursive: true })
    const tmp = this.filePath + '.tmp'
    writeFileSync(tmp, JSON.stringify({ entries: this.entries }, null, 2), 'utf-8')
    renameSync(tmp, this.filePath)
  }

  add(text: string, meta: HistoryMeta = {}): void {
    if (!text.trim()) return
    this.load()
    const now = new Date()
    // Second-precision ISO timestamp, matching history.py.
    const createdAt = now.toISOString().replace(/\.\d{3}Z$/, 'Z')
    const entry: HistoryEntry = { created_at: createdAt, text }
    if (meta.audio_path) entry.audio_path = meta.audio_path
    if (typeof meta.duration_ms === 'number') entry.duration_ms = Math.round(meta.duration_ms)
    if (typeof meta.processing_ms === 'number') entry.processing_ms = Math.round(meta.processing_ms)
    this.entries.unshift(entry)
    this.trim()
    this.persist()
  }

  private trim(): void {
    if (this.entries.length > this.limit * 2) {
      this.entries = this.entries.slice(0, this.limit)
    }
  }

  /**
   * Delete archived WAVs older than retentionDays and strip audio_path from
   * entries whose file is gone (dangling references). Called after add() when
   * audio archiving is enabled.
   */
  pruneArchive(retentionDays: number, dir: string): void {
    this.load()
    const cutoff = Date.now() - retentionDays * 86_400_000
    try {
      for (const name of readdirSync(dir)) {
        if (!name.endsWith('.wav')) continue
        const path = join(dir, name)
        try {
          if (statSync(path).mtimeMs < cutoff) rmSync(path, { force: true })
        } catch {
          // best effort per file
        }
      }
    } catch {
      // archive dir missing — nothing to prune
    }
    let changed = false
    for (const entry of this.entries) {
      if (entry.audio_path && !existsSync(entry.audio_path)) {
        delete entry.audio_path
        changed = true
      }
    }
    if (changed) this.persist()
  }

  /**
   * Aggregate stats for the history window's summary bar. est_minutes_saved
   * assumes a 40 chars/minute typing speed.
   */
  stats(): HistoryStats {
    this.load()
    const now = new Date()
    const dayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
    const weekStart = now.getTime() - 7 * 86_400_000
    let totalChars = 0
    let totalDuration = 0
    let todayCount = 0
    let todayChars = 0
    let weekCount = 0
    let weekChars = 0
    for (const entry of this.entries) {
      const chars = entry.text.length
      totalChars += chars
      totalDuration += entry.duration_ms ?? 0
      const at = Date.parse(entry.created_at)
      if (!Number.isFinite(at)) continue
      if (at >= dayStart) {
        todayCount++
        todayChars += chars
      }
      if (at >= weekStart) {
        weekCount++
        weekChars += chars
      }
    }
    return {
      total: this.entries.length,
      total_chars: totalChars,
      total_duration_ms: totalDuration,
      today_count: todayCount,
      today_chars: todayChars,
      week_count: weekCount,
      week_chars: weekChars,
      est_minutes_saved: Math.round((totalChars / 40) * 10) / 10
    }
  }

  loadRecent(): HistoryEntry[] {
    this.load()
    return this.entries.slice(0, this.limit)
  }

  clear(): void {
    this.entries = []
    this.loaded = true
    try {
      this.persist()
    } catch {
      // ignore
    }
  }
}
