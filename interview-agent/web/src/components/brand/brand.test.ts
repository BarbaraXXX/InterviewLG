import assert from 'node:assert/strict'
import test from 'node:test'

import { BRAND_ACCESSIBLE_LABEL, BRAND_NAME, BRAND_TAGLINE, getBrandPresentation } from './brand.ts'

test('uses the confirmed Chinese product tagline', () => {
  assert.equal(BRAND_TAGLINE, 'AI 技术面试训练')
})

test('wordmark presentation exposes the full brand without duplicating accessible text', () => {
  assert.deepEqual(getBrandPresentation('wordmark'), {
    accessibleLabel: BRAND_ACCESSIBLE_LABEL,
    name: BRAND_NAME,
    showWordmark: true,
  })
})

test('compact presentation keeps an accessible label while hiding the visible wordmark', () => {
  assert.deepEqual(getBrandPresentation('compact'), {
    accessibleLabel: BRAND_ACCESSIBLE_LABEL,
    name: BRAND_NAME,
    showWordmark: false,
  })
})

test('custom accessible labels are trimmed and blank labels fall back to the product label', () => {
  assert.equal(getBrandPresentation('compact', '  返回问砺首页  ').accessibleLabel, '返回问砺首页')
  assert.equal(getBrandPresentation('compact', '   ').accessibleLabel, BRAND_ACCESSIBLE_LABEL)
})
