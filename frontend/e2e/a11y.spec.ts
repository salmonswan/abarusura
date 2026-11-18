import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const pages = ['/']

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
}

test('axe detects an image without alt text', async ({ page }) => {
  await page.setContent('<html lang="en"><title>t</title><img src="x.png"></html>')

  const { violations } = await new AxeBuilder({ page }).analyze()

  expect(violations.some(({ id }) => id === 'image-alt')).toBe(true)
})
