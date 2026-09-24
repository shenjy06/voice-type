#!/usr/bin/env node
// 回退对照实验：逐个还原修复，确认对应测试确实失败。
// 目的：证明测试不是"永远为绿"的假测试。
//
// 用法: node scripts/verify-reverts.mjs   (在 desktop/ 目录下运行)

import { readFileSync, writeFileSync } from 'node:fs'
import { execSync } from 'node:child_process'
import { join } from 'node:path'

const ROOT = process.cwd()

// 每个 case: 名字 -> { file, testFile, apply(源码) -> 回退后的源码, expect: 应失败的测试名 }
const cases = [
  {
    name: '1. 托盘重试 gate (idle 限定)',
    file: 'src/main/app.ts',
    testFile: 'tests/app-state.test.ts',
    apply: (s) =>
      s.replace(
        "if (!retryState || (this.state !== 'idle' && this.state !== 'error')) {",
        "if (!retryState || this.state !== 'idle') {"
      ),
    needle: "this.state !== 'idle')"
  },
  {
    name: '2. VAD 尾部音频 (state 判定)',
    file: 'src/main/app.ts',
    testFile: 'tests/app-state.test.ts',
    apply: (s) => s.replace('if (!this.capturing) return\n    this.pcmChunks.push(pcm)', "if (this.state !== 'recording') return\n    this.pcmChunks.push(pcm)"),
    needle: "if (this.state !== 'recording') return\n    this.pcmChunks.push(pcm)"
  },
  {
    name: '3. 流式 drain (finalize 前刷缓冲)',
    file: 'src/main/services/streaming-asr.ts',
    testFile: 'tests/streaming-asr.test.ts',
    apply: (s) => s.replace('    await this.drainPendingSends()\n', ''),
    needle: 'await this.drainPendingSends()'
  },
  {
    name: '8. 流式文本覆盖语义 (非拼接)',
    file: 'src/main/services/streaming-asr.ts',
    testFile: 'tests/streaming-asr.test.ts',
    apply: (s) =>
      s.replace(
        `      const transcript = (item.content ?? [])
        .map((content) => content.transcript ?? '')
        .filter(Boolean)
        .join(' ')
      if (transcript) {
        this.finalText = transcript`,
        `      let transcript = ''
      for (const content of item.content ?? []) {
        const t = content.transcript ?? ''
        if (t) transcript = this.finalText ? this.finalText + ' ' + t : t
      }
      if (transcript) {
        this.finalText = transcript`
      ),
    needle: "this.finalText + ' ' + t"
  },
  {
    name: '4. 预览不持久化 (改回直接改 config)',
    file: 'src/main/app.ts',
    testFile: 'tests/app-state.test.ts',
    apply: (s) =>
      s.replace(
        `  previewSettings(next: { theme_mode?: string; language?: string }): void {
    // Live preview without persisting. store.config must never be mutated
    // here, or the previewed value would leak into the next debounced save.
    const cfg = this.config
    const themeMode = next.theme_mode && next.theme_mode !== cfg.window.theme_mode ? next.theme_mode : null
    const language = next.language && next.language !== cfg.language ? next.language : null
    if (!themeMode && !language) return

    this.previewThemeMode = themeMode
    this.previewLanguage = language
    if (language) setLanguage(language, process.env.LANG || 'en-US')

    const preview: AppConfig = JSON.parse(JSON.stringify(cfg)) as AppConfig
    if (themeMode) preview.window.theme_mode = themeMode
    if (language) preview.language = language
    this.deps.windows.broadcast('evt', { type: 'config', config: preview, theme: this.resolvedTheme() })
    if (language) this.deps.tray.retranslate()
  }`,
        `  previewSettings(next: { theme_mode?: string; language?: string }): void {
    const cfg = this.config
    let changed = false
    if (next.theme_mode && next.theme_mode !== cfg.window.theme_mode) {
      cfg.window.theme_mode = next.theme_mode
      changed = true
    }
    if (next.language && next.language !== cfg.language) {
      cfg.language = next.language
      changed = true
    }
    if (changed) {
      this.applyLanguage()
      this.deps.windows.broadcast('evt', { type: 'config', config: cfg, theme: this.resolvedTheme() })
    }
  }`
      ),
    needle: 'cfg.window.theme_mode = next.theme_mode'
  },
  {
    name: '5. 快捷更新失效词库缓存',
    file: 'src/main/app.ts',
    testFile: 'tests/app-state.test.ts',
    apply: (s) =>
      s.replace(
        `    mutate(this.config)
    // Cheap and content-keyed, so invalidating unconditionally is safe and
    // keeps a future quick-toggle for glossary/runtime fields from serving
    // stale compiled patterns.
    invalidateGlossaryCache()
    this.deps.debouncedSave()`,
        `    mutate(this.config)
    this.deps.debouncedSave()`
      ),
    needle: 'invalidateGlossaryCache()'
  },
  {
    name: '6. 连续口述 flag 竞态 (无条件置位)',
    file: 'src/main/app.ts',
    testFile: 'tests/app-state.test.ts',
    apply: (s) =>
      s.replace(
        `        this.continuousActive = false // a restart re-arms it on success
        void this.startRecording().then((started) => {
          if (started) this.continuousActive = true
        })`,
        `        this.continuousActive = false // session restart clears the flag
        void this.startRecording().then(() => {
          this.continuousActive = true
        })`
      ),
    needle: 'if (started) this.continuousActive = true'
  }
]

