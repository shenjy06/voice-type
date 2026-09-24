// Settings window root — port of SettingsDialog: 7 tabs, edit-then-save
// semantics, live theme/language preview with cancel rollback, validation
// (at least one API key), network check hint on save.

import { createRoot } from 'react-dom/client'
import { useEffect, useRef, useState } from 'react'
import { AppProvider, useApp } from '../shared/app-context'
import type { AppConfig } from '../../shared/types'
import { windowApi } from '../shared/api-binding'
import {
  GeneralTab,
  GlossaryTab,
  HotkeysTab,
  OutputTab,
  PolishTab,
  RecordingTab,
  SttTab
} from './tabs'
import '../shared/global.css'
import './settings.css'

// 16px stroke icons, one per section — a native settings rail reads faster with
// them than with text alone.
const ICONS: Record<string, JSX.Element> = {
  general: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.01a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h.01a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.01a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </>
  ),
  recording: (
    <>
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10v1a7 7 0 0 0 14 0v-1" />
      <line x1="12" y1="18" x2="12" y2="22" />
    </>
  ),
  stt: (
    <>
      <path d="M3 6h18M3 12h12M3 18h8" />
      <circle cx="19" cy="18" r="2.5" />
    </>
  ),
  polish: (
    <>
      <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
      <path d="M18 16l.9 2.1L21 19l-2.1.9L18 22l-.9-2.1L15 19l2.1-.9z" />
    </>
  ),
  glossary: (
    <>
      <path d="M4 4h9a3 3 0 0 1 3 3v13a2.5 2.5 0 0 0-2.5-2.5H4z" />
      <path d="M20 4h-4a3 3 0 0 0-3 3v13a2.5 2.5 0 0 1 2.5-2.5H20z" />
    </>
  ),
  output: (
    <>
      <path d="M9 9V5l-6 7 6 7v-4h6v-6z" />
      <path d="M15 5h4a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-4" />
    </>
  ),
  hotkeys: (
    <>
      <rect x="2" y="6" width="20" height="12" rx="2" />
      <path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M8 14h8" />
    </>
  )
}

const TABS = [
  { key: 'general', labelKey: 'settings.general' },
  { key: 'recording', labelKey: 'settings.recording_tab' },
  { key: 'stt', labelKey: 'settings.stt_tab' },
  { key: 'polish', labelKey: 'settings.polish_tab' },
  { key: 'glossary', labelKey: 'settings.glossary_tab' },
  { key: 'output', labelKey: 'settings.output' },
  { key: 'hotkeys', labelKey: 'settings.hotkeys' }
] as const

type TabKey = (typeof TABS)[number]['key']

function SettingsApp(): JSX.Element | null {
  const { config, t, format } = useApp()
  const [tab, setTab] = useState<TabKey>('general')
  const [draft, setDraft] = useState<AppConfig | null>(null)
  const [toast, setToast] = useState('')
  const savedRef = useRef<AppConfig | null>(null)

  // (Re)load the draft when the window opens with fresh config.
  useEffect(() => {
    if (config && !draft) {
      setDraft(JSON.parse(JSON.stringify(config)) as AppConfig)
      savedRef.current = config
    }
  }, [config, draft])

  if (!config || !draft) return null

  const update = (mutate: (d: AppConfig) => void): void => {
    setDraft((prev) => {
      if (!prev) return prev
      const next = JSON.parse(JSON.stringify(prev)) as AppConfig
      mutate(next)
      return next
    })
  }

  const showToast = (message: string): void => {
    if (!message) return
    setToast(message)
    setTimeout(() => setToast(''), 2600)
  }

  const onSave = (): void => {
    if (!draft.asr.api_key.trim() && !draft.polish.api_key.trim()) {
      showToast(t('settings.api_key_required'))
      return
    }
    void windowApi.saveConfig(draft).then(() => {
      savedRef.current = draft
      showToast(t('msg.settings_saved'))
      window.close()
    })
  }

  const onCancel = (): void => {
    // Discard any live theme/language preview (main keeps it out of the
    // persisted config, so this only has to drop the override + re-broadcast).
    void windowApi.cancelPreview()
    window.close()
  }

  const tabProps = { draft, update, showToast }

  return (
    <div className="window-body settings-body">
      <nav className="settings-sidebar">
        <div className="sidebar-title">{t('settings.title')}</div>
        {TABS.map((item) => (
          <button
            key={item.key}
            className={`tab ${tab === item.key ? 'active' : ''}`}
            aria-current={tab === item.key ? 'page' : undefined}
            onClick={() => setTab(item.key)}
          >
            <svg
              className="tab-icon"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              {ICONS[item.key]}
            </svg>
            <span>{t(item.labelKey)}</span>
          </button>
        ))}
      </nav>
      <div className="settings-content">
        <div className="tab-panel">
          {tab === 'general' && <GeneralTab {...tabProps} />}
          {tab === 'recording' && <RecordingTab {...tabProps} />}
          {tab === 'stt' && <SttTab {...tabProps} />}
          {tab === 'polish' && <PolishTab {...tabProps} />}
          {tab === 'glossary' && <GlossaryTab {...tabProps} />}
          {tab === 'output' && <OutputTab {...tabProps} />}
          {tab === 'hotkeys' && <HotkeysTab {...tabProps} />}
        </div>
        <div className="footer">
          <button className="primary" onClick={onSave}>
            {t('settings.save')}
          </button>
          <button onClick={onCancel}>{t('settings.cancel')}</button>
        </div>
      </div>
      {toast && <div className="toast">{format('{msg}', { msg: toast })}</div>}
    </div>
  )
}

function Root(): JSX.Element {
  return (
    <AppProvider>
      <SettingsApp />
    </AppProvider>
  )
}

createRoot(document.getElementById('root')!).render(<Root />)
