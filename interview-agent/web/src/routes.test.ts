import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ADMIN_ROUTE_ENTRIES,
  getRouteSessionId,
  isAdminRoute,
  routeToUserView,
  ROUTES,
  USER_RESOURCE_ROUTE_ENTRIES,
  USER_TOP_LEVEL_ROUTE_ENTRIES,
  userViewToRoute,
} from './routes.ts';

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

test('maps resource routes to owning user views', () => {
  assert.equal(routeToUserView('/unknown'), null);
  assert.equal(routeToUserView('/interview/session-1'), 'chat');
  assert.equal(routeToUserView('/history/session-1'), 'history');
});

test('recognizes dedicated admin routes', () => {
  assert.equal(isAdminRoute('/admin'), true);
  assert.equal(isAdminRoute('/admin/login'), true);

  assert.equal(isAdminRoute('/'), false);
  assert.equal(isAdminRoute('/dashboard'), false);
  assert.equal(isAdminRoute('/admin/users'), false);
  assert.equal(isAdminRoute('/login'), false);
});

test('exposes complete top-level route entries for route rendering', () => {
  assert.deepEqual(
    USER_TOP_LEVEL_ROUTE_ENTRIES.map((entry) => [entry.path, entry.view]),
    [
      [ROUTES.login, 'login'],
      [ROUTES.dashboard, 'dashboard'],
      [ROUTES.setup, 'setup'],
      [ROUTES.profile, 'profile'],
      [ROUTES.history, 'history'],
      [ROUTES.insights, 'insights'],
    ],
  );

  assert.deepEqual(
    ADMIN_ROUTE_ENTRIES.map((entry) => entry.path),
    [ROUTES.adminLogin, ROUTES.admin],
  );
});

test('exposes resource route entries for session-scoped pages', () => {
  assert.deepEqual(
    USER_RESOURCE_ROUTE_ENTRIES.map((entry) => [entry.path, entry.view]),
    [
      ['/interview/:sessionId', 'chat'],
      ['/history/:sessionId', 'history'],
    ],
  );
});

test('extracts session ids from resource paths', () => {
  assert.equal(getRouteSessionId('/interview/session-1', 'interview'), 'session-1');
  assert.equal(getRouteSessionId('/history/session-2', 'history'), 'session-2');
  assert.equal(getRouteSessionId('/history/session-2', 'interview'), null);
  assert.equal(getRouteSessionId('/history', 'history'), null);
});