const results = []

// Restore-on-exit safety net: if anything throws mid-experiment, every file we
// touched is written back from the in-memory originals.
const originals = new Map()
let activePath = null

function restoreAll() {
  for (const [path, content] of originals) {
    try {
      writeFileSync(path, content, 'utf-8')
    } catch {
      // best effort — reported by the caller
    }
  }
}

process.on('exit', restoreAll)
process.on('uncaughtException', (e) => {
  restoreAll()
  console.error('对照实验中发生异常，已恢复源码:', e)
  process.exit(2)
})

for (const c of cases) {
  const origPath = join(ROOT, c.file)

  const original = readFileSync(origPath, 'utf-8')
  const reverted = c.apply(original)

  if (reverted === original) {
    results.push({ ...c, status: 'SKIP', detail: '回退替换未匹配（源码已变）' })
    continue
  }

  if (!originals.has(origPath)) originals.set(origPath, original)
  activePath = origPath

  let failed = false
  let output = ''
  try {
    writeFileSync(origPath, reverted, 'utf-8')
    output = execSync(`npx vitest run ${c.testFile}`, {
      cwd: ROOT,
      encoding: 'utf-8',
      stdio: 'pipe'
    })
  } catch (e) {
    failed = true
    output = (e.stdout ?? '') + (e.stderr ?? '')
  } finally {
    // Restore immediately, inside the loop, so a later failure can't leave a
    // reverted file on disk.
    writeFileSync(origPath, original, 'utf-8')
    activePath = null
  }

  const stripped = output.replace(/\x1b\[[0-9;]*m/g, '')
  const failedCount = (stripped.match(/×/g) ?? []).length
  const whichFailed = [...stripped.matchAll(/×\s+(.+?)\s+\d+ms/g)]
    .map((m) => m[1].trim())
    .slice(0, 3)

  results.push({
    ...c,
    status: failed ? 'PASS (测试捕获到缺陷)' : 'FAIL (测试未捕获!)',
    failedCount,
    whichFailed
  })
}

console.log('\n========== 回退对照实验结果 ==========\n')
for (const r of results) {
  console.log(`${r.status}`)
  console.log(`  用例: ${r.name}`)
  if (r.whichFailed?.length) {
    for (const w of r.whichFailed) console.log(`    × ${w}`)
  }
  if (r.detail) console.log(`    ${r.detail}`)
  console.log()
}

const bad = results.filter((r) => r.status !== 'PASS (测试捕获到缺陷)')
console.log(bad.length === 0 ? '结论: 全部回退均被测试捕获 ✓' : `结论: ${bad.length} 项未被捕获 ✗`)
process.exit(bad.length === 0 ? 0 : 1)
