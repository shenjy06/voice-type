// History storage — JSON file equivalent of voicetype/history.py.
// The Python app used SQLite+WAL for a capped 20-entry list; a JSON file with
// identical semantics (latest first, trim at 2× limit) avoids a native SQLite
// dependency. Entries keep the {created_at, text} shape so exports stay
// conceptually compatible.

import { mkdirSync, readFileSync, writeFileSync, renameSync } from 'node:fs'
import { join } from 'node:path'
import type { HistoryEntry } from '../../shared/types'

const DEFAULT_HISTORY_LIMIT = 20

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

  add(text: string): void {
    if (!text.trim()) return
    this.load()
    const now = new Date()
    // Second-precision ISO timestamp, matching history.py.
    const createdAt = now.toISOString().replace(/\.\d{3}Z$/, 'Z')
    this.entries.unshift({ created_at: createdAt, text })
    this.trim()
    this.persist()
  }

  private trim(): void {
    if (this.entries.length > this.limit * 2) {
      this.entries = this.entries.slice(0, this.limit)
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
