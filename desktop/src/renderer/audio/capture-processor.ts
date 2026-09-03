// AudioWorklet processor source, injected as a Blob module (keeps the build
// free of worker-asset bundling config). Accumulates 128-frame quanta into
// ~1024-frame chunks, converts float32 → int16 PCM, and reports the chunk RMS.

export const CAPTURE_PROCESSOR_NAME = 'capture-processor'

export const CAPTURE_PROCESSOR_SRC = `
class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.chunkSize = 1024
    this.buf = new Float32Array(this.chunkSize)
    this.count = 0
  }

  process(inputs) {
    const input = inputs[0] && inputs[0][0]
    if (!input) return true
    for (let i = 0; i < input.length; i++) {
      this.buf[this.count++] = input[i]
      if (this.count >= this.chunkSize) {
        this.flush()
      }
    }
    return true
  }

  flush() {
    const n = this.count
    const pcm = new Int16Array(n)
    let sum = 0
    for (let i = 0; i < n; i++) {
      const s = this.buf[i]
      const clamped = s < -1 ? -1 : s > 1 ? 1 : s
      pcm[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff
      sum += clamped * clamped
    }
    const level = Math.sqrt(sum / n)
    this.port.postMessage({ pcm, level }, [pcm.buffer])
    this.count = 0
  }
}

registerProcessor('${CAPTURE_PROCESSOR_NAME}', CaptureProcessor)
`
