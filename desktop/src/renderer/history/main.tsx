// History window — port of HistoryDialog: two-pane list + preview with
// copy / paste / clear actions.

import { createRoot } from 'react-dom/client'
import { useEffect, useState } from 'react'
import { AppProvider, useApp } from '../shared/app-context'
import { windowApi } from '../shared/api-binding'
import type { HistoryEntry } from '../../shared/types'
import '../shared/global.css'
import './history.css'

function HistoryApp(): JSX.Element {
  const { t, format } = useApp()
  const [entries, setEntries] = useState<HistoryEntry[]>([])
  const [selected, setSelected] = useState<number>(-1)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    void windowApi.historyList().then((list) => {
      setEntries(list)
      setSelected(list.length ? 0 : -1)
    })
  }, [])

  const current = selected >= 0 && selected < entries.length ? entries[selected] : null

  const onCopy = (): void => {
    if (!current) return
    void windowApi.historyCopy(current.text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1200)
  }

  const onPaste = (): void => {
    if (!current) return
    void windowApi.historyPaste(current.text).then(() => window.close())
  }

  const onClear = (): void => {
    void windowApi.historyClear().then(() => {
      setEntries([])
      setSelected(-1)
    })
  }

  return (
    <div className="window-body history-body">
      <div className="history-main">
        <div className="history-list">
          {entries.length === 0 && <div className="history-empty">{t('history.empty')}</div>}
          {entries.map((entry, i) => (
            <button
              key={i}
              className={`history-item ${i === selected ? 'selected' : ''}`}
              onClick={() => setSelected(i)}
            >
              <span className="history-time">{entry.created_at.replace('T', ' ').slice(0, 19)}</span>
              <span className="history-preview">{firstLine(entry.text)}</span>
            </button>
          ))}
        </div>
        <div className="history-detail">{current ? current.text : ''}</div>
      </div>
      <div className="history-actions">
        <button disabled={!current} onClick={onCopy}>
          {copied ? t('history.copied') : t('history.copy')}
        </button>
        <button className="primary" disabled={!current} onClick={onPaste}>
          {t('history.paste')}
        </button>
        <div className="spacer" />
        <button className="danger" disabled={!entries.length} onClick={onClear}>
          {t('history.clear')}
        </button>
        <button onClick={() => window.close()}>{t('settings.cancel')}</button>
      </div>
      <div className="visually-hidden">{format('{count}', { count: entries.length })}</div>
    </div>
  )
}

function firstLine(text: string): string {
  const line = text.split('\n')[0] ?? ''
  return line.length > 48 ? line.slice(0, 48) + '…' : line
}

function Root(): JSX.Element {
  return (
    <AppProvider>
      <HistoryApp />
    </AppProvider>
  )
}

createRoot(document.getElementById('root')!).render(<Root />)
