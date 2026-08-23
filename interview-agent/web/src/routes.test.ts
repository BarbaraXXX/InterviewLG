import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ADMIN_ROUTE_ENTRIES,
  createLoginRoute,
  getRouteSessionId,
  isAdminRoute,
  isProtectedUserRoute,
  isPublicUserRoute,
  resolveAuthenticatedUserView,
  resolveLoginNextPath,
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
  assert.equal(routeToUserView('/'), null);
  assert.equal(routeToUserView('/login'), 'login');
  assert.equal(routeToUserView('/dashboard'), 'dashboard');
  assert.equal(routeToUserView('/setup'), 'setup');
  assert.equal(routeToUserView('/profile'), 'profile');
  assert.equal(routeToUserView('/history'), 'history');
  assert.equal(routeToUserView('/insights'), 'insights');
});

test('distinguishes public pages from protected user routes', () => {
  assert.equal(isPublicUserRoute('/'), true);
  assert.equal(isPublicUserRoute('/login'), true);
  assert.equal(isPublicUserRoute('/dashboard'), false);
  assert.equal(isPublicUserRoute('/interview/session-1'), false);

  assert.equal(isProtectedUserRoute('/dashboard'), true);
  assert.equal(isProtectedUserRoute('/setup'), true);
  assert.equal(isProtectedUserRoute('/history'), true);
  assert.equal(isProtectedUserRoute('/interview/session-1'), true);
  assert.equal(isProtectedUserRoute('/history/session-1'), true);
  assert.equal(isProtectedUserRoute('/'), false);
  assert.equal(isProtectedUserRoute('/login'), false);
  assert.equal(isProtectedUserRoute('/admin'), false);
  assert.equal(isProtectedUserRoute('/unknown'), false);
});

test('accepts only protected local user routes as a login continuation', () => {
  assert.equal(resolveLoginNextPath('/dashboard'), '/dashboard');
  assert.equal(resolveLoginNextPath('/interview/session-1'), '/interview/session-1');
  assert.equal(resolveLoginNextPath('/history/session%202'), '/history/session%202');
  assert.equal(
    resolveLoginNextPath('/interview/session-1?debug_rationale=1#latest-answer'),
    '/interview/session-1?debug_rationale=1#latest-answer',
  );

  assert.equal(resolveLoginNextPath(null), ROUTES.dashboard);
  assert.equal(resolveLoginNextPath(''), ROUTES.dashboard);
  assert.equal(resolveLoginNextPath('/'), ROUTES.dashboard);
  assert.equal(resolveLoginNextPath('/login'), ROUTES.dashboard);
  assert.equal(resolveLoginNextPath('/admin'), ROUTES.dashboard);
  assert.equal(resolveLoginNextPath('https://example.com'), ROUTES.dashboard);
  assert.equal(resolveLoginNextPath('//example.com/dashboard'), ROUTES.dashboard);
  assert.equal(resolveLoginNextPath('/\\example.com/dashboard'), ROUTES.dashboard);
  assert.equal(resolveLoginNextPath('/interview/%'), ROUTES.dashboard);
});

test('builds an encoded login route from a safe continuation', () => {
  assert.equal(createLoginRoute('/setup'), '/login?next=%2Fsetup');
  assert.equal(
    createLoginRoute('/interview/session-1?debug_rationale=1'),
    '/login?next=%2Finterview%2Fsession-1%3Fdebug_rationale%3D1',
  );
  assert.equal(createLoginRoute('https://example.com'), '/login?next=%2Fdashboard');
});

test('resolves authenticated user view from the latest pathname before fallback state', () => {
  assert.equal(resolveAuthenticatedUserView('/setup', 'dashboard'), 'setup');
  assert.equal(resolveAuthenticatedUserView('/history', 'dashboard'), 'history');
  assert.equal(resolveAuthenticatedUserView('/profile', 'dashboard'), 'profile');
  assert.equal(resolveAuthenticatedUserView('/unknown', 'dashboard'), 'dashboard');
  assert.equal(resolveAuthenticatedUserView('/login', 'dashboard'), 'dashboard');
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
  assert.equal(getRouteSessionId('/interview/%', 'interview'), null);
});
