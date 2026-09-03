// Floating recording widget — port of FloatingRecordingWindow in
// ui/main_window.py: draggable always-on-top card with mic icon, pulsing
// recording dot, live 18-bar level waveform, and a tri-state action button.

import { createRoot } from 'react-dom/client'
import { useEffect, useRef, useState } from 'react'
import { AppProvider, useApp } from '../shared/app-context'
import { windowApi } from '../shared/api-binding'
import type { RecorderState } from '../../shared/types'
import '../shared/global.css'
import './floating.css'

function MicIcon({ color }: { color: string }): JSX.Element {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round">
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10v1a7 7 0 0 0 14 0v-1" />
      <line x1="12" y1="18" x2="12" y2="22" />
    </svg>
  )
}

function GearIcon(): JSX.Element {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.01a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h.01a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.01a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  )
}

function CloseIcon(): JSX.Element {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

const BAR_COUNT = 18

function Waveform({ level, recording }: { level: number; recording: boolean }): JSX.Element {
  const [bars, setBars] = useState<number[]>(() => new Array(BAR_COUNT).fill(0))
  const barsRef = useRef(bars)
  barsRef.current = bars

  useEffect(() => {
    if (!recording) {
      setBars(new Array(BAR_COUNT).fill(0))
      return
    }
    const id = setInterval(() => {
      setBars((prev) => {
        const next = prev.slice(1)
        // Map the smoothed level into a visible bar height, with jitter.
        const value = Math.min(1, level * 4 + Math.random() * 0.08)
        next.push(value)
        return next
      })
    }, 100)
    return () => clearInterval(id)
  }, [recording, level])

  return (
    <div className="waveform">
      {bars.map((v, i) => (
        <div
          key={i}
          className="bar"
          style={{
            height: `${4 + v * 18}px`,
            background: recording ? 'var(--vt-success)' : 'var(--vt-border-hover)',
            opacity: 0.35 + v * 0.65
          }}
        />
      ))}
    </div>
  )
}

function FloatingApp(): JSX.Element {
  const { t } = useApp()
  const [state, setState] = useState<RecorderState>('idle')
  const [error, setError] = useState('')
  const [level, setLevel] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const [recording, setRecording] = useState(false)
  const startedAtRef = useRef(0)

  useEffect(() => {
    const off = windowApi.onEvt((msg) => {
      if (msg.type === 'state') {
        const s = msg.state ?? 'idle'
        setState(s)
        setError(msg.error ?? '')
        startedAtRef.current = msg.startedAt ?? 0
        setRecording(s === 'recording')
        if (s !== 'recording') setElapsed(0)
      } else if (msg.type === 'level') {
        setLevel(msg.level ?? 0)
      }
    })
    return off
  }, [])

  useEffect(() => {
    if (!recording) return
    const id = setInterval(() => {
      const secs = Math.floor((Date.now() - startedAtRef.current) / 1000)
      setElapsed(secs)
    }, 500)
    return () => clearInterval(id)
  }, [recording])

  const mm = String(Math.floor(elapsed / 60)).padStart(2, '0')
  const ss = String(elapsed % 60).padStart(2, '0')

  const buttonLabel =
    state === 'recording' ? t('btn.recording') : state === 'processing' ? t('btn.polishing') : t('btn.record')
  const buttonClass =
    state === 'recording' ? 'record-btn danger' : state === 'processing' ? 'record-btn warning' : 'record-btn primary'

  return (
    <div className="floating-card" title={state === 'error' ? error : undefined}>
      <div className="drag-header">
        <MicIcon color="var(--vt-accent)" />
        <span className="app-name">Voice Type</span>
        <button className="icon-btn no-drag" title="Settings" onClick={() => void windowApi.showSettings()}>
          <GearIcon />
        </button>
        <button className="icon-btn close no-drag" title="Hide" onClick={() => window.close()}>
          <CloseIcon />
        </button>
      </div>
      <div className="status-row">
        <span className={`pulse-dot ${recording ? 'on' : ''}`} />
        <span className="timer">
          {mm}:{ss}
        </span>
      </div>
      <Waveform level={level} recording={recording} />
      <button
        className={buttonClass}
        disabled={state === 'processing'}
        onClick={() => void windowApi.toggleRecording()}
      >
        {buttonLabel}
      </button>
    </div>
  )
}

function Root(): JSX.Element {
  return (
    <AppProvider>
      <FloatingApp />
    </AppProvider>
  )
}

createRoot(document.getElementById('root')!).render(<Root />)
