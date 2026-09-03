// PCM16 → WAV encoder. The Python app wrote WAV files via libsndfile; the
// Electron app keeps recorded audio in memory and wraps it in a WAV container
// only when handing it to the ASR endpoint (or the retry path).

export function encodeWavPcm16(pcm: Buffer | Int16Array, sampleRate: number, channels = 1): Buffer {
  const data = pcm instanceof Int16Array ? Buffer.from(pcm.buffer, pcm.byteOffset, pcm.byteLength) : pcm
  const bitsPerSample = 16
  const blockAlign = (channels * bitsPerSample) / 8
  const byteRate = sampleRate * blockAlign
  const header = Buffer.alloc(44)

  header.write('RIFF', 0, 'ascii')
  header.writeUInt32LE(36 + data.length, 4)
  header.write('WAVE', 8, 'ascii')
  header.write('fmt ', 12, 'ascii')
  header.writeUInt32LE(16, 16) // PCM chunk size
  header.writeUInt16LE(1, 20) // PCM format
  header.writeUInt16LE(channels, 22)
  header.writeUInt32LE(sampleRate, 24)
  header.writeUInt32LE(byteRate, 28)
  header.writeUInt16LE(blockAlign, 32)
  header.writeUInt16LE(bitsPerSample, 34)
  header.write('data', 36, 'ascii')
  header.writeUInt32LE(data.length, 40)

  return Buffer.concat([header, data])
}
