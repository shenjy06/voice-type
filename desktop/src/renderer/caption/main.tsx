// Standalone live caption window — an interactive counterpart to the overlay's
// click-through caption card. Shows the full streaming transcript (scrollable,
// copyable) while streaming ASR is active; closing hides the window and the
// main process recreates it on demand.

import { createRoot } from 'react-dom/client'
import { useEffect, useRef, useState } from 'react'
import { AppProvider, useApp } from '../shared/app-context'
import { windowApi } from '../shared/api-binding'
import '../shared/global.css'
import './caption.css'

function CaptionApp(): JSX.Element {
  const { t } = useApp()
  const [text, setText] = useState('')
  const [live, setLive] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const off = windowApi.onEvt((msg) => {
      switch (msg.type) {
        case 'caption':
          setText(msg.text ?? '')
          setLive(true)
          break
        case 'caption-hide':
          setLive(false)
          break
      }
    })
    return off
  }, [])

  // Keep the newest words in view as the transcript grows.
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [text])

  return (
    <div className="caption-window">
      <header className="caption-header">
        <span className={`caption-dot ${live ? 'live' : ''}`} />
        <span className="caption-title">{t('caption.window_title')}</span>
        <button
          className="caption-copy"
          disabled={!text}
          onClick={() => void windowApi.historyCopy(text)}
        >
          {t('btn.copy')}
        </button>
      </header>
      <div className="caption-scroll" ref={scrollRef}>
        <div className="caption-text">{text || t('caption.listening')}</div>
      </div>
    </div>
  )
}

function Root(): JSX.Element {
  return (
    <AppProvider>
      <CaptionApp />
    </AppProvider>
  )
}

createRoot(document.getElementById('root')!).render(<Root />)
