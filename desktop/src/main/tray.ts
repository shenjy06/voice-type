// System tray — port of ui/system_tray.py TrayIcon: status badge, full context
// menu with quick settings (checkbox items debounce config writes by 500ms),
// and failure-retry entry.

import { Menu, Tray, app } from 'electron'
import type { AppConfig } from '../shared/types'
import { ASR_LANGUAGES, POLISH_STYLES, PASTE_MODES } from '../shared/types'
import { t, format } from '../shared/i18n'
import { createBadgeImage } from './tray-icon'
import { DARK_PALETTE } from '../shared/theme'

export interface TrayCallbacks {
  onShowWindow(): void
  onToggleRecording(): void
  onRetry(): void
  onOpenSettings(): void
  onOpenHistory(): void
  onQuit(): void
  /** Persist quick-setting toggles (already merged into the passed config). */
  onUpdateConfig(mutate: (config: AppConfig) => void): void
}

export class TrayController {
  private tray: Tray | null = null
  private config: AppConfig
  private cb: TrayCallbacks
  private state: 'idle' | 'recording' | 'processing' | 'error' = 'idle'
  private retryAvailable = false

  constructor(config: AppConfig, cb: TrayCallbacks) {
    this.config = config
    this.cb = cb
  }

  init(): void {
    this.tray = new Tray(createBadgeImage('T', DARK_PALETTE.accent))
    this.tray.setToolTip(t('tray.tooltip'))
    this.tray.on('double-click', () => this.cb.onShowWindow())
    this.rebuildMenu()
  }

  setState(state: typeof this.state): void {
    this.state = state
    if (!this.tray) return
    if (state === 'recording') {
      this.tray.setImage(createBadgeImage('S', DARK_PALETTE.danger))
      this.tray.setToolTip(t('tray.tooltip_recording'))
    } else {
      this.tray.setImage(createBadgeImage('T', DARK_PALETTE.accent))
      this.tray.setToolTip(t('tray.tooltip'))
    }
    this.rebuildMenu()
  }

  setRetryAvailable(available: boolean): void {
    this.retryAvailable = available
    this.rebuildMenu()
  }

  applyConfig(config: AppConfig): void {
    this.config = config
    this.rebuildMenu()
  }

  retranslate(): void {
    if (this.tray) this.tray.setToolTip(this.state === 'recording' ? t('tray.tooltip_recording') : t('tray.tooltip'))
    this.rebuildMenu()
  }

  showNotification(title: string, message: string): void {
    this.tray?.displayBalloon?.({ title, content: message })
  }

  destroy(): void {
    this.tray?.destroy()
    this.tray = null
  }

  /** Quick toggles: the Application merges + debounce-saves + broadcasts. */
  private quickUpdate(mutate: (config: AppConfig) => void): void {
    this.cb.onUpdateConfig(mutate)
  }

  private rebuildMenu(): void {
    if (!this.tray) return
    const recording = this.state === 'recording'
    const menu = Menu.buildFromTemplate([
      {
        label: t('tray.show_window'),
        click: () => this.cb.onShowWindow()
      },
      { type: 'separator' },
      {
        label: recording ? t('tray.stop_recording') : t('tray.start_recording'),
        click: () => this.cb.onToggleRecording()
      },
      {
        label: t('tray.retry'),
        enabled: this.retryAvailable,
        click: () => this.cb.onRetry()
      },
      { type: 'separator' },
      {
        label: t('tray.auto_paste'),
        type: 'checkbox',
        checked: this.config.output.auto_paste,
        click: (item) => this.quickUpdate((c) => void (c.output.auto_paste = item.checked))
      },
      {
        label: t('tray.continuous_mode'),
        type: 'checkbox',
        checked: this.config.output.continuous_mode,
        click: (item) => this.quickUpdate((c) => void (c.output.continuous_mode = item.checked))
      },
      {
        label: t('tray.polish'),
        type: 'checkbox',
        checked: this.config.polish.enabled,
        click: (item) => this.quickUpdate((c) => void (c.polish.enabled = item.checked))
      },
      {
        label: t('tray.polish_style'),
        submenu: POLISH_STYLES.map((style) => ({
          label: t(`settings.polish_style_${style}`),
          type: 'radio' as const,
          checked: this.config.polish.style === style,
          click: () => this.quickUpdate((c) => void (c.polish.style = style))
        }))
      },
      {
        label: t('tray.paste_mode'),
        submenu: PASTE_MODES.map((mode) => ({
          label: t(`settings.paste_mode_${mode}`),
          type: 'radio' as const,
          checked: this.config.output.paste_mode === mode,
          click: () => this.quickUpdate((c) => void (c.output.paste_mode = mode))
        }))
      },
      {
        label: t('tray.asr_language'),
        submenu: ASR_LANGUAGES.map((lang) => ({
          label: lang === 'auto' ? t('settings.lang_auto') : lang,
          type: 'radio' as const,
          checked: this.config.asr.language === lang,
          click: () => this.quickUpdate((c) => void (c.asr.language = lang))
        }))
      },
      { type: 'separator' },
      { label: t('tray.settings'), click: () => this.cb.onOpenSettings() },
      { label: t('tray.history'), click: () => this.cb.onOpenHistory() },
      { type: 'separator' },
      { label: t('tray.quit'), click: () => this.cb.onQuit() }
    ])
    this.tray.setContextMenu(menu)
  }
}

// Re-export format for tray notification messages composed elsewhere.
export { format, app }
