// Terminal-window detection — port of voicetype/window_detect.py.
// Shared by paste (Ctrl+V vs Ctrl+Shift+V) and cursor-context capture
// (Ctrl+C is SIGINT in terminals, so capture must be skipped there).

import { decodeUtf16, getWin32, PROCESS_QUERY_LIMITED_INFORMATION } from './user32'

const TERMINAL_WINDOW_CLASSES = new Set([
  // Windows Terminal / conPTY
  'CASCADIA_HOSTING_WINDOW_CLASS',
  'ConsoleWindowClass',
  'PseudoConsoleInputSocket',
  // Linux-like terminals on Windows
  'mintty',
  'cygwin',
  'xterm',
  'rxvt',
  // Modern GPU-accelerated terminals
  'Alacritty',
  'wezterm-gui',
  'org.wezterm.wezterm',
  'kgui',
  // VS Code / IDE terminals (also covers cursor, windsurf)
  'Chrome_WidgetWin_1',
  'Chrome_WidgetWin_0',
  'Chrome_RenderWidgetHostHWND',
  // JetBrains / IntelliJ
  'SunAwtFrame',
  'JetWindowClass',
  // Other agent / IDE
  'Windows.UI.Core.CoreWindow',
  'ReBarWindow32',
  'HwndWrapper',
  'Notepad'
])

const TERMINAL_TITLE_MARKERS = [
  'command prompt',
  'powershell',
  'windows powershell',
  'cmd.exe',
  'bash',
  'zsh',
  'git bash',
  'wsl',
  // AI coding agents
  'claude',
  'codex',
  'kimi',
  'cursor',
  'windsurf',
  'continue',
  'cline',
  ' aider',
  'tabnine',
  'github copilot',
  // IDEs
  'visual studio code',
  'vs code',
  'intellij',
  'pycharm',
  'webstorm',
  'jetbrains'
]

const KNOWN_TERMINAL_EXES = new Set([
  'windowsterminal.exe',
  'cmd.exe',
  'powershell.exe',
  'pwsh.exe',
  'bash.exe',
  'zsh.exe',
  'sh.exe',
  'mintty.exe',
  'alacritty.exe',
  'wezterm-gui.exe',
  'wezterm.exe',
  'code.exe',
  'cursor.exe',
  'windsurf.exe',
  'claude.exe',
  'codex.exe',
  'kitty.exe',
  'conhost.exe'
])

export function getWindowClassName(hwnd: number): string {
  const api = getWin32()
  if (!api) return ''
  const buf = new Uint16Array(256)
  try {
    if (!api.getClassNameW(hwnd, buf, buf.length)) return ''
    return decodeUtf16(buf)
  } catch {
    return ''
  }
}

export function getWindowTitle(hwnd: number): string {
  const api = getWin32()
  if (!api) return ''
  try {
    const len = api.getWindowTextLengthW(hwnd)
    if (!len) return ''
    const buf = new Uint16Array(len + 1)
    api.getWindowTextW(hwnd, buf, buf.length)
    return decodeUtf16(buf)
  } catch {
    return ''
  }
}

// Process lookup is cached by (hwnd, pid) — Windows recycles HWNDs, so a
// pure-hwnd cache could return a stale process name (same as window_detect.py).
const processNameCache = new Map<string, string>()

export function getProcessName(hwnd: number): string {
  const api = getWin32()
  if (!api) return ''
  const pidBuf = new Uint32Array(1)
  try {
    api.getWindowThreadProcessId(hwnd, pidBuf)
  } catch {
    return ''
  }
  const pid = pidBuf[0]
  if (!pid) return ''
  const key = `${hwnd}:${pid}`
  const cached = processNameCache.get(key)
  if (cached !== undefined) return cached

  let name = ''
  try {
    const hProcess = api.openProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid)
    if (hProcess) {
      const buf = new Uint16Array(512)
      if (api.getModuleFileNameExW(hProcess, 0, buf, buf.length)) {
        const full = decodeUtf16(buf)
        name = full ? full.split('\\').pop() ?? '' : ''
      }
      api.closeHandle(hProcess)
    }
  } catch {
    name = ''
  }
  if (processNameCache.size >= 64) {
    processNameCache.delete(processNameCache.keys().next().value as string)
  }
  processNameCache.set(key, name)
  return name
}

export function isTerminalWindow(hwnd: number): boolean {
  if (!hwnd) return false
  const api = getWin32()
  if (!api) return false

  const className = getWindowClassName(hwnd)
  if (TERMINAL_WINDOW_CLASSES.has(className)) return true

  const title = getWindowTitle(hwnd).toLowerCase()
  for (const marker of TERMINAL_TITLE_MARKERS) {
    if (title.includes(marker)) return true
  }

  const procName = getProcessName(hwnd)
  if (procName && KNOWN_TERMINAL_EXES.has(procName.toLowerCase())) return true

  return false
}
