// Win32 user32/kernel32/psapi bindings via koffi (N-API, no compilation).
// Only loaded on Windows; every entry point is guarded by win32Available.

import koffi from 'koffi'

export const isWindows = process.platform === 'win32'
export const win32Available = isWindows

export const KEYEVENTF_KEYUP = 0x0002

// Virtual-key codes used across the injection paths.
export const VK_SHIFT = 0x10
export const VK_CONTROL = 0x11
export const VK_MENU = 0x12 // Alt
export const VK_END = 0x23
export const VK_HOME = 0x24
export const VK_LEFT = 0x25
export const VK_RIGHT = 0x27
export const VK_C = 0x43
export const VK_V = 0x56
export const VK_ESCAPE = 0x1b

type KoffiLibrary = ReturnType<typeof koffi.load>

let user32: KoffiLibrary | null = null
let kernel32: KoffiLibrary | null = null
let psapi: KoffiLibrary | null = null

interface Win32Api {
  keybdEvent(vk: number, scan: number, flags: number): number
  getForegroundWindow(): number
  isWindow(hwnd: number): boolean
  setForegroundWindow(hwnd: number): number
  attachThreadInput(targetTid: number, ourTid: number, attach: boolean): number
  detachThreadInput(targetTid: number, ourTid: number): void
  getCurrentThreadId(): number
  getWindowThreadProcessId(hwnd: number, out: Uint32Array): number
  getClassNameW(hwnd: number, buf: Uint16Array, max: number): number
  getWindowTextLengthW(hwnd: number): number
  getWindowTextW(hwnd: number, buf: Uint16Array, max: number): number
  bringWindowToTop(hwnd: number): boolean
  openProcess(access: number, inherit: boolean, pid: number): number
  closeHandle(handle: number): boolean
  getModuleFileNameExW(hProcess: number, hModule: number, buf: Uint16Array, size: number): number
  getClipboardSequenceNumber(): number
}

let api: Win32Api | null = null

function init(): Win32Api | null {
  if (!isWindows) return null
  if (api) return api
  try {
    user32 = koffi.load('user32.dll')
    kernel32 = koffi.load('kernel32.dll')
    psapi = koffi.load('psapi.dll')

    const keybdEvent = user32.func('int __stdcall keybd_event(uint8_t bVk, uint8_t bScan, uint32_t dwFlags, uintptr_t dwExtraInfo)')
    const getForegroundWindow = user32.func('uintptr_t __stdcall GetForegroundWindow()')
    const isWindow = user32.func('int __stdcall IsWindow(uintptr_t hWnd)')
    const setForegroundWindow = user32.func('int __stdcall SetForegroundWindow(uintptr_t hWnd)')
    const attachThreadInput = user32.func('int __stdcall AttachThreadInput(uint32_t idAttach, uint32_t idAttachTo, bool fAttach)')
    const getCurrentThreadId = user32.func('uint32_t __stdcall GetCurrentThreadId()')
    const getWindowThreadProcessId = user32.func('uint32_t __stdcall GetWindowThreadProcessId(uintptr_t hWnd, _Out_ uint32_t *lpdwProcessId)')
    const getClassNameW = user32.func('int __stdcall GetClassNameW(uintptr_t hWnd, _Out_ uint16_t *lpClassName, int nMaxCount)')
    const getWindowTextLengthW = user32.func('int __stdcall GetWindowTextLengthW(uintptr_t hWnd)')
    const getWindowTextW = user32.func('int __stdcall GetWindowTextW(uintptr_t hWnd, _Out_ uint16_t *lpString, int nMaxCount)')
    const bringWindowToTop = user32.func('int __stdcall BringWindowToTop(uintptr_t hWnd)')
    const openProcess = kernel32.func('uintptr_t __stdcall OpenProcess(uint32_t dwDesiredAccess, bool bInheritHandle, uint32_t dwProcessId)')
    const closeHandle = kernel32.func('int __stdcall CloseHandle(uintptr_t hObject)')
    const getModuleFileNameExW = psapi.func('uint32_t __stdcall GetModuleFileNameExW(uintptr_t hProcess, uintptr_t hModule, _Out_ uint16_t *lpFilename, uint32_t nSize)')
    const getClipboardSequenceNumber = user32.func('uint32_t __stdcall GetClipboardSequenceNumber()')

    api = {
      keybdEvent: (vk, scan, flags) => keybdEvent(vk, scan, flags, 0),
      getForegroundWindow: () => Number(getForegroundWindow()),
      isWindow: (hwnd) => isWindow(hwnd) !== 0,
      setForegroundWindow: (hwnd) => setForegroundWindow(hwnd),
      attachThreadInput: (targetTid, ourTid, attach) => attachThreadInput(targetTid, ourTid, attach),
      detachThreadInput: (targetTid, ourTid) => {
        attachThreadInput(targetTid, ourTid, false)
      },
      getCurrentThreadId: () => getCurrentThreadId(),
      getWindowThreadProcessId: (hwnd, out) => getWindowThreadProcessId(hwnd, out),
      getClassNameW: (hwnd, buf, max) => getClassNameW(hwnd, buf, max),
      getWindowTextLengthW: (hwnd) => getWindowTextLengthW(hwnd),
      getWindowTextW: (hwnd, buf, max) => getWindowTextW(hwnd, buf, max),
      bringWindowToTop: (hwnd) => bringWindowToTop(hwnd) !== 0,
      openProcess: (access, inherit, pid) => Number(openProcess(access, inherit, pid)),
      closeHandle: (handle) => closeHandle(handle) !== 0,
      getModuleFileNameExW: (hProcess, hModule, buf, size) => getModuleFileNameExW(hProcess, hModule, buf, size),
      getClipboardSequenceNumber: () => getClipboardSequenceNumber()
    }
    return api
  } catch (e) {
    console.error('Failed to initialize Win32 bindings:', String(e))
    return null
  }
}

export function getWin32(): Win32Api | null {
  return init()
}

// ---- string helpers -----------------------------------------------------------

/** Decode a NUL-terminated UTF-16 buffer into a JS string. */
export function decodeUtf16(buf: Uint16Array): string {
  let end = buf.indexOf(0)
  if (end === -1) end = buf.length
  return Buffer.from(buf.buffer, buf.byteOffset, end * 2).toString('utf16le')
}

export const PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
