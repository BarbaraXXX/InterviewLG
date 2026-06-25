import assert from 'node:assert/strict';
import test from 'node:test';

import { isAdminRoute, routeToUserView, ROUTES, userViewToRoute } from './routes.ts';

test('maps top-level user views to stable routes', () => {
  assert.equal(userViewToRoute('login'), ROUTES.login);
  assert.equal(userViewToRoute('dashboard'), ROUTES.dashboard);
  assert.equal(userViewToRoute('setup'), ROUTES.setup);
  assert.equal(userViewToRoute('profile'), ROUTES.profile);
  assert.equal(userViewToRoute('history'), ROUTES.history);
  assert.equal(userViewToRoute('insights'), ROUTES.insights);
});

test('does not assign phase-one routes to transient user views', () => {
  assert.equal(userViewToRoute('loading'), null);
  assert.equal(userViewToRoute('chat'), null);
});

test('maps stable routes back to user views', () => {
  assert.equal(routeToUserView('/'), 'dashboard');
  assert.equal(routeToUserView('/login'), 'login');
  assert.equal(routeToUserView('/dashboard'), 'dashboard');
  assert.equal(routeToUserView('/setup'), 'setup');
  assert.equal(routeToUserView('/profile'), 'profile');
  assert.equal(routeToUserView('/history'), 'history');
  assert.equal(routeToUserView('/insights'), 'insights');
});

test('ignores unknown and resource routes for phase one', () => {
  assert.equal(routeToUserView('/unknown'), null);
  assert.equal(routeToUserView('/interview/session-1'), null);
  assert.equal(routeToUserView('/history/session-1'), null);
});

test('recognizes dedicated admin routes', () => {
  assert.equal(isAdminRoute('/admin'), true);
  assert.equal(isAdminRoute('/admin/login'), true);

  assert.equal(isAdminRoute('/'), false);
  assert.equal(isAdminRoute('/dashboard'), false);
  assert.equal(isAdminRoute('/admin/users'), false);
  assert.equal(isAdminRoute('/login'), false);
});
