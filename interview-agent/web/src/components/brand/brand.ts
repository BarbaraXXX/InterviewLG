export const BRAND_NAME = '问砺'
export const BRAND_TAGLINE = 'AI 技术面试训练'
export const BRAND_ACCESSIBLE_LABEL = '问砺 AI 面试训练'

export type BrandMarkVariant = 'compact' | 'wordmark'
export type BrandMarkSize = 'sm' | 'md' | 'lg'

export interface BrandPresentation {
  accessibleLabel: string
  name: typeof BRAND_NAME
  showWordmark: boolean
}

export function getBrandPresentation(
  variant: BrandMarkVariant,
  accessibleLabel = BRAND_ACCESSIBLE_LABEL,
): BrandPresentation {
  return {
    accessibleLabel: accessibleLabel.trim() || BRAND_ACCESSIBLE_LABEL,
    name: BRAND_NAME,
    showWordmark: variant === 'wordmark',
  }
}
