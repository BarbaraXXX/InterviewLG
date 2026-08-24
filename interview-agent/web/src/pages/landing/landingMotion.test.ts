import assert from 'node:assert/strict'
import test from 'node:test'

import { getRevealDelay, resolveLandingMotionMode } from './landingMotion.ts'

test('disables observed motion when reduced motion is requested or observers are unavailable', () => {
  assert.equal(resolveLandingMotionMode(true, true), 'static')
  assert.equal(resolveLandingMotionMode(false, false), 'static')
  assert.equal(resolveLandingMotionMode(false, true), 'observe')
})

test('staggered reveal delays stay short and bounded', () => {
  assert.equal(getRevealDelay(0), 0)
  assert.equal(getRevealDelay(1), 70)
  assert.equal(getRevealDelay(3), 210)
  assert.equal(getRevealDelay(20), 280)
  assert.equal(getRevealDelay(-1), 0)
})
