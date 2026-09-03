// Audio capture bridge between the Application and the hidden audio renderer.
// Protocol (all via the 'evt' channel + invoke round-trips):
//   main → audio window : {type:'audio-start', sampleRate, deviceId}
//                         {type:'audio-stop'}
//   audio window → main : invoke('audio:capture-started')
//                         invoke('audio:capture-error', {message})
//                         invoke('audio:capture-stopped')
//                         send('audio:chunk', ArrayBuffer)   (PCM16)
//                         send('audio:level', number)        (~10Hz RMS)

import type { BrowserWindow } from 'electron'
import type { WindowManager } from './windows'

export interface AudioStartOptions {
  sampleRate: number
  deviceId: string | null
}

export class AudioBridge {
  private windows: WindowManager
  readonly onChunk: (pcm: Buffer) => void
  readonly onLevel: (level: number) => void
  readonly onError: (message: string) => void

  private startResolve: ((ok: boolean) => void) | null = null
  private stopResolve: (() => void) | null = null

  constructor(
    windows: WindowManager,
    handlers: { onChunk: (pcm: Buffer) => void; onLevel: (level: number) => void; onError: (message: string) => void }
  ) {
    this.windows = windows
    this.onChunk = handlers.onChunk
    this.onLevel = handlers.onLevel
    this.onError = handlers.onError
  }

  async start(opts: AudioStartOptions): Promise<boolean> {
    const win = this.windows.ensureAudio()
    await waitForLoad(win)
    this.windows.send('audio', 'evt', { type: 'audio-start', sampleRate: opts.sampleRate, deviceId: opts.deviceId })
    const ok = await new Promise<boolean>((resolve) => {
      this.startResolve = resolve
      setTimeout(() => {
        if (this.startResolve === resolve) {
          this.startResolve = null
          resolve(false)
        }
      }, 10_000)
    })
    return ok
  }

  async stop(): Promise<void> {
    const win = this.windows.get('audio')
    if (!win || win.isDestroyed()) return
    this.windows.send('audio', 'evt', { type: 'audio-stop' })
    await new Promise<void>((resolve) => {
      this.stopResolve = resolve
      setTimeout(() => {
        if (this.stopResolve === resolve) {
          this.stopResolve = null
          resolve()
        }
      }, 5_000)
    })
  }

  // ---- invoked by the audio renderer (wired in ipc.ts) -----------------------

  handleCaptureStarted(): void {
    this.startResolve?.(true)
    this.startResolve = null
  }

  handleCaptureError(message: string): void {
    this.onError(message)
    this.startResolve?.(false)
    this.startResolve = null
    this.stopResolve?.()
    this.stopResolve = null
  }

  handleCaptureStopped(): void {
    this.stopResolve?.()
    this.stopResolve = null
  }

  handleChunk(pcm: ArrayBuffer): void {
    this.onChunk(Buffer.from(pcm))
  }

  handleLevel(level: number): void {
    this.onLevel(level)
  }
}

function waitForLoad(win: BrowserWindow): Promise<void> {
  if (win.webContents.isLoading()) {
    return new Promise((resolve) => win.webContents.once('did-finish-load', () => resolve()))
  }
  return Promise.resolve()
}
