// Overlay layer — combines StatusBubble, CaptionPanel and Toast from
// ui/main_window.py into one transparent click-through window:
//   bubble   bottom-center status pill ("Recording…", "Polishing…")
//   caption  live streaming transcript card above the bubble; keeps the
//            newest text visible by trimming old content from the head once
//            the panel exceeds ~4 lines / 500 chars (same policy as Qt)
//   toast    transient notification, auto-dismisses after ~3s

import { createRoot } from 'react-dom/client'
import { useEffect, useRef, useState } from 'react'
import { AppProvider, useApp } from '../shared/app-context'
import { windowApi } from '../shared/api-binding'
import '../shared/global.css'
import './overlay.css'

const CAPTION_MAX_CHARS = 500
const CAPTION_TRIM_KEEP = 440

function CaptionPanel({ text }: { text: string }): JSX.Element {
  const { t } = useApp()
  const display = text.length > CAPTION_MAX_CHARS ? '…' + text.slice(-CAPTION_TRIM_KEEP) : text
  return (
    <div className="caption-panel">
      <div className="caption-text">{display || t('caption.listening')}</div>
    </div>
  )
}

function Bubble({ text }: { text: string }): JSX.Element {
  const preview = text.length > 40 ? text.slice(0, 40) + '…' : text
  return <div className="bubble">{preview}</div>
}

function Toast({ message, onDone }: { message: string; onDone(): void }): JSX.Element {
  useEffect(() => {
    const id = setTimeout(onDone, 3200)
    return () => clearTimeout(id)
  }, [message, onDone])
  return <div className="toast">{message}</div>
}

function OverlayApp(): JSX.Element {
  const { t } = useApp()
  const [bubbleText, setBubbleText] = useState<string | null>(null)
  const [captionText, setCaptionText] = useState<string | null>(null)
  const [toastMessage, setToastMessage] = useState<string | null>(null)
  const streamLiveRef = useRef(false)

  useEffect(() => {
    const off = windowApi.onEvt((msg) => {
      switch (msg.type) {
        case 'bubble':
          setBubbleText(msg.text ?? '')
          break
        case 'bubble-hide':
          setBubbleText(null)
          break
        case 'caption':
          streamLiveRef.current = true
          setCaptionText(msg.text ?? t('caption.listening'))
          break
        case 'caption-hide':
          streamLiveRef.current = false
          setCaptionText(null)
          break
        case 'toast':
          setToastMessage(msg.message ?? '')
          break
      }
    })
    return off
  }, [t])

  return (
    <div className="overlay-stack">
      {captionText !== null && <CaptionPanel text={captionText} />}
      {bubbleText !== null && <Bubble text={bubbleText} />}
      {toastMessage !== null && <Toast message={toastMessage} onDone={() => setToastMessage(null)} />}
    </div>
  )
}

function Root(): JSX.Element {
  return (
    <AppProvider>
      <OverlayApp />
    </AppProvider>
  )
}

createRoot(document.getElementById('root')!).render(<Root />)
