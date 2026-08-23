import type { ButtonHTMLAttributes } from 'react'

import { getThemeTogglePresentation, type ThemeMode } from './theme'
import styles from './ThemeToggle.module.css'

export interface ThemeToggleProps extends Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  'aria-label' | 'children' | 'onClick' | 'title' | 'type'
> {
  onToggle: () => void
  theme: ThemeMode
}

export default function ThemeToggle({ className = '', onToggle, theme, ...rest }: ThemeToggleProps) {
  const presentation = getThemeTogglePresentation(theme)
  const classNames = [styles.toggle, className].filter(Boolean).join(' ')

  return (
    <button
      {...rest}
      type="button"
      className={classNames}
      onClick={onToggle}
      aria-label={presentation.accessibleLabel}
      title={presentation.accessibleLabel}
      data-theme-target={presentation.nextTheme}
    >
      {presentation.icon === 'sun' ? (
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
          <circle cx="12" cy="12" r="3.75" stroke="currentColor" strokeWidth="1.8" />
          <path
            d="M12 2.4v2.1M12 19.5v2.1M4.2 4.2l1.5 1.5M18.3 18.3l1.5 1.5M2.4 12h2.1M19.5 12h2.1M4.2 19.8l1.5-1.5M18.3 5.7l1.5-1.5"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
          <path
            d="M20.3 14.15A7.6 7.6 0 0 1 9.85 3.7a8.35 8.35 0 1 0 10.45 10.45Z"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      )}
      <span className={styles.halo} aria-hidden="true" />
    </button>
  )
}
