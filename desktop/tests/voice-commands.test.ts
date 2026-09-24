// Voice-command matching — pure matching logic from services/voice-commands.ts.

import { describe, expect, it } from 'vitest'
import { matchVoiceCommand } from '../src/main/services/voice-commands'
import type { VoiceCommandItem } from '../src/shared/types'

const items: VoiceCommandItem[] = [
  { phrase: '换行', action: 'newline' },
  { phrase: 'new line', action: 'newline' },
  { phrase: '回车', action: 'enter' },
  { phrase: 'enter', action: 'enter' },
  { phrase: '撤销', action: 'undo' },
  { phrase: 'undo', action: 'undo' },
  { phrase: '取消', action: 'discard' },
  { phrase: 'cancel', action: 'discard' }
]

describe('matchVoiceCommand', () => {
  it('matches an exact phrase', () => {
    expect(matchVoiceCommand('换行', items)).toBe('newline')
    expect(matchVoiceCommand('取消', items)).toBe('discard')
  })

  it('ignores surrounding punctuation and whitespace', () => {
    expect(matchVoiceCommand('换行。', items)).toBe('newline')
    expect(matchVoiceCommand('  new line! ', items)).toBe('newline')
  })

  it('is case-insensitive for latin phrases', () => {
    expect(matchVoiceCommand('CANCEL', items)).toBe('discard')
    expect(matchVoiceCommand('Undo', items)).toBe('undo')
  })

  it('does not match partial phrases or longer utterances', () => {
    expect(matchVoiceCommand('换一行', items)).toBeNull()
    expect(matchVoiceCommand('请换行', items)).toBeNull()
    expect(matchVoiceCommand('hello world', items)).toBeNull()
  })

  it('returns null for blank input or items', () => {
    expect(matchVoiceCommand('', items)).toBeNull()
    expect(matchVoiceCommand('   ', items)).toBeNull()
    expect(matchVoiceCommand('取消', [])).toBeNull()
  })

  it('skips items with blank phrase or action', () => {
    const dirty: VoiceCommandItem[] = [
      { phrase: '', action: 'newline' },
      { phrase: '撤销', action: '' },
      { phrase: '撤销', action: 'undo' }
    ]
    expect(matchVoiceCommand('撤销', dirty)).toBe('undo')
  })
})
