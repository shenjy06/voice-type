// Reusable settings components: modal dialog, password field with visibility
// toggle, labeled field row, editable model picker with provider refresh, and
// the hotkey recorder (port of hotkey_recorder.py).

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useApp } from '../shared/app-context'
import { windowApi } from '../shared/api-binding'

// ---- modal ------------------------------------------------------------------

export interface ModalSpec {
  title: string
  body: ReactNode
  okLabel?: string
  cancelLabel?: string
  danger?: boolean
  onOk(): void
  onCancel(): void
}

export function Modal({ spec }: { spec: ModalSpec }): JSX.Element {
  const { t } = useApp()
  return (
    <div className="modal-backdrop">
      <div className="modal">
        <h3>{spec.title}</h3>
        <div className="modal-body">{spec.body}</div>
        <div className="modal-actions">
          <button onClick={spec.onCancel}>{spec.cancelLabel ?? t('settings.cancel')}</button>
          <button className={spec.danger ? 'danger' : 'primary'} onClick={spec.onOk}>
            {spec.okLabel ?? t('settings.save')}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---- password input with eye toggle ------------------------------------------

export function PasswordInput({
  value,
  onChange,
  placeholder
}: {
  value: string
  onChange(v: string): void
  placeholder?: string
}): JSX.Element {
  const { t } = useApp()
  const [visible, setVisible] = useState(false)
  return (
    <div className="password-wrap">
      <input
        type={visible ? 'text' : 'password'}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        type="button"
        className="eye-btn"
        title={visible ? t('settings.hide_password') : t('settings.show_password')}
        onClick={() => setVisible((v) => !v)}
      >
        {visible ? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
            <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
            <line x1="1" y1="1" x2="23" y2="23" />
          </svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
        )}
      </button>
    </div>
  )
}

// ---- labeled field row ----------------------------------------------------------

export function Field({ label, children, alignTop }: { label: string; children: ReactNode; alignTop?: boolean }): JSX.Element {
  return (
    <div className={`field ${alignTop ? 'align-top' : ''}`}>
      <label>{label}</label>
      <div className="control">{children}</div>
    </div>
  )
}

// ---- model picker (editable combo + provider refresh) ----------------------------

export function ModelPicker({
  kind,
  value,
  onChange,
  suggestions
}: {
  kind: 'asr' | 'polish'
  value: string
  onChange(v: string): void
  suggestions: string[]
}): JSX.Element {
  const { t } = useApp()
  const [models, setModels] = useState<string[]>(suggestions)
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(false)

  const refresh = (): void => {
    setLoading(true)
    setStatus(t('settings.loading_models'))
    void windowApi
      .fetchModels(kind)
      .then((res) => {
        if (res.ok && res.models) {
          setModels(res.models)
          setStatus(t('settings.models_loaded').replace('{count}', String(res.models.length)))
        } else {
          setStatus(t('settings.models_fetch_failed').replace('{error}', res.error ?? ''))
        }
      })
      .finally(() => setLoading(false))
  }

  const listId = `models-${kind}`
  return (
    <>
      <input
        type="text"
        value={value}
        list={listId}
        onChange={(e) => onChange(e.target.value)}
        style={{ flex: 1, minWidth: 0 }}
      />
      <datalist id={listId}>
        {models.map((m) => (
          <option key={m} value={m} />
        ))}
      </datalist>
      <button type="button" className="model-refresh" title={t('settings.refresh_models')} disabled={loading} onClick={refresh}>
        {loading ? '…' : '⟳'}
      </button>
      {status && (
        <span className="hint" style={{ margin: 0 }}>
          {status}
        </span>
      )}
    </>
  )
}

// ---- hotkey recorder (port of HotkeyRecorder) ------------------------------------

const F_KEY_RE = /^F([1-9]|1[0-2])$/

export function hotkeyLabelFor(hotkey: string): string {
  const normalized = hotkey.trim().toLowerCase()
  if (normalized === 'right_alt' || normalized === 'right-alt') return 'Right Alt'
  if (normalized.startsWith('vk:')) {
    const vk = Number(normalized.slice(3))
    if (vk >= 0x70 && vk <= 0x7b) return `F${vk - 0x70 + 1}`
    if (vk >= 0x30 && vk <= 0x5a) return String.fromCharCode(vk)
    return `VK 0x${vk.toString(16).toUpperCase()}`
  }
  const fMatch = normalized.match(/^f([1-9]|1[0-2])$/)
  if (fMatch) return `F${fMatch[1]}`
  if (normalized.length === 1) return normalized.toUpperCase()
  return hotkey || 'Right Alt'
}

export function HotkeyRecorder({
  value,
  onChange
}: {
  value: string
  onChange(v: string): void
}): JSX.Element {
  const { t } = useApp()
  const [listening, setListening] = useState(false)
  const ref = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!listening) return
    const handler = (e: KeyboardEvent): void => {
      e.preventDefault()
      e.stopPropagation()
      if (e.key === 'Escape') {
        setListening(false)
        return
      }
      if (e.code === 'AltRight') {
        onChange('right_alt')
        setListening(false)
        return
      }
      if (e.code === 'AltLeft' || e.code === 'ControlLeft' || e.code === 'ControlRight' || e.code === 'ShiftLeft' || e.code === 'ShiftRight' || e.code === 'MetaLeft' || e.code === 'MetaRight') {
        return // bare modifiers other than Right Alt are not bindable
      }
      const fMatch = e.key.match(F_KEY_RE)
      if (fMatch) {
        onChange(e.key.toLowerCase())
      } else if (e.key.length === 1 && /[a-z0-9]/i.test(e.key)) {
        onChange(e.key.toLowerCase())
      } else if (e.keyCode >= 32 && e.keyCode <= 126) {
        onChange(`vk:${e.keyCode}`)
      } else {
        return // unrecognized — keep listening
      }
      setListening(false)
    }
    window.addEventListener('keydown', handler, true)
    ref.current?.focus()
    return () => window.removeEventListener('keydown', handler, true)
  }, [listening, onChange])

  return (
    <>
      <div ref={ref} className={`hotkey-display ${listening ? 'listening' : ''}`} tabIndex={-1}>
        {listening ? '…' : hotkeyLabelFor(value)}
      </div>
      <button type="button" onClick={() => setListening((v) => !v)}>
        {listening ? t('settings.cancel') : 'Change'}
      </button>
    </>
  )
}
