export const navItems = [
  { label: 'Our story', href: '/story' },
  { label: 'Fixtures', href: '/fixtures' },
  { label: 'Academy', href: '/academy' },
  { label: 'Kabalega 7s', href: '/kabalega-7s' },
  { label: 'Partners', href: '/partners' },
]

export function isCurrent(pathname: string, href: string): boolean {
  return pathname.replace(/\/$/, '') === href.replace(/\/$/, '')
}
