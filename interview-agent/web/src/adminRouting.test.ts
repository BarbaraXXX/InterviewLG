import assert from 'node:assert/strict';
import test from 'node:test';

import { isAdminPath } from './adminRouting.ts';

test('recognizes only dedicated admin entry paths', () => {
  assert.equal(isAdminPath('/admin'), true);
  assert.equal(isAdminPath('/admin/login'), true);

  assert.equal(isAdminPath('/'), false);
  assert.equal(isAdminPath('/dashboard'), false);
  assert.equal(isAdminPath('/admin/users'), false);
  assert.equal(isAdminPath('/login'), false);
});
