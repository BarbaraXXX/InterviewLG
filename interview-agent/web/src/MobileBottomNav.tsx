import { History, Home, PlusCircle, UserRound, type LucideIcon } from 'lucide-react'

import type { MobileNavigationItem } from './mobileNavigation'

interface MobileBottomNavProps {
  activeItem: MobileNavigationItem | null
  onNavigate: (item: MobileNavigationItem) => void
}

const NAVIGATION_ITEMS: Array<{
  id: MobileNavigationItem
  label: string
  icon: LucideIcon
}> = [
  { id: 'dashboard', label: '工作台', icon: Home },
  { id: 'setup', label: '开始面试', icon: PlusCircle },
  { id: 'history', label: '历史记录', icon: History },
  { id: 'profile', label: '个人中心', icon: UserRound },
]

export default function MobileBottomNav({ activeItem, onNavigate }: MobileBottomNavProps) {
  return (
    <nav className="mobile-bottom-nav" aria-label="移动端主导航">
      {NAVIGATION_ITEMS.map((item) => {
        const Icon = item.icon
        const isActive = item.id === activeItem
        return (
          <button
            key={item.id}
            type="button"
            className={isActive ? 'active' : ''}
            aria-current={isActive ? 'page' : undefined}
            onClick={() => onNavigate(item.id)}
          >
            <Icon size={20} strokeWidth={isActive ? 2.4 : 2} aria-hidden="true" />
            <span>{item.label}</span>
          </button>
        )
      })}
    </nav>
  )
}
