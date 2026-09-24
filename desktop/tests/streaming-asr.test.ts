// Streaming ASR protocol tests against a local mock WebSocket server.
// Covers the two fixes: the send-buffer drain before close (tail audio must
// reach the provider) and the overwrite — not append — transcript semantics.

import { afterEach, describe, expect, it } from 'vitest'
import { WebSocketServer, type WebSocket as WsSocket } from 'ws'
import { StreamingTranscriber } from '../src/main/services/streaming-asr'

interface MockServer {
  url: string
  /** Every JSON message the server received, in order. */
  received: Array<Record<string, unknown>>
  /** Non-JSON frames (the empty drain sentinel). */
  sentinels: number
  sockets: WsSocket[]
  close(): Promise<void>
}

/** Start a server on an ephemeral port that answers session.update. */
async function startServer(onReady?: (socket: WsSocket) => void): Promise<MockServer> {
  const server = new WebSocketServer({ port: 0 })
  await new Promise<void>((resolve) => server.once('listening', resolve))
  const address = server.address()
  if (address === null || typeof address === 'string') throw new Error('no port')

  const received: Array<Record<string, unknown>> = []
  const sockets: WsSocket[] = []
  let sentinels = 0

  server.on('connection', (socket) => {
    sockets.push(socket)
    socket.on('message', (raw) => {
      const text = String(raw)
      if (!text) {
        sentinels++ // the empty frame used to drain the send buffer
        return
      }
      const msg = JSON.parse(text) as Record<string, unknown>
      received.push(msg)
      if (msg.type === 'session.update') {
        socket.send(JSON.stringify({ type: 'session.updated' }))
        onReady?.(socket)
      }
    })
  })

  return {
    url: `ws://127.0.0.1:${address.port}`,
    received,
    get sentinels() {
      return sentinels
    },
    sockets,
    close: () =>
      new Promise<void>((resolve) => {
        for (const s of sockets) s.terminate()
        server.close(() => resolve())
      })
  }
}

const makeTranscriber = (url: string): StreamingTranscriber =>
  new StreamingTranscriber({ apiKey: 'test-key', model: 'test-model', baseUrl: url, sampleRate: 16000 })

let active: MockServer | null = null

afterEach(async () => {
  await active?.close()
  active = null
})

describe('StreamingTranscriber', () => {
  it('flushes queued audio before closing on finalize', async () => {
    active = await startServer()
    const streamer = makeTranscriber(active.url)
    expect(await streamer.start()).toBe(true)

    // Queue several chunks, then finalize immediately. The provider must see
    // all of them before the socket goes away.
    const chunks = [Buffer.alloc(320, 1), Buffer.alloc(320, 2), Buffer.alloc(320, 3)]
    for (const c of chunks) streamer.sendAudio(c)

    const server = active
    void streamer.finalize(200)

    await new Promise((r) => setTimeout(r, 300))
    const appends = server.received.filter((m) => m.type === 'input_audio_buffer.append')
    expect(appends).toHaveLength(chunks.length)
    expect(appends.map((m) => m.audio)).toEqual(chunks.map((c) => c.toString('base64')))
    // The empty sentinel is what orders the close after the queued audio:
    // its send callback only fires once everything ahead of it has flushed.
    expect(server.sentinels).toBeGreaterThanOrEqual(1)
  })

  it('overwrites (never appends) when the created-item fallback arrives late', async () => {
    active = await startServer((socket) => {
      // Full-text event first, then the item.created fallback carrying the
      // same transcript — appending would duplicate it.
      socket.send(
        JSON.stringify({
          type: 'conversation.item.input_audio_transcription.text',
          stash: '你好世界'
        })
      )
      socket.send(
        JSON.stringify({
          type: 'conversation.item.created',
          item: { content: [{ transcript: '你好世界' }] }
        })
      )
    })

    const streamer = makeTranscriber(active.url)
    expect(await streamer.start()).toBe(true)
    await new Promise((r) => setTimeout(r, 100))

    const text = await streamer.finalize(300)
    expect(text).toBe('你好世界')
  })

  it('keeps the full stash text when transcriptions stream in', async () => {
    active = await startServer((socket) => {
      // DashScope puts the whole transcript so far in `stash`.
      socket.send(
        JSON.stringify({ type: 'conversation.item.input_audio_transcription.text', stash: '今天' })
      )
      socket.send(
        JSON.stringify({ type: 'conversation.item.input_audio_transcription.text', stash: '今天开会' })
      )
      socket.send(
        JSON.stringify({
          type: 'conversation.item.input_audio_transcription.completed',
          text: '今天开会讨论部署'
        })
      )
    })

    const streamer = makeTranscriber(active.url)
    expect(await streamer.start()).toBe(true)
    await new Promise((r) => setTimeout(r, 100))

    expect(await streamer.finalize(300)).toBe('今天开会讨论部署')
  })

  it('returns false when the session never becomes ready', async () => {
    // A server that accepts the connection but never sends session.updated.
    const server = new WebSocketServer({ port: 0 })
    await new Promise<void>((resolve) => server.once('listening', resolve))
    const address = server.address()
    if (address === null || typeof address === 'string') throw new Error('no port')
    const sockets: WsSocket[] = []
    server.on('connection', (s) => sockets.push(s))
    active = {
      url: `ws://127.0.0.1:${address.port}`,
      received: [],
      sockets,
      close: () =>
        new Promise<void>((resolve) => {
          for (const s of sockets) s.terminate()
          server.close(() => resolve())
        })
    }

    const streamer = makeTranscriber(active.url)
    // The handshake succeeds but ready never arrives — start() resolves false
    // so the caller can fall back to batch mode. (10s internal timeout.)
    const started = await streamer.start()
    expect(started).toBe(false)
  }, 20_000)
})
