import { describe, expect, it } from 'vitest'
import { applyGlossary } from '../src/main/services/glossary'
import type { GlossaryEntry } from '../src/shared/types'

const entry = (source: string, replacement: string): GlossaryEntry => ({ source, replacement })

describe('applyGlossary', () => {
  it('replaces recognized text with the configured term', () => {
    expect(applyGlossary('今天开会讨论 kubernetes 部署', [entry('kubernetes', 'K8s')])).toBe(
      '今天开会讨论 K8s 部署'
    )
  })

  it('replaces longer sources first when nested', () => {
    const entries = [entry('Open AI', 'OpenAI'), entry('Open AI API', 'OpenAI 接口')]
    expect(applyGlossary('使用 Open AI API 完成', entries)).toBe('使用 OpenAI 接口 完成')
  })

  it('escapes regex special characters in sources', () => {
    expect(applyGlossary('价格是 C++ (不是 C)', [entry('C++ (不是 C)', 'C++')])).toBe('价格是 C++')
  })

  it('ignores entries with empty source or replacement', () => {
    expect(applyGlossary('hello world', [entry('', 'x'), entry('hello', '')])).toBe('hello world')
  })

  it('returns the text unchanged for an empty glossary', () => {
    expect(applyGlossary('hello', [])).toBe('hello')
  })

  it('keeps the first occurrence when duplicate sources exist', () => {
    expect(applyGlossary('aa bb', [entry('aa', '1'), entry('aa', '2')])).toBe('1 bb')
  })
})
