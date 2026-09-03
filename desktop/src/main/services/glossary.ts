// Glossary-based transcript correction — port of voicetype/glossary.py.
// All sources are compiled into one alternation regex (longest first) and
// replaced in a single pass; compiled patterns are content-keyed and cached.

import type { GlossaryEntry } from '../../shared/types'

interface CompiledGlossary {
  pattern: RegExp
  replacementMap: Map<string, string>
}

const glossaryCache = new Map<string, CompiledGlossary>()

function normalize(entries: GlossaryEntry[]): Array<[string, string]> {
  return entries
    .map((e) => [e.source.trim(), e.replacement.trim()] as [string, string])
    .filter(([source, replacement]) => source && replacement)
    .sort((a, b) => b[0].length - a[0].length)
}

function buildGlossary(entries: GlossaryEntry[]): CompiledGlossary | null {
  const valid = normalize(entries)
  if (!valid.length) return null

  const key = JSON.stringify(valid)
  const cached = glossaryCache.get(key)
  if (cached) return cached

  const seen = new Set<string>()
  const unique: Array<[string, string]> = []
  for (const [source, replacement] of valid) {
    if (!seen.has(source)) {
      seen.add(source)
      unique.push([source, replacement])
    }
  }

  const pattern = new RegExp(unique.map(([source]) => source.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'gu')
  const replacementMap = new Map(unique)

  if (glossaryCache.size >= 16) {
    glossaryCache.delete(glossaryCache.keys().next().value as string)
  }
  const compiled = { pattern, replacementMap }
  glossaryCache.set(key, compiled)
  return compiled
}

export function invalidateGlossaryCache(): void {
  glossaryCache.clear()
}

export function applyGlossary(text: string, entries: GlossaryEntry[]): string {
  if (!text || !entries.length) return text
  const compiled = buildGlossary(entries)
  if (!compiled) return text
  return text.replace(compiled.pattern, (m) => compiled.replacementMap.get(m) ?? m)
}
