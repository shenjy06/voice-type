// RMS-level VAD state machine — port of the AudioRecorder._update_vad logic in
// voicetype/audio.py: silence is only counted after the first speech is
// detected, and on_silence fires once per recording (latched).

interface VadOptions {
  enabled: boolean
  threshold: number
  silenceDurationMs: number
  onSilence: () => void
}

export class VadDetector {
  private readonly opts: VadOptions
  private speaking = false
  private hasSpoken = false
  private lastVoiceTime = 0
  private fired = false

  constructor(opts: VadOptions) {
    this.opts = opts
  }

  /** Feed one audio level (same 0..1 scale as the recorder's input_level). */
  update(level: number, now: number): void {
    if (!this.opts.enabled || this.fired) return
    if (level >= this.opts.threshold) {
      this.speaking = true
      this.hasSpoken = true
      this.lastVoiceTime = now
      return
    }
    // Silence is only counted after the first speech is detected.
    if (this.hasSpoken && this.speaking && now - this.lastVoiceTime >= this.opts.silenceDurationMs) {
      this.fired = true
      this.opts.onSilence()
    }
  }

  reset(): void {
    this.speaking = false
    this.hasSpoken = false
    this.lastVoiceTime = 0
    this.fired = false
  }
}
