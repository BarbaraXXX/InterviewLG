import type { MobileNavigationView } from './mobileNavigation';

export const ROUTES = {
  root: '/',
  login: '/login',
  dashboard: '/dashboard',
  setup: '/setup',
  profile: '/profile',
  history: '/history',
  insights: '/insights',
  admin: '/admin',
  adminLogin: '/admin/login',
  interview: (sessionId: string) => `/interview/${sessionId}`,
  historyDetail: (sessionId: string) => `/history/${sessionId}`,
} as const;

const USER_VIEW_ROUTES: Partial<Record<MobileNavigationView, string>> = {
  login: ROUTES.login,
  dashboard: ROUTES.dashboard,
  setup: ROUTES.setup,
  profile: ROUTES.profile,
  history: ROUTES.history,
  insights: ROUTES.insights,
};

export const USER_TOP_LEVEL_ROUTE_ENTRIES = [
  { path: ROUTES.login, view: 'login' },
  { path: ROUTES.dashboard, view: 'dashboard' },
  { path: ROUTES.setup, view: 'setup' },
  { path: ROUTES.profile, view: 'profile' },
  { path: ROUTES.history, view: 'history' },
  { path: ROUTES.insights, view: 'insights' },
] as const satisfies ReadonlyArray<{ path: string; view: MobileNavigationView }>;

export const USER_RESOURCE_ROUTE_ENTRIES = [
  { path: ROUTES.interview(':sessionId'), view: 'chat' },
  { path: ROUTES.historyDetail(':sessionId'), view: 'history' },
] as const satisfies ReadonlyArray<{ path: string; view: MobileNavigationView }>;

export const ADMIN_ROUTE_ENTRIES = [
  { path: ROUTES.adminLogin },
  { path: ROUTES.admin },
] as const satisfies ReadonlyArray<{ path: string }>;

const USER_ROUTE_VIEWS = new Map<string, MobileNavigationView>([
  [ROUTES.root, 'dashboard'],
  [ROUTES.login, 'login'],
  [ROUTES.dashboard, 'dashboard'],
  [ROUTES.setup, 'setup'],
  [ROUTES.profile, 'profile'],
  [ROUTES.history, 'history'],
  [ROUTES.insights, 'insights'],
]);

export function userViewToRoute(view: MobileNavigationView): string | null {
  return USER_VIEW_ROUTES[view] ?? null;
}

export function routeToUserView(pathname: string): MobileNavigationView | null {
  const topLevelView = USER_ROUTE_VIEWS.get(pathname);
  if (topLevelView) return topLevelView;
  if (getRouteSessionId(pathname, 'interview')) return 'chat';
  if (getRouteSessionId(pathname, 'history')) return 'history';
  return null;
}

export function resolveAuthenticatedUserView(
  pathname: string,
  fallbackView: MobileNavigationView,
): MobileNavigationView {
  const routeView = routeToUserView(pathname);
  return routeView && routeView !== 'login' ? routeView : fallbackView;
}

export function isAdminRoute(pathname: string): boolean {
  return pathname === ROUTES.admin || pathname === ROUTES.adminLogin;
}

export function getRouteSessionId(pathname: string, resource: 'interview' | 'history'): string | null {
  const prefix = `/${resource}/`;
  if (!pathname.startsWith(prefix)) return null;
  const sessionId = pathname.slice(prefix.length);
  if (!sessionId || sessionId.includes('/')) return null;
  return decodeURIComponent(sessionId);
}
