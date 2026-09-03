// The seven settings tabs — functional port of settings_dialog.py:
// General (language/theme/autostart/config export-import/profiles),
// Recording (sample rate/device/mic test/denoise deferred/VAD),
// STT (key/url/model+refresh/language/streaming), Polish (key/url/model/
// enabled/style), Glossary (table + CSV), Output (delay/mode/auto/continuous),
// Hotkeys (enable + recorder).

import { useEffect, useRef, useState } from 'react'
import type { AppConfig, GlossaryEntry, OutputDevice } from '../../shared/types'
import { ASR_LANGUAGES, POLISH_STYLES, PASTE_MODES, THEME_MODES } from '../../shared/types'
import { useApp } from '../shared/app-context'
import { windowApi } from '../shared/api-binding'
import { Field, Modal, ModelPicker, PasswordInput, HotkeyRecorder } from './components'

export interface TabProps {
  draft: AppConfig
  update(mutate: (d: AppConfig) => void): void
  showToast(message: string): void
  snapshot: AppConfig
}

// ---- General -----------------------------------------------------------------

export function GeneralTab({ draft, update, showToast, snapshot }: TabProps): JSX.Element {
  const { t, format } = useApp()
  const [profiles, setProfiles] = useState<{ profiles: string[]; active: string | null }>({ profiles: [], active: null })
  const [modal, setModal] = useState<'save-as' | 'delete' | 'switch' | null>(null)
  const [newProfileName, setNewProfileName] = useState('')
  const [passwordModal, setPasswordModal] = useState<'export' | null>(null)

  const refreshProfiles = (): void => {
    void windowApi.listProfiles().then(setProfiles)
  }
  useEffect(refreshProfiles, [])

  const onExport = (password: string | null): void => {
    setPasswordModal(null)
    void windowApi.exportConfig(password).then((res) => {
      showToast(res.ok ? t('settings.export_success') : res.error ? format(t('settings.config_write_failed'), { error: res.error }) : '')
    })
  }

  const runImport = (password?: string): void => {
    void windowApi.importConfig(password).then((res) => {
      if (res.canceled) return
      if (res.needsPassword) {
        pendingPassword.current = 'import'
        setShowPasswordRequest(true)
        return
      }
      if (res.invalidPassword) {
        showToast(t('settings.import_invalid_password'))
        pendingPassword.current = 'import'
        setShowPasswordRequest(true)
        return
      }
      if (!res.ok || !res.config) {
        showToast(res.error ? format(t('settings.import_failed'), { error: res.error }) : '')
        return
      }
      const imported = res.config
      const summary = (res.summary ?? {}) as Record<string, string>
      const summaryText = ['stt', 'polish', 'recording', 'output', 'glossary', 'window']
        .map((k) => summary[k])
        .filter(Boolean)
        .join('\n')
      const isDefault = !imported.asr.api_key && !imported.polish.api_key && !imported.glossary.length
      setModalSpec({
        title: t('settings.import_confirm_title'),
        body: isDefault
          ? t('settings.import_empty_config_warning')
          : format(t('settings.import_preview_text'), { summary: summaryText }),
        onOk: () => {
          update((d) => {
            Object.assign(d, imported)
          })
          setModalSpec(null)
          showToast(t('settings.import_success'))
        },
            onCancel: () => setModalSpec(null)
      })
    })
  }

  const [modalSpec, setModalSpec] = useState<{
    title: string
    body: string
    onOk(): void
    onCancel(): void
  } | null>(null)
  const [showPasswordRequest, setShowPasswordRequest] = useState(false)
  const pendingPassword = useRef<'import' | null>(null)
  const [importPassword, setImportPassword] = useState('')

  const onProfileSwitch = (name: string): void => {
    if (!name) return
    setModalSpec({
      title: t('settings.profile_label'),
      body: t('settings.profile_switch_confirm_text'),
      onOk: () => {
        setModalSpec(null)
        void windowApi.loadProfile(name).then((res) => {
          if (res.ok && res.config) {
            update((d) => {
              Object.assign(d, res.config)
            })
            showToast(format(t('settings.profile_loaded'), { name }))
          }
        })
      },
            onCancel: () => setModalSpec(null)
    })
  }

  return (
    <div>
      <div className="group">
        <div className="group-title">{t('settings.general')}</div>
        <Field label={t('settings.ui_language')}>
          <select
            value={draft.language}
            onChange={(e) => {
              const lang = e.target.value
              update((d) => void (d.language = lang))
              void windowApi.previewSettings({ language: lang })
            }}
          >
            <option value="auto">{t('settings.ui_language_auto')}</option>
            <option value="en">English</option>
            <option value="zh">中文</option>
          </select>
        </Field>
        <Field label={t('settings.theme')}>
          <select
            value={draft.window.theme_mode}
            onChange={(e) => {
              const mode = e.target.value
              update((d) => void (d.window.theme_mode = mode))
              void windowApi.previewSettings({ theme_mode: mode })
            }}
          >
            {THEME_MODES.map((m) => (
              <option key={m} value={m}>
                {t(`settings.theme_${m}`)}
              </option>
            ))}
          </select>
        </Field>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={draft.window.auto_start}
            onChange={(e) => update((d) => void (d.window.auto_start = e.target.checked))}
          />
          {t('settings.auto_start')}
        </label>
      </div>

      <div className="group">
        <div className="group-title">{t('settings.config_management')}</div>
        <div className="field">
          <label />
          <div className="control">
            <button onClick={() => setPasswordModal('export')}>{t('settings.export_config')}</button>
            <button onClick={() => runImport()}>{t('settings.import_config')}</button>
          </div>
        </div>
        <Field label={t('settings.profile_label')}>
          <div className="profile-row">
            <select
              value={profiles.active ?? ''}
              onChange={(e) => onProfileSwitch(e.target.value)}
            >
              <option value="">—</option>
              {profiles.profiles.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <button
              onClick={() => {
                setNewProfileName('')
                setModal('save-as')
              }}
            >
              {t('settings.profile_save_new')}
            </button>
            <button
              className="danger"
              disabled={!profiles.active}
              onClick={() => setModal('delete')}
            >
              {t('settings.profile_delete')}
            </button>
          </div>
        </Field>
      </div>

      {passwordModal === 'export' && (
        <ExportPasswordModal
          onOk={(password) => onExport(password)}
          onCancel={() => setPasswordModal(null)}
        />
      )}
      {showPasswordRequest && (
        <ImportPasswordModal
          value={importPassword}
          onChange={setImportPassword}
          onOk={() => {
            setShowPasswordRequest(false)
            const pw = importPassword
            setImportPassword('')
            runImport(pw)
          }}
          onCancel={() => {
            setShowPasswordRequest(false)
            setImportPassword('')
            pendingPassword.current = null
          }}
        />
      )}
      {modal === 'save-as' && (
        <Modal
          spec={{
            title: t('settings.profile_save_new_title'),
            body: (
              <div>
                <div>{t('settings.profile_save_new_prompt')}</div>
                <input
                  type="text"
                  value={newProfileName}
                  autoFocus
                  style={{ width: '100%', marginTop: 8 }}
                  onChange={(e) => setNewProfileName(e.target.value)}
                />
              </div>
            ),
            onOk: () => {
              const name = newProfileName.trim()
              if (!name || name.includes('/') || name.includes('\\')) {
                showToast(t('settings.profile_name_invalid'))
                return
              }
              void windowApi.saveProfile(name).then((res) => {
                if (res.ok) {
                  refreshProfiles()
                  setModal(null)
                  showToast(format(t('settings.profile_saved'), { name }))
                } else {
                  showToast(t('settings.profile_name_invalid'))
                }
              })
            },
            onCancel: () => setModal(null)
          }}
        />
      )}
      {modal === 'delete' && profiles.active && (
        <Modal
          spec={{
            title: t('settings.profile_delete_confirm_title'),
            body: format(t('settings.profile_delete_confirm_text'), { name: profiles.active }),
            danger: true,
            okLabel: t('settings.profile_delete'),
            onOk: () => {
              const name = profiles.active!
              void windowApi.deleteProfile(name).then((res) => {
                if (res.ok) {
                  refreshProfiles()
                  showToast(format(t('settings.profile_deleted'), { name }))
                }
                setModal(null)
              })
            },
            onCancel: () => setModal(null)
          }}
        />
      )}
      {modalSpec && <Modal spec={modalSpec} />}
      {/* keep snapshot referenced so cancel-rollback stays symmetric */}
      <span style={{ display: 'none' }}>{snapshot.window.theme_mode}</span>
    </div>
  )
}

function ExportPasswordModal({ onOk, onCancel }: { onOk(password: string | null): void; onCancel(): void }): JSX.Element {
  const { t } = useApp()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const mismatch = confirm !== '' && password !== confirm
  return (
    <Modal
      spec={{
        title: t('settings.export_encrypt_title'),
        body: (
          <div>
            <div>{t('settings.export_encrypt_prompt')}</div>
            <div style={{ marginTop: 8 }}>
              <PasswordInput value={password} onChange={setPassword} />
            </div>
            <div style={{ marginTop: 8 }}>
              <PasswordInput value={confirm} onChange={setConfirm} />
            </div>
            {mismatch && <div className="error-text">{t('settings.password_mismatch')}</div>}
          </div>
        ),
        okLabel: t('settings.save'),
        onOk: () => onOk(mismatch ? null : password || null),
        onCancel: onCancel
      }}
    />
  )
}

function ImportPasswordModal({
  value,
  onChange,
  onOk,
  onCancel
}: {
  value: string
  onChange(v: string): void
  onOk(): void
  onCancel(): void
}): JSX.Element {
  const { t } = useApp()
  return (
    <Modal
      spec={{
        title: t('settings.import_password_title'),
        body: (
          <div>
            <div>{t('settings.import_password_prompt')}</div>
            <div style={{ marginTop: 8 }}>
              <PasswordInput value={value} onChange={onChange} />
            </div>
          </div>
        ),
        okLabel: t('settings.save'),
        onOk: onOk,
        onCancel: onCancel
      }}
    />
  )
}

// ---- Recording ------------------------------------------------------------------

const SAMPLE_RATES = [8000, 16000, 24000, 32000, 40000, 48000]

export function RecordingTab({ draft, update }: TabProps): JSX.Element {
  const { t } = useApp()
  const [devices, setDevices] = useState<OutputDevice[]>([])
  const [testing, setTesting] = useState(false)
  const [level, setLevel] = useState(0)
  const [status, setStatus] = useState<'idle' | 'listening' | 'ok' | 'silent' | 'error'>('idle')
  const testRef = useRef<{ stop(): void } | null>(null)

  useEffect(() => {
    const load = (): void => {
      void navigator.mediaDevices.enumerateDevices().then((all) => {
        const inputs = all
          .filter((d) => d.kind === 'audioinput')
          .map((d) => ({ deviceId: d.deviceId, label: d.label, isDefault: false }))
        setDevices(inputs)
      })
    }
    load()
    navigator.mediaDevices.addEventListener?.('devicechange', load)
    return () => navigator.mediaDevices.removeEventListener?.('devicechange', load)
  }, [])

  const startTest = (): void => {
    void startMicTest(draft.recording.device_id, (lvl) => {
      setLevel(lvl)
      if (lvl > 0.02) setStatus('ok')
    })
      .then(() => {
        
        setTesting(true)
        setStatus('listening')
      })
      .catch(() => setStatus('error'))
  }

  const stopTest = (): void => {
    testRef.current?.stop()
    testRef.current = null
    setTesting(false)
    setLevel(0)
    setStatus('idle')
  }

  const statusText = {
    idle: t('settings.mic_status_idle'),
    listening: t('settings.mic_status_listening'),
    ok: t('settings.mic_status_ok'),
    silent: t('settings.mic_status_silent'),
    error: t('settings.mic_status_error')
  }[status]

  return (
    <div>
      <div className="group">
        <div className="group-title">{t('settings.recording_group')}</div>
        <Field label={t('settings.sample_rate')}>
          <select
            value={draft.recording.sample_rate}
            onChange={(e) => update((d) => void (d.recording.sample_rate = Number(e.target.value)))}
          >
            {SAMPLE_RATES.map((r) => (
              <option key={r} value={r}>
                {r} Hz
              </option>
            ))}
          </select>
        </Field>
        <Field label={t('settings.mic_device')}>
          <select
            value={draft.recording.device_id ?? ''}
            onChange={(e) => update((d) => void (d.recording.device_id = e.target.value || null))}
          >
            <option value="">{t('settings.mic_device_default')}</option>
            {devices.map((d) => (
              <option key={d.deviceId} value={d.deviceId}>
                {d.label || d.deviceId.slice(0, 12)}
              </option>
            ))}
          </select>
        </Field>
        {!devices.length && <div className="hint">{t('settings.mic_device_none')}</div>}
        <Field label={t('settings.mic_level')}>
          <div className="mic-bar">
            <div className="fill" style={{ width: `${Math.min(100, level * 400)}%` }} />
          </div>
          <button onClick={testing ? stopTest : startTest}>
            {testing ? t('settings.mic_test_stop') : t('settings.mic_test_start')}
          </button>
        </Field>
        <div className="hint">{statusText}</div>
      </div>

      <div className="group">
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={draft.recording.vad_enabled}
            onChange={(e) => update((d) => void (d.recording.vad_enabled = e.target.checked))}
          />
          {t('settings.vad_enabled')}
        </label>
        {draft.recording.vad_enabled && (
          <Field label={t('settings.vad_silence_duration')}>
            <input
              type="text"
              value={draft.recording.vad_silence_duration_ms}
              onChange={(e) => {
                const v = Number(e.target.value.replace(/\D/g, '') || 0)
                update((d) => void (d.recording.vad_silence_duration_ms = Math.max(500, Math.min(5000, v))))
              }}
              style={{ width: 90 }}
            />
            <span className="hint" style={{ margin: 0 }}>
              ms
            </span>
          </Field>
        )}
        <div className="hint">{t('settings.vad_hint')}</div>
      </div>

      <div className="group">
        <label className="checkbox-row">
          <input type="checkbox" disabled checked={false} readOnly />
          {t('settings.denoise_enabled')}
        </label>
        <div className="hint">{t('settings.denoise_hint')}</div>
      </div>
    </div>
  )
}

// Mic test lives entirely in this renderer (mirrors MicrophoneMonitor).
async function startMicTest(
  deviceId: string | null,
  onLevel: (level: number) => void
): Promise<{ stop(): void }> {
  const { CAPTURE_PROCESSOR_SRC, CAPTURE_PROCESSOR_NAME } = await import('../audio/capture-processor')
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false
    } as MediaTrackConstraints,
    video: false
  })
  const context = new AudioContext()
  const blobUrl = URL.createObjectURL(new Blob([CAPTURE_PROCESSOR_SRC], { type: 'application/javascript' }))
  await context.audioWorklet.addModule(blobUrl)
  URL.revokeObjectURL(blobUrl)
  const source = context.createMediaStreamSource(stream)
  const node = new AudioWorkletNode(context, CAPTURE_PROCESSOR_NAME)
  node.port.onmessage = (e: MessageEvent<{ level: number }>) => onLevel(e.data.level)
  source.connect(node)

  return {
    stop(): void {
      node.port.onmessage = null
      node.disconnect()
      stream.getTracks().forEach((t) => t.stop())
      void context.close()
    }
  }
}

