import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const pages = ['/', '/story', '/fixtures', '/academy', '/kabalega-7s', '/partners']

for (const path of pages) {
  for (const reducedMotion of ['no-preference', 'reduce'] as const) {
    test(`${path} meets WCAG AA with reduced motion ${reducedMotion}`, async ({ page }) => {
      await page.emulateMedia({ reducedMotion })
      await page.goto(path)

      const { violations } = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
        .analyze()

      expect(violations).toEqual([])
    })
  }

  test(`${path} reflows at 320px`, async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 640 })
    await page.goto(path)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320)
  })

  test(`${path} keeps keyboard focus below the sticky header`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await page.goto(path)
    await page.keyboard.press('Tab')
    const first = await page.locator(':focus').elementHandle()
    expect(first).not.toBeNull()

    const expectFocusUnobscured = async () => {
      const bounds = await page.evaluate(() => {
        const header = document.querySelector('header')!
        const focused = document.activeElement!
        return header.contains(focused) || focused === document.body ? null : {
          top: focused.getBoundingClientRect().top,
          headerBottom: header.getBoundingClientRect().bottom,
        }
      })
      if (bounds) expect(bounds.top).toBeGreaterThanOrEqual(bounds.headerBottom)
    }

    await expectFocusUnobscured()
    let wrapped = false
    for (let press = 0; press < 60; press++) {
      await page.keyboard.press('Tab')
      await expectFocusUnobscured()
      if (await first!.evaluate((element) => element === document.activeElement)) {
        wrapped = true
        break
      }
    }
    expect(wrapped).toBe(true)

    wrapped = false
    for (let press = 0; press < 60; press++) {
      await page.keyboard.press('Shift+Tab')
      await expectFocusUnobscured()
      if (await first!.evaluate((element) => element === document.activeElement)) {
        wrapped = true
        break
      }
    }
    expect(wrapped).toBe(true)
  })
}

test('axe detects an image without alt text', async ({ page }) => {
  await page.setContent('<html lang="en"><title>t</title><img src="x.png"></html>')

  const { violations } = await new AxeBuilder({ page }).analyze()

  expect(violations.some(({ id }) => id === 'image-alt')).toBe(true)
})
