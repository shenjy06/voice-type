// Regression tests for WindowManager's visibility contract.
//
// The bug these guard against: ensureSettings()/ensureHistory() created their
// window with `show: false` but only revealed it on the "already exists" path,
// so the first call — including the first-run wizard — produced an invisible
// window. Nothing threw, so only an explicit assertion catches a regression.
//
// BrowserWindow is stubbed with a minimal fake that records show/hide/once so
// the lifecycle can be driven deterministically.

import { describe, expect, it, vi, beforeEach } from 'vitest'

// ---- electron stub -----------------------------------------------------------

interface FakeWindow {
  id: number
  opts: Record<string, unknown>
  visible: boolean
  destroyed: boolean
  shown: number
  focused: number
  url: string
  menu: unknown
  handlers: Map<string, Array<(...args: unknown[]) => void>>
  // methods used by WindowManager
  isDestroyed(): boolean
  isVisible(): boolean
  show(): void
  hide(): void
  focus(): void
  setAlwaysOnTop(v: boolean, level?: string): void
  setIgnoreMouseEvents(ignore: boolean, opts?: unknown): void
  setMenu(m: unknown): void
  loadURL(u: string): void
  on(event: string, cb: (...args: unknown[]) => void): void
  once(event: string, cb: (...args: unknown[]) => void): void
  webContents: { send: () => void; id: number; isLoading: () => boolean }
  /** Test helper: fire a lifecycle event registered with on()/once(). */
  emit(event: string, ...args: unknown[]): void
}

let created: FakeWindow[] = []
let nextId = 1

function makeFakeWindow(opts: Record<string, unknown>): FakeWindow {
  const handlers = new Map<string, Array<(...a: unknown[]) => void>>()
  // Declared first so the method closures below can reference it.
  const win: FakeWindow = {
    id: nextId++,
    opts,
    // Mirrors Electron: `show: false` means not visible until show() is called.
    visible: opts.show === true,
    destroyed: false,
    shown: 0,
    focused: 0,
    url: '',
    menu: undefined,
    handlers,
    isDestroyed: () => win.destroyed,
    isVisible: () => win.visible,
    show() {
      win.visible = true
      win.shown++
    },
    hide() {
      win.visible = false
    },
    focus() {
      win.focused++
    },
    setAlwaysOnTop: () => undefined,
    setIgnoreMouseEvents: () => undefined,
    setMenu: (m) => {
      win.menu = m
    },
    loadURL: (u) => {
      win.url = u
    },
    on: (event, cb) => {
      const list = handlers.get(event) ?? []
      list.push(cb)
      handlers.set(event, list)
    },
    once: (event, cb) => {
      const list = handlers.get(event) ?? []
      // once() handlers are removed after firing; model that in emit().
      ;(cb as { __once?: boolean }).__once = true
      list.push(cb)
      handlers.set(event, list)
    },
    webContents: { send: () => undefined, id: 0, isLoading: () => false },
    emit(event, ...args) {
      const list = [...(handlers.get(event) ?? [])]
      for (const cb of list) {
        cb(...args)
        if ((cb as { __once?: boolean }).__once) {
          const cur = handlers.get(event) ?? []
          handlers.set(
            event,
            cur.filter((f) => f !== cb)
          )
        }
      }
    }
  }
  win.webContents.id = win.id
  return win
}

vi.mock('electron', () => ({
  BrowserWindow: class {
    constructor(opts: Record<string, unknown>) {
      const w = makeFakeWindow(opts)
      created.push(w)
      return w as unknown as object
    }
  },
  screen: {
    getPrimaryDisplay: () => ({ workArea: { x: 0, y: 0, width: 1920, height: 1080 } })
  }
}))

const { WindowManager } = await import('../src/main/windows')

const sep = process.platform === 'win32' ? '\\' : '/'

/** Matches a window whose loadURL targeted a given renderer view. */
function isFor(url: string, name: string): boolean {
  return url.includes(`${name}${sep}index.html`) || url.includes(`/${name}/`)
}

/** The fake window most recently handed out for a given renderer view. */
function lastWindowFor(name: string): FakeWindow {
  const match = [...created].reverse().find((w) => isFor(w.url, name))
  if (!match) throw new Error(`no window created for ${name}; created: ${created.map((c) => c.url).join(', ')}`)
  return match
}

/** Number of windows created for a given renderer view. */
function countFor(name: string): number {
  return created.filter((w) => isFor(w.url, name)).length
}

beforeEach(() => {
  created = []
  nextId = 1
})

// ---- tests -------------------------------------------------------------------

describe('WindowManager visibility', () => {
  describe('ensureSettings', () => {
    it('shows the window on the first call', () => {
      const wm = new WindowManager()
      wm.ensureSettings()
      const win = lastWindowFor('settings')

      // Created hidden; must not become visible until the page is ready.
      expect(win.visible).toBe(false)
      win.emit('ready-to-show')
      expect(win.visible).toBe(true)
      expect(win.focused).toBeGreaterThan(0)
    })

    it('reuses and shows an existing window on later calls', () => {
      const wm = new WindowManager()
      const first = wm.ensureSettings()
      const again = wm.ensureSettings()
      expect(again).toBe(first)
      // A second call is an explicit show request, so it should be visible
      // immediately without waiting for ready-to-show.
      expect((first as unknown as FakeWindow).visible).toBe(true)
    })

    it('creates only one window across repeated calls', () => {
      const wm = new WindowManager()
      wm.ensureSettings()
      wm.ensureSettings()
      wm.ensureSettings()
      expect(countFor('settings')).toBe(1)
    })
  })

  describe('ensureHistory', () => {
    it('shows the window on the first call', () => {
      const wm = new WindowManager()
      wm.ensureHistory()
      const win = lastWindowFor('history')
      expect(win.visible).toBe(false)
      win.emit('ready-to-show')
      expect(win.visible).toBe(true)
      expect(win.focused).toBeGreaterThan(0)
    })
  })

  describe('ensureFloating', () => {
    it('does not show when show is false', () => {
      const wm = new WindowManager()
      wm.ensureFloating({ alwaysOnTop: true, show: false })
      const win = lastWindowFor('floating')
      win.emit('ready-to-show')
      expect(win.visible).toBe(false)
    })

    it('shows when requested', () => {
      const wm = new WindowManager()
      wm.ensureFloating({ alwaysOnTop: true, show: true })
      const win = lastWindowFor('floating')
      win.emit('ready-to-show')
      expect(win.visible).toBe(true)
    })
  })

  describe('close semantics', () => {
    it('hides instead of closing while running', () => {
      const wm = new WindowManager()
      const win = wm.ensureSettings() as unknown as FakeWindow
      win.emit('ready-to-show')
      expect(win.visible).toBe(true)

      const ev = { preventDefault: vi.fn() }
      win.emit('close', ev)
      expect(ev.preventDefault).toHaveBeenCalled()
      expect(win.visible).toBe(false)
      expect(win.destroyed).toBe(false)
    })

    it('allows the close to proceed while quitting', () => {
      const wm = new WindowManager()
      const win = wm.ensureSettings() as unknown as FakeWindow
      wm.setQuitting()

      const ev = { preventDefault: vi.fn() }
      win.emit('close', ev)
      expect(ev.preventDefault).not.toHaveBeenCalled()
    })
  })

  describe('ensureOverlay', () => {
    it('never shows on creation (purely informational layer)', () => {
      const wm = new WindowManager()
      wm.ensureOverlay()
      const win = lastWindowFor('overlay')
      expect(win.visible).toBe(false)
      win.emit('ready-to-show')
      expect(win.visible).toBe(false)
    })
  })
})