// ---- STT ------------------------------------------------------------------------

const STT_MODEL_SUGGESTIONS = ['SenseVoiceSmall', 'whisper-1']

export function SttTab({ draft, update }: TabProps): JSX.Element {
  const { t } = useApp()
  return (
    <div className="group">
      <div className="group-title">{t('settings.stt_api')}</div>
      <Field label={t('settings.api_key')}>
        <PasswordInput value={draft.asr.api_key} onChange={(v) => update((d) => void (d.asr.api_key = v))} />
      </Field>
      <Field label={t('settings.base_url')}>
        <input type="text" value={draft.asr.base_url} onChange={(e) => update((d) => void (d.asr.base_url = e.target.value))} />
      </Field>
      <Field label={t('settings.model')}>
        {draft.asr.streaming_enabled ? (
          <input type="text" value={draft.asr.model} onChange={(e) => update((d) => void (d.asr.model = e.target.value))} />
        ) : (
          <ModelPicker
            kind="asr"
            value={draft.asr.model}
            suggestions={STT_MODEL_SUGGESTIONS}
            onChange={(v) => update((d) => void (d.asr.model = v))}
          />
        )}
      </Field>
      <Field label={t('settings.language')}>
        <select value={draft.asr.language} onChange={(e) => update((d) => void (d.asr.language = e.target.value))}>
          {ASR_LANGUAGES.map((l) => (
            <option key={l} value={l}>
              {l === 'auto' ? t('settings.lang_auto') : l}
            </option>
          ))}
        </select>
      </Field>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={draft.asr.streaming_enabled}
          onChange={(e) => update((d) => void (d.asr.streaming_enabled = e.target.checked))}
        />
        {t('settings.streaming_enabled')}
      </label>
      <div className="hint">{t('settings.streaming_hint')}</div>
    </div>
  )
}

