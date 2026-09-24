// History window — port of HistoryDialog: two-pane list + preview with
// copy / paste / clear actions.

import { createRoot } from 'react-dom/client'
import { useEffect, useRef, useState } from 'react'
import { AppProvider, useApp } from '../shared/app-context'
import { windowApi } from '../shared/api-binding'
import type { HistoryEntry, HistoryStats } from '../../shared/types'
import '../shared/global.css'
import './history.css'

function HistoryApp(): JSX.Element {
  const { t, format } = useApp()
  const [entries, setEntries] = useState<HistoryEntry[]>([])
  const [stats, setStats] = useState<HistoryStats | null>(null)
  const [selected, setSelected] = useState<number>(-1)
  const [copied, setCopied] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [loading, setLoading] = useState(false)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const sourceRef = useRef<AudioBufferSourceNode | null>(null)
  // Decoded buffers by entry index — replaying an entry must not re-fetch
  // and re-decode the whole WAV every time. Tiny LRU (most recent 4).
  const bufferCacheRef = useRef<Map<number, AudioBuffer>>(new Map())
  const playGenRef = useRef(0)

  useEffect(() => {
    void windowApi.historyList().then((list) => {
      setEntries(list)
      setSelected(list.length ? 0 : -1)
    })
    void windowApi.statsSummary().then(setStats)
  }, [])

  const stopAudio = (): void => {
    playGenRef.current++
    try {
      sourceRef.current?.stop()
    } catch {
      // stop() throws if the source already ended — harmless here
    }
    sourceRef.current = null
    setPlaying(false)
  }

  // Stop playback and release the AudioContext when the window goes away.
  useEffect(() => {
    const cleanup = (): void => {
      stopAudio()
      void audioCtxRef.current?.close()
      audioCtxRef.current = null
      bufferCacheRef.current.clear()
    }
    window.addEventListener('beforeunload', cleanup)
    return () => window.removeEventListener('beforeunload', cleanup)
  }, [])

  const current = selected >= 0 && selected < entries.length ? entries[selected] : null

  const onPlay = (): void => {
    if (playing || loading) {
      // A take is in flight: the button means "stop" (or "be patient").
      stopAudio()
      setLoading(false)
      return
    }
    if (!current?.audio_path) return
    setLoading(true)
    const gen = ++playGenRef.current

    const startPlayback = (buf: AudioBuffer): void => {
      if (gen !== playGenRef.current) return // superseded by a newer click
      const ctx = audioCtxRef.current ?? new AudioContext()
      audioCtxRef.current = ctx
      const src = ctx.createBufferSource()
      src.buffer = buf
      src.connect(ctx.destination)
      src.onended = () => {
        if (sourceRef.current === src) {
          sourceRef.current = null
          setPlaying(false)
        }
      }
      src.start()
      sourceRef.current = src
      setPlaying(true)
    }

    const cached = bufferCacheRef.current.get(selected)
    if (cached) {
      setLoading(false)
      startPlayback(cached)
      return
    }
    void windowApi.historyAudio(selected).then((res) => {
      setLoading(false)
      if (!res.ok || !res.data) return
      // decodeAudioData needs the exact byte range — a pooled Buffer view
      // would otherwise decode garbage.
      const bytes = res.data
      const slice = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
      const ctx = audioCtxRef.current ?? new AudioContext()
      audioCtxRef.current = ctx
      void ctx.decodeAudioData(slice).then((buf) => {
        if (gen !== playGenRef.current) return
        const cache = bufferCacheRef.current
        cache.set(selected, buf)
        if (cache.size > 4) {
          // Drop the oldest decoded entry (Map preserves insertion order).
          cache.delete(cache.keys().next().value!)
        }
        startPlayback(buf)
      })
    })
  }

  const onCopy = (): void => {
    if (!current) return
    void windowApi.historyCopy(current.text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1200)
  }

  const onPaste = (): void => {
    if (!current) return
    void windowApi.historyPaste(current.text).then(() => window.close())
  }

  const onClear = (): void => {
    stopAudio()
    bufferCacheRef.current.clear()
    void windowApi.historyClear().then(() => {
      setEntries([])
      setSelected(-1)
      void windowApi.statsSummary().then(setStats)
    })
  }

  return (
    <div className="window-body history-body">
      <div className="history-header">
        <span className="history-title">{t('history.title')}</span>
        {entries.length > 0 && <span className="history-count">{entries.length}</span>}
      </div>
      {stats && (
        <div className="history-stats">
          {format('history.stats_summary', {
            total: stats.total,
            chars: stats.total_chars,
            today: stats.today_count,
            minutes: stats.est_minutes_saved
          })}
        </div>
      )}
      <div className="history-main">
        <div className="history-list">
          {entries.length === 0 && <div className="history-empty">{t('history.empty')}</div>}
          {entries.map((entry, i) => (
            <button
              key={i}
              className={`history-item ${i === selected ? 'selected' : ''}`}
              onClick={() => setSelected(i)}
            >
              <span className="history-time">{entry.created_at.replace('T', ' ').slice(0, 19)}</span>
              <span className="history-preview">{firstLine(entry.text)}</span>
            </button>
          ))}
        </div>
        <div className={`history-detail ${current ? '' : 'empty'}`}>
          {current ? current.text : t('history.select_hint')}
        </div>
      </div>
      <div className="history-actions">
        <button disabled={!current} onClick={onCopy}>
          {copied ? t('history.copied') : t('history.copy')}
        </button>
        <button className="primary" disabled={!current} onClick={onPaste}>
          {t('history.paste')}
        </button>
        <button disabled={!current?.audio_path} onClick={onPlay}>
          {playing ? t('history.stop') : loading ? '…' : t('history.play')}
        </button>
        <div className="spacer" />
        <button className="danger" disabled={!entries.length} onClick={onClear}>
          {t('history.clear')}
        </button>
        <button onClick={() => window.close()}>{t('settings.cancel')}</button>
      </div>
      <div className="visually-hidden">{format('{count}', { count: entries.length })}</div>
    </div>
  )
}

function firstLine(text: string): string {
  const line = text.split('\n')[0] ?? ''
  return line.length > 48 ? line.slice(0, 48) + '…' : line
}

function Root(): JSX.Element {
  return (
    <AppProvider>
      <HistoryApp />
    </AppProvider>
  )
}

createRoot(document.getElementById('root')!).render(<Root />)
