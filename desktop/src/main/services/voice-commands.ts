// Voice-command matching — port target for voicetype/voice_commands.py.
// Runs after glossary correction and before polishing: a transcript that
// consists solely of a command phrase triggers the mapped action (discard or
// a key injection) instead of being polished and pasted.

import type { VoiceCommandItem } from '../../shared/types'

/** Key-injection actions handled by TextTyper.sendActionKey; 'discard' is
 *  handled by the pipeline itself. */
export const COMMAND_ACTIONS = ['newline', 'enter', 'undo', 'tab', 'discard'] as const

// Punctuation and whitespace are stripped so "取消。" or "new line!" still
// match; comparison is case-insensitive for the English phrases.
function normalize(text: string): string {
  return text.toLowerCase().replace(/[\p{P}\p{S}\s]/gu, '')
}

/** Return the action for a matching command phrase, or null. */
export function matchVoiceCommand(transcript: string, items: VoiceCommandItem[]): string | null {
  const key = normalize(transcript)
  if (!key) return null
  for (const item of items) {
    if (!item.phrase.trim() || !item.action.trim()) continue
    if (normalize(item.phrase) === key) return item.action
  }
  return null
}
