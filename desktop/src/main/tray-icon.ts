// Tray icons drawn at runtime — round letter badges ("T" idle / "S" recording)
// mirroring ui/icon_utils.make_circle_icon in the Python app. PNGs are encoded
// with the same dependency-free encoder as the app icon script.

import { deflateSync } from 'node:zlib'
import { nativeImage } from 'electron'

const CRC_TABLE = (() => {
  const table = new Int32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    table[n] = c
  }
  return table
})()

function crc32(buf: Uint8Array): number {
  let c = 0xffffffff
  for (const b of buf) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}

function pngChunk(type: string, data: Buffer): Buffer {
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length)
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data])
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(body))
  return Buffer.concat([len, body, crc])
}

function encodePng(width: number, height: number, rgba: Buffer): Buffer {
  const sig = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(width, 0)
  ihdr.writeUInt32BE(height, 4)
  ihdr[8] = 8
  ihdr[9] = 6
  const raw = Buffer.alloc((width * 4 + 1) * height)
  for (let y = 0; y < height; y++) {
    rgba.copy(raw, y * (width * 4 + 1) + 1, y * width * 4, (y + 1) * width * 4)
  }
  return Buffer.concat([sig, pngChunk('IHDR', ihdr), pngChunk('IDAT', deflateSync(raw)), pngChunk('IEND', Buffer.alloc(0))])
}

/**
 * Render a round badge with a pixel-font letter. `size` should be 16 or 32.
 * Letter bitmaps are 3x5 grids scaled to fit the inner circle.
 */
export function createBadgeImage(letter: 'T' | 'S', colorHex: string, size = 32): Electron.NativeImage {
  const r = parseInt(colorHex.slice(1, 3), 16)
  const g = parseInt(colorHex.slice(3, 5), 16)
  const b = parseInt(colorHex.slice(5, 7), 16)

  // 3x5 pixel-font glyphs.
  const GLYPHS: Record<string, number[]> = {
    T: [0b111, 0b010, 0b010, 0b010, 0b010],
    S: [0b111, 0b100, 0b111, 0b001, 0b111]
  }
  const glyph = GLYPHS[letter]
  const cx = size / 2
  const cy = size / 2
  const radius = size / 2 - 1
  const cell = size / 7 // 7 units across the glyph area
  const gx0 = cx - (3 * cell) / 2
  const gy0 = cy - (5 * cell) / 2

  const rgba = Buffer.alloc(size * size * 4)
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const px = x + 0.5
      const py = y + 0.5
      const dist = Math.hypot(px - cx, py - cy)
      let alpha = 0
      if (dist <= radius - 0.5) alpha = 255
      else if (dist <= radius + 0.5) alpha = Math.round(255 * (radius + 0.5 - dist))
      // letter pixel?
      const ux = Math.floor((px - gx0) / cell)
      const uy = Math.floor((py - gy0) / cell)
      let letterPixel = false
      if (ux >= 0 && ux < 3 && uy >= 0 && uy < 5) {
        letterPixel = (glyph[uy] & (1 << (2 - ux))) !== 0
      }
      const i = (y * size + x) * 4
      if (letterPixel && alpha > 0) {
        rgba[i] = 255
        rgba[i + 1] = 255
        rgba[i + 2] = 255
        rgba[i + 3] = alpha
      } else {
        rgba[i] = r
        rgba[i + 1] = g
        rgba[i + 2] = b
        rgba[i + 3] = alpha
      }
    }
  }
  const img = nativeImage.createFromBuffer(encodePng(size, size, rgba), { scaleFactor: 1 })
  img.setTemplateImage(false)
  return img
}
