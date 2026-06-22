export type MobileNavigationView =
  | 'loading'
  | 'login'
  | 'dashboard'
  | 'setup'
  | 'chat'
  | 'profile'
  | 'history'
  | 'insights'

export type MobileNavigationItem = 'dashboard' | 'setup' | 'history' | 'profile'

const VISIBLE_VIEWS = new Set<MobileNavigationView>(['dashboard', 'setup', 'profile', 'history', 'insights'])

export function shouldShowMobileNavigation(view: MobileNavigationView): boolean {
  return VISIBLE_VIEWS.has(view)
}

export function getActiveMobileNavigationItem(view: MobileNavigationView): MobileNavigationItem | null {
  if (view === 'dashboard' || view === 'setup' || view === 'history' || view === 'profile') {
    return view
  }
  return null
}
