// Microphone capture pipeline for the hidden audio window:
// getUserMedia → AudioContext(configured rate) → AudioWorklet → IPC.
// Browser-side processing (AGC/NS/echo cancellation) is disabled so the
// provider receives raw mic audio like the Python sounddevice path.

import { CAPTURE_PROCESSOR_NAME, CAPTURE_PROCESSOR_SRC } from './capture-processor'
import { windowApi } from '../shared/api-binding'

interface CaptureSession {
  stream: MediaStream
  context: AudioContext
  node: AudioWorkletNode
}

let session: CaptureSession | null = null
let lastLevelSent = 0
let streamCounter = 0

export async function startCapture(sampleRate: number, deviceId: string | null): Promise<void> {
  if (session) await stopCapture()
  const token = ++streamCounter

  const constraints: MediaStreamConstraints = {
    audio: {
      ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
      channelCount: { ideal: 1 },
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false
    } as MediaTrackConstraints,
    video: false
  }
  const stream = await navigator.mediaDevices.getUserMedia(constraints)

  let context: AudioContext
  try {
    context = new AudioContext({ sampleRate })
  } catch {
    context = new AudioContext()
  }

  const blobUrl = URL.createObjectURL(new Blob([CAPTURE_PROCESSOR_SRC], { type: 'application/javascript' }))
  await context.audioWorklet.addModule(blobUrl)
  URL.revokeObjectURL(blobUrl)

  const source = context.createMediaStreamSource(stream)
  const node = new AudioWorkletNode(context, CAPTURE_PROCESSOR_NAME)
  node.port.onmessage = (e: MessageEvent<{ pcm: Int16Array; level: number }>) => {
    if (token !== streamCounter) return
    const { pcm, level } = e.data
    windowApi.sendChunk(pcm.buffer as ArrayBuffer)
    const now = performance.now()
    if (now - lastLevelSent >= 100) {
      lastLevelSent = now
      windowApi.sendLevel(level)
    }
  }
  source.connect(node)
  // No connection to destination: capture-only, no feedback.
  void context.resume()

  session = { stream, context, node }
}

export async function stopCapture(): Promise<void> {
  streamCounter++
  const s = session
  session = null
  if (!s) return
  try {
    s.node.port.onmessage = null
    s.node.disconnect()
    s.stream.getTracks().forEach((t) => t.stop())
    await s.context.close()
  } catch {
    // best effort
  }
}
