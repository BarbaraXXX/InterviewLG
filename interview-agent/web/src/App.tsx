import { Component, lazy, Suspense, useEffect, useState, type ErrorInfo, type ReactNode } from 'react'
import { Route, Routes, useLocation } from 'react-router-dom'

import { BrandMark } from './components/brand'
import { isThemeMode, resolveInitialTheme, THEME_STORAGE_KEY, type ThemeMode } from './components/theme'
import { LandingPage } from './pages/landing'
import { ROUTES } from './routes'
import { APP_VERSION } from './version'

const Application = lazy(() => import('./app/Application'))

const AUTH_SESSION_KEY = 'interviewlg_active_session'

function getInitialTheme(): ThemeMode {
  const documentTheme = document.documentElement.dataset.theme
  if (isThemeMode(documentTheme)) return documentTheme

  let storedTheme: string | null = null
  try {
    storedTheme = localStorage.getItem(THEME_STORAGE_KEY)
  } catch {
    // Storage can be unavailable in restricted browser modes.
  }

  return resolveInitialTheme(storedTheme, Boolean(window.matchMedia?.('(prefers-color-scheme: light)').matches))
}

function applyTheme(theme: ThemeMode): void {
  document.documentElement.dataset.theme = theme
  document.documentElement.style.colorScheme = theme
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    // The selected theme still applies to this page when storage is unavailable.
  }
}

function hasActiveBrowserSession(): boolean {
  try {
    return sessionStorage.getItem(AUTH_SESSION_KEY) === '1'
  } catch {
    return false
  }
}

function ApplicationFallback() {
  return (
    <main className="route-loading" aria-live="polite" aria-busy="true">
      <BrandMark variant="compact" size="md" />
      <div>
        <strong>正在进入问砺</strong>
        <span>正在加载你的面试训练工作区。</span>
      </div>
    </main>
  )
}

class ApplicationErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Application chunk failed to load', error, info.componentStack)
  }

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      <main className="route-error" role="alert">
        <BrandMark size="md" />
        <h1>工作区加载失败</h1>
        <p>可能是网络暂时中断，或页面版本刚刚更新。请刷新后重试。</p>
        <div>
          <button type="button" onClick={() => window.location.reload()}>
            重新加载
          </button>
          <a href={ROUTES.root}>返回产品首页</a>
        </div>
      </main>
    )
  }
}

function App() {
  const location = useLocation()
  const [theme, setTheme] = useState<ThemeMode>(getInitialTheme)

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  const toggleTheme = () => {
    setTheme((current) => (current === 'dark' ? 'light' : 'dark'))
  }

  const isAuthenticated = location.pathname === ROUTES.root && hasActiveBrowserSession()

  return (
    <Routes>
      <Route
        path={ROUTES.root}
        element={
          <LandingPage
            appVersion={APP_VERSION}
            isAuthenticated={isAuthenticated}
            onThemeToggle={toggleTheme}
            theme={theme}
          />
        }
      />
      <Route
        path="*"
        element={
          <ApplicationErrorBoundary>
            <Suspense fallback={<ApplicationFallback />}>
              <Application theme={theme} onToggleTheme={toggleTheme} />
            </Suspense>
          </ApplicationErrorBoundary>
        }
      />
    </Routes>
  )
}

export default App