// ---- Polish ----------------------------------------------------------------------

const POLISH_MODEL_SUGGESTIONS = [
  'gpt-4o',
  'gpt-4o-mini',
  'gpt-4-turbo',
  'claude-sonnet-4-5',
  'deepseek-chat',
  'qwen-plus',
  'qwen-max'
]

export function PolishTab({ draft, update }: TabProps): JSX.Element {
  const { t } = useApp()
  return (
    <div className="group">
      <div className="group-title">{t('settings.polish_api')}</div>
      <Field label={t('settings.api_key')}>
        <PasswordInput value={draft.polish.api_key} onChange={(v) => update((d) => void (d.polish.api_key = v))} />
      </Field>
      <Field label={t('settings.base_url')}>
        <input type="text" value={draft.polish.base_url} onChange={(e) => update((d) => void (d.polish.base_url = e.target.value))} />
      </Field>
      <Field label={t('settings.model')}>
        <ModelPicker
          kind="polish"
          value={draft.polish.model}
          suggestions={POLISH_MODEL_SUGGESTIONS}
          onChange={(v) => update((d) => void (d.polish.model = v))}
        />
      </Field>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={draft.polish.enabled}
          onChange={(e) => update((d) => void (d.polish.enabled = e.target.checked))}
        />
        {t('settings.polish_enabled')}
      </label>
      <Field label={t('settings.polish_style')}>
        <select value={draft.polish.style} onChange={(e) => update((d) => void (d.polish.style = e.target.value))}>
          {POLISH_STYLES.map((s) => (
            <option key={s} value={s}>
              {t(`settings.polish_style_${s}`)}
            </option>
          ))}
        </select>
      </Field>
    </div>
  )
}

