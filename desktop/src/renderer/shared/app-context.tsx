// App-wide React context: live config, resolved theme, language, and i18n.
// Every window root wraps itself in <AppProvider>; config/theme updates arrive
// over the 'evt' bus and re-render subscribers.

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { AppConfig } from '../../shared/types'
import { setLanguage, t as translate } from '../../shared/i18n'
import { windowApi } from './api-binding'

interface AppState {
  config: AppConfig | null
  theme: 'dark' | 'light'
  t(key: string): string
  format(template: string, params: Record<string, string | number>): string
}

const AppContext = createContext<AppState>({
  config: null,
  theme: 'dark',
  t: translate,
  format: (tpl) => tpl
})

export function useApp(): AppState {
  return useContext(AppContext)
}

export function AppProvider({ children }: { children: ReactNode }): JSX.Element {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')
  const [langTick, setLangTick] = useState(0)

  useEffect(() => {
    void windowApi.getConfig().then((cfg) => {
      setConfig(cfg)
      setLanguage(cfg.language)
      setLangTick((n) => n + 1)
    })
    const off = windowApi.onEvt((msg) => {
      if (msg.type === 'config' && msg.config) {
        const cfg = msg.config as AppConfig
        setConfig(cfg)
        setLanguage(cfg.language)
        setLangTick((n) => n + 1)
      }
      if (msg.theme === 'dark' || msg.theme === 'light') setTheme(msg.theme)
    })
    return off
  }, [])

  const t = useCallback((key: string) => translate(key), [langTick])

  // Apply theme variables to the document root on every change.
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    import('./theme-css').then((m) => m.applyThemeVars(document.documentElement, theme))
  }, [theme])

  const value = useMemo<AppState>(
    () => ({
      config,
      theme,
      t,
      format: (tpl, params) => tpl.replace(/\{(\w+)\}/g, (_, k: string) => String(params[k] ?? ''))
    }),
    [config, theme, t]
  )

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}
