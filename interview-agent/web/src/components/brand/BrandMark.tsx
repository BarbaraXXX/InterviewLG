import { useId, type ComponentPropsWithoutRef } from 'react'

import { BRAND_TAGLINE, getBrandPresentation, type BrandMarkSize, type BrandMarkVariant } from './brand'
import styles from './BrandMark.module.css'

export interface BrandMarkProps extends Omit<ComponentPropsWithoutRef<'span'>, 'aria-label' | 'children'> {
  accessibleLabel?: string
  size?: BrandMarkSize
  variant?: BrandMarkVariant
}

export default function BrandMark({
  accessibleLabel,
  className = '',
  size = 'md',
  variant = 'wordmark',
  ...rest
}: BrandMarkProps) {
  const presentation = getBrandPresentation(variant, accessibleLabel)
  const instanceId = useId().replaceAll(':', '')
  const surfaceGradientId = `brand-surface-${instanceId}`
  const trailGradientId = `brand-trail-${instanceId}`
  const variantClassName = variant === 'compact' ? styles.compact : styles.withWordmark
  const classNames = [styles.root, styles[size], variantClassName, className].filter(Boolean).join(' ')

  return (
    <span
      {...rest}
      className={classNames}
      role="img"
      aria-label={presentation.accessibleLabel}
      data-brand-variant={variant}
    >
      <svg className={styles.symbol} viewBox="0 0 48 48" fill="none" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id={surfaceGradientId} x1="7" y1="5" x2="42" y2="44" gradientUnits="userSpaceOnUse">
            <stop stopColor="#102a2a" />
            <stop offset="1" stopColor="#071521" />
          </linearGradient>
          <linearGradient id={trailGradientId} x1="12" y1="13" x2="38" y2="34" gradientUnits="userSpaceOnUse">
            <stop stopColor="#4ade80" />
            <stop offset="1" stopColor="#22d3ee" />
          </linearGradient>
        </defs>

        <rect x="1" y="1" width="46" height="46" rx="14" fill={`url(#${surfaceGradientId})`} />
        <rect
          x="1.75"
          y="1.75"
          width="44.5"
          height="44.5"
          rx="13.25"
          stroke={`url(#${trailGradientId})`}
          strokeOpacity="0.72"
          strokeWidth="1.5"
        />
        <path
          d="M13 14.8C13 12.7 14.7 11 16.8 11h14.4c2.1 0 3.8 1.7 3.8 3.8v11.4c0 2.1-1.7 3.8-3.8 3.8h-7.4L17 36v-6.35c-2.28-.45-4-2.46-4-4.85v-10Z"
          stroke="rgba(248, 250, 252, 0.72)"
          strokeWidth="1.65"
          strokeLinejoin="round"
        />
        <path
          d="M17.2 19.2h6.15l-2.7 3.15 3.15 3.2h6.05l3-3.1"
          stroke={`url(#${trailGradientId})`}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="17.2" cy="19.2" r="1.65" fill="#4ade80" />
        <path d="m30.7 20.25 2.55 1.75-1.8 2.5" fill="#22d3ee" />
      </svg>

      {presentation.showWordmark && (
        <span className={styles.wordmarkText} aria-hidden="true">
          <strong>{presentation.name}</strong>
          <small>{BRAND_TAGLINE}</small>
        </span>
      )}
    </span>
  )
}