// ---- Glossary ----------------------------------------------------------------------

export function GlossaryTab({ draft, update, showToast }: TabProps): JSX.Element {
  const { t, format } = useApp()
  const [selected, setSelected] = useState(-1)
  const entries = draft.glossary

  const setEntry = (i: number, mutate: (e: GlossaryEntry) => void): void => {
    update((d) => {
      const entry = d.glossary[i]
      if (entry) mutate(entry)
    })
  }

  return (
    <div className="group">
      <div className="group-title">{t('settings.glossary_group')}</div>
      <table className="glossary-table">
        <thead>
          <tr>
            <th style={{ width: '50%' }}>{t('settings.glossary_source')}</th>
            <th style={{ width: '50%' }}>{t('settings.glossary_replacement')}</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry, i) => (
            <tr key={i} className={i === selected ? 'selected' : ''} onClick={() => setSelected(i)}>
              <td>
                <input
                  type="text"
                  value={entry.source}
                  onChange={(e) => setEntry(i, (en) => void (en.source = e.target.value))}
                />
              </td>
              <td>
                <input
                  type="text"
                  value={entry.replacement}
                  onChange={(e) => setEntry(i, (en) => void (en.replacement = e.target.value))}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="field">
        <label />
        <div className="control">
          <button
            onClick={() => {
              update((d) => d.glossary.push({ source: '', replacement: '' }))
              setSelected(entries.length)
            }}
          >
            {t('settings.glossary_add')}
          </button>
          <button
            className="danger"
            disabled={selected < 0}
            onClick={() => {
              update((d) => d.glossary.splice(selected, 1))
              setSelected(-1)
            }}
          >
            {t('settings.glossary_remove')}
          </button>
          <button
            onClick={() => {
              void windowApi.importGlossaryCsv().then((res) => {
                if (res.canceled) return
                if (res.ok && res.entries) {
                  update((d) => void (d.glossary = res.entries!))
                  showToast(t('settings.glossary_import_csv_success'))
                } else if (res.error === 'empty') {
                  showToast(t('settings.glossary_import_csv_empty'))
                } else if (res.error) {
                  showToast(format(t('settings.glossary_import_csv_failed'), { error: res.error }))
                }
              })
            }}
          >
            {t('settings.glossary_import_csv')}
          </button>
          <button
            onClick={() => {
              void windowApi.exportGlossaryCsv(entries).then((res) => {
                if (res.canceled) return
                if (res.ok) showToast(t('settings.glossary_export_csv_success'))
                else if (res.error) showToast(format(t('settings.glossary_export_csv_failed'), { error: res.error }))
              })
            }}
          >
            {t('settings.glossary_export_csv')}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---- Output ------------------------------------------------------------------------

export function OutputTab({ draft, update }: TabProps): JSX.Element {
  const { t } = useApp()
  return (
    <div className="group">
      <div className="group-title">{t('settings.output')}</div>
      <Field label={t('settings.paste_delay')}>
        <input
          type="text"
          value={draft.output.paste_delay_ms}
          style={{ width: 90 }}
          onChange={(e) => {
            const v = Number(e.target.value.replace(/\D/g, '') || 0)
            update((d) => void (d.output.paste_delay_ms = Math.max(0, Math.min(2000, v))))
          }}
        />
        <span className="hint" style={{ margin: 0 }}>
          ms
        </span>
      </Field>
      <Field label={t('settings.paste_mode')}>
        <select value={draft.output.paste_mode} onChange={(e) => update((d) => void (d.output.paste_mode = e.target.value))}>
          {PASTE_MODES.map((m) => (
            <option key={m} value={m}>
              {t(`settings.paste_mode_${m}`)}
            </option>
          ))}
        </select>
      </Field>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={draft.output.auto_paste}
          onChange={(e) => update((d) => void (d.output.auto_paste = e.target.checked))}
        />
        {t('settings.auto_paste')}
      </label>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={draft.output.continuous_mode}
          onChange={(e) => update((d) => void (d.output.continuous_mode = e.target.checked))}
        />
        {t('settings.continuous_mode')}
      </label>
      <div className="hint">{t('settings.continuous_hint')}</div>
    </div>
  )
}

// ---- Hotkeys -------------------------------------------------------------------------

export function HotkeysTab({ draft, update }: TabProps): JSX.Element {
  const { t } = useApp()
  return (
    <div className="group">
      <div className="group-title">{t('settings.hotkeys')}</div>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={draft.hotkey.toggle_enabled}
          onChange={(e) => update((d) => void (d.hotkey.toggle_enabled = e.target.checked))}
        />
        {t('settings.hotkey_toggle')}
      </label>
      {draft.hotkey.toggle_enabled && (
        <Field label={t('settings.hotkey_toggle_key')}>
          <HotkeyRecorder value={draft.hotkey.toggle_hotkey} onChange={(v) => update((d) => void (d.hotkey.toggle_hotkey = v))} />
        </Field>
      )}
      <div className="hint">{t('settings.hotkey_hint')}</div>
      <div className="hint" dangerouslySetInnerHTML={{ __html: t('settings.hotkey_cancel') }} />
    </div>
  )
}
