// Hidden audio-capture window: reacts to audio-start/audio-stop control
// events and reports capture lifecycle back to the main process.

import { createRoot } from 'react-dom/client'
import { useEffect } from 'react'
import { startCapture, stopCapture } from './recorder'
import { windowApi } from '../shared/api-binding'

function AudioWindow(): null {
  useEffect(() => {
    const off = windowApi.onEvt((msg) => {
      if (msg.type === 'audio-start') {
        void startCapture(msg.sampleRate ?? 16000, msg.deviceId ?? null)
          .then(() => windowApi.captureStarted())
          .catch((err) => void windowApi.captureError(String(err)))
      } else if (msg.type === 'audio-stop') {
        void stopCapture()
          .then(() => windowApi.captureStopped())
          .catch(() => windowApi.captureStopped())
      }
    })
    return off
  }, [])
  return null
}

createRoot(document.getElementById('root')!).render(<AudioWindow />)
