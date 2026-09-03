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
  const snapshot = savedRef.current ?? config

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
    // Roll back any live theme/language preview.
    void windowApi.previewSettings({
      theme_mode: snapshot.window.theme_mode,
      language: snapshot.language
    })
    window.close()
  }

  const tabProps = { draft, update, showToast, snapshot }

  return (
    <div className="window-body settings-body">
      <div className="tabs">
        {TABS.map((item) => (
          <button key={item.key} className={`tab ${tab === item.key ? 'active' : ''}`} onClick={() => setTab(item.key)}>
            {t(item.labelKey)}
          </button>
        ))}
      </div>
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
