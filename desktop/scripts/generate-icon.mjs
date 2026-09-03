// Generate app icons (ICO with embedded PNGs) without any external deps.
// Renders a dark rounded square with an accent circle and a white microphone
// glyph using raw pixel math, then box-downsamples to the standard sizes.
// Usage: node scripts/generate-icon.mjs
import { deflateSync } from 'node:zlib'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)))
const OUT = join(ROOT, 'build', 'icon.ico')

// ---- minimal PNG encoder (RGBA, 8-bit) -------------------------------------

const CRC_TABLE = (() => {
  const table = new Int32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    table[n] = c
  }
  return table
})()

function crc32(buf) {
  let c = 0xffffffff
  for (const b of buf) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}

function chunk(type, data) {
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length)
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data])
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(body))
  return Buffer.concat([len, body, crc])
}

function encodePng(width, height, rgba) {
  const sig = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(width, 0)
  ihdr.writeUInt32BE(height, 4)
  ihdr[8] = 8 // bit depth
  ihdr[9] = 6 // color type RGBA
  const raw = Buffer.alloc((width * 4 + 1) * height)
  for (let y = 0; y < height; y++) {
    raw[y * (width * 4 + 1)] = 0 // filter: none
    rgba.copy(raw, y * (width * 4 + 1) + 1, y * width * 4, (y + 1) * width * 4)
  }
  return Buffer.concat([
    sig,
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0))
  ])
}

// ---- glyph drawing ----------------------------------------------------------

// hex "#rrggbb" -> [r, g, b]
function rgb(hex) {
  return [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)]
}

const mix = (a, b, t) => a + (b - a) * t

// Signed-distance helpers. All take a point in a 256x256 virtual canvas.
const sdRoundedRect = (px, py, x0, y0, x1, y1, r) => {
  const cx = Math.max(x0 + r, Math.min(px, x1 - r))
  const cy = Math.max(y0 + r, Math.min(py, y1 - r))
  return Math.hypot(px - cx, py - cy) - r
}
const sdCircle = (px, py, cx, cy, r) => Math.hypot(px - cx, py - cy) - r
// Ring segment: distance to circle outline, restricted to |angle| <= half.
const sdArc = (px, py, cx, cy, r, halfAngleDeg) => {
  const dx = px - cx
  const dy = py - cy
  const ang = Math.atan2(dy, dx)
  const half = (halfAngleDeg * Math.PI) / 180
  // arc spans the bottom half (90°-half .. 90°+half)
  const delta = Math.abs(((ang - Math.PI / 2 + Math.PI * 3) % (Math.PI * 2)) - Math.PI)
  if (delta <= half) return Math.abs(Math.hypot(dx, dy) - r)
  const ex = cx + r * Math.cos(Math.PI / 2 + half * Math.sign(delta || 1))
  const ey = cy + r * Math.sin(Math.PI / 2 + half * Math.sign(delta || 1))
  return Math.hypot(px - ex, py - ey)
}
const sdSegment = (px, py, ax, ay, bx, by) => {
  const abx = bx - ax
  const aby = by - ay
  const t = Math.max(0, Math.min(1, ((px - ax) * abx + (py - ay) * aby) / (abx * abx + aby * aby)))
  return Math.hypot(px - (ax + abx * t), py - (ay + aby * t))
}

// Microphone glyph SDF (negative = inside), coordinates in 256-space.
function micSdf(px, py) {
  const dCapsule = sdRoundedRect(px, py, 106, 56, 150, 130, 22)
  const dArc = sdArc(px, py, 128, 122, 42, 78) - 10
  const dStem = sdSegment(px, py, 128, 162, 128, 186) - 5
  const dBase = sdSegment(px, py, 96, 196, 160, 196) - 5
  return Math.min(dCapsule, dArc, dStem, dBase)
}

function render(size) {
  const scale = size / 256
  const aa = 1 / scale // one device pixel feather
  const bg = rgb('#1a1b26')
  const circle = rgb('#7c8cff')
  const white = [255, 255, 255]
  const rgba = Buffer.alloc(size * size * 4)
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const px = (x + 0.5) / scale
      const py = (y + 0.5) / scale
      const dBg = sdRoundedRect(px, py, 8, 8, 248, 248, 52)
      const dCircle = sdCircle(px, py, 128, 128, 96)
      const dMic = micSdf(px, py)
      const aBg = Math.min(1, Math.max(0, 0.5 - dBg / aa))
      const aCircle = Math.min(1, Math.max(0, 0.5 - dCircle / aa)) * aBg
      const aMic = Math.min(1, Math.max(0, 0.5 - dMic / aa)) * aBg
      let r = bg[0]
      let g = bg[1]
      let b = bg[2]
      r = mix(r, circle[0], aCircle)
      g = mix(g, circle[1], aCircle)
      b = mix(b, circle[2], aCircle)
      r = mix(r, white[0], aMic)
      g = mix(g, white[1], aMic)
      b = mix(b, white[2], aMic)
      const i = (y * size + x) * 4
      rgba[i] = Math.round(r)
      rgba[i + 1] = Math.round(g)
      rgba[i + 2] = Math.round(b)
      rgba[i + 3] = Math.round(aBg * 255)
    }
  }
  return rgba
}

// ---- ICO assembly -----------------------------------------------------------

const master = render(256)
const sizes = [256, 128, 64, 48, 32, 24, 16]
const pngs = sizes.map((size) => {
  if (size === 256) return encodePng(256, 256, master)
  // Box-average downsample from the 256px master.
  const f = 256 / size
  const rgba = Buffer.alloc(size * size * 4)
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let r = 0
      let g = 0
      let b = 0
      let a = 0
      let n = 0
      for (let sy = Math.floor(y * f); sy < Math.floor((y + 1) * f); sy++) {
        for (let sx = Math.floor(x * f); sx < Math.floor((x + 1) * f); sx++) {
          const i = (sy * 256 + sx) * 4
          r += master[i]
          g += master[i + 1]
          b += master[i + 2]
          a += master[i + 3]
          n++
        }
      }
      const o = (y * size + x) * 4
      rgba[o] = Math.round(r / n)
      rgba[o + 1] = Math.round(g / n)
      rgba[o + 2] = Math.round(b / n)
      rgba[o + 3] = Math.round(a / n)
    }
  }
  return encodePng(size, size, rgba)
})

const header = Buffer.alloc(6)
header.writeUInt16LE(0, 0) // reserved
header.writeUInt16LE(1, 2) // type: icon
header.writeUInt16LE(sizes.length, 4)

const entries = []
let offset = 6 + sizes.length * 16
sizes.forEach((size, i) => {
  const entry = Buffer.alloc(16)
  entry[0] = size === 256 ? 0 : size
  entry[1] = size === 256 ? 0 : size
  entry[2] = 0 // palette colors
  entry[3] = 0 // reserved
  entry.writeUInt16LE(1, 4) // planes
  entry.writeUInt16LE(32, 6) // bits per pixel
  entry.writeUInt32LE(pngs[i].length, 8)
  entry.writeUInt32LE(offset, 12)
  offset += pngs[i].length
  entries.push(entry)
})

mkdirSync(dirname(OUT), { recursive: true })
writeFileSync(OUT, Buffer.concat([header, ...entries, ...pngs]))
console.log(`icon written: ${OUT}`)
