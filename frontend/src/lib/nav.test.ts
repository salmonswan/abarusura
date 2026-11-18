import { describe, expect, it } from 'vitest'
import { isCurrent, navItems } from './nav'

describe('navItems', () => {
  it('lists the five destinations in header order', () => {
    expect(navItems).toEqual([
      { label: 'Our story', href: '/story' },
      { label: 'Fixtures', href: '/fixtures' },
      { label: 'Academy', href: '/academy' },
      { label: 'Kabalega 7s', href: '/kabalega-7s' },
      { label: 'Partners', href: '/partners' },
    ])
  })
})

describe('isCurrent', () => {
  it.each([
    ['/story', '/story', true],
    ['/story/', '/story', true],
    ['/story', '/story/', true],
    ['/story/', '/story/', true],
    ['/', '/story', false],
    ['/story', '/', false],
    ['/story/child', '/story', false],
  ])('compares %s with %s as %s', (pathname, href, current) => {
    expect(isCurrent(pathname, href)).toBe(current)
  })
})
