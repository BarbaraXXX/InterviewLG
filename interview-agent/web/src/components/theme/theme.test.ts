import assert from 'node:assert/strict'
import test from 'node:test'

import { getThemeTogglePresentation, resolveInitialTheme } from './theme.ts'

test('dark mode toggle announces and renders the light-mode action', () => {
  assert.deepEqual(getThemeTogglePresentation('dark'), {
    accessibleLabel: '切换到浅色模式',
    icon: 'sun',
    nextTheme: 'light',
  })
})

test('light mode toggle announces and renders the dark-mode action', () => {
  assert.deepEqual(getThemeTogglePresentation('light'), {
    accessibleLabel: '切换到深色模式',
    icon: 'moon',
    nextTheme: 'dark',
  })
})

test('stored theme wins and system preference provides the fallback', () => {
  assert.equal(resolveInitialTheme('light', false), 'light')
  assert.equal(resolveInitialTheme('dark', true), 'dark')
  assert.equal(resolveInitialTheme(null, true), 'light')
  assert.equal(resolveInitialTheme('unexpected', false), 'dark')
})
