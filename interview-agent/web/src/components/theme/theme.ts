export const THEME_STORAGE_KEY = 'interviewlg_theme'

export type ThemeMode = 'light' | 'dark'
export type ThemeToggleIcon = 'sun' | 'moon'

export interface ThemeTogglePresentation {
  accessibleLabel: string
  icon: ThemeToggleIcon
  nextTheme: ThemeMode
}

export function isThemeMode(value: string | null | undefined): value is ThemeMode {
  return value === 'light' || value === 'dark'
}

export function resolveInitialTheme(storedTheme: string | null, prefersLight: boolean): ThemeMode {
  if (isThemeMode(storedTheme)) return storedTheme
  return prefersLight ? 'light' : 'dark'
}

export function getThemeTogglePresentation(theme: ThemeMode): ThemeTogglePresentation {
  if (theme === 'light') {
    return {
      accessibleLabel: '切换到深色模式',
      icon: 'moon',
      nextTheme: 'dark',
    }
  }

  return {
    accessibleLabel: '切换到浅色模式',
    icon: 'sun',
    nextTheme: 'light',
  }
}
