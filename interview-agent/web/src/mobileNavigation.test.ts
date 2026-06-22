import assert from 'node:assert/strict'
import test from 'node:test'

import {
  getActiveMobileNavigationItem,
  shouldShowMobileNavigation,
  type MobileNavigationView,
} from './mobileNavigation.ts'

test('shows mobile navigation only on authenticated non-interview views', () => {
  const visibleViews: MobileNavigationView[] = ['dashboard', 'setup', 'profile', 'history', 'insights']
  const hiddenViews: MobileNavigationView[] = ['loading', 'login', 'chat']

  for (const view of visibleViews) {
    assert.equal(shouldShowMobileNavigation(view), true, `${view} should show navigation`)
  }
  for (const view of hiddenViews) {
    assert.equal(shouldShowMobileNavigation(view), false, `${view} should hide navigation`)
  }
})

test('maps navigable views to the correct active item', () => {
  assert.equal(getActiveMobileNavigationItem('dashboard'), 'dashboard')
  assert.equal(getActiveMobileNavigationItem('setup'), 'setup')
  assert.equal(getActiveMobileNavigationItem('history'), 'history')
  assert.equal(getActiveMobileNavigationItem('profile'), 'profile')
})

test('does not mark unrelated or hidden views as active', () => {
  assert.equal(getActiveMobileNavigationItem('insights'), null)
  assert.equal(getActiveMobileNavigationItem('login'), null)
  assert.equal(getActiveMobileNavigationItem('chat'), null)
})
