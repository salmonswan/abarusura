import { expect, test } from '@playwright/test'

declare global {
  interface Window {
    __vt: number
  }
}

test('visitors move between pages with a persistent header and current link', async ({ page }) => {
  await page.goto('/')
  const header = await page.getByRole('banner').elementHandle()
  expect(header).not.toBeNull()
  const nav = page.getByRole('navigation', { name: 'Main' })
  const story = nav.getByRole('link', { name: 'Our story', exact: true })
  await story.click()
  await expect(page).toHaveURL(/\/story$/)
  await expect(page.getByRole('heading', { name: 'Our story', exact: true })).toBeVisible()
  await expect(story).toHaveAttribute('aria-current', 'page')
  await expect(story).toHaveCSS('border-bottom-color', 'rgb(230, 37, 41)')
  await expect(nav.locator('[aria-current="page"]')).toHaveCount(1)
  expect(await page.evaluate(() => window.scrollY)).toBe(0)
  expect(await header!.evaluate((element) => element.isConnected)).toBe(true)
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused()
  await page.getByRole('banner').getByRole('link', { name: 'Abarusura RFC', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(nav.locator('[aria-current="page"]')).toHaveCount(0)
})

test('page navigation starts a view transition', async ({ page }) => {
  await page.addInitScript(() => {
    const state = window
    state.__vt = 0
    const startViewTransition = document.startViewTransition.bind(document)
    document.startViewTransition = (...args) => {
      state.__vt += 1
      return startViewTransition(...args)
    }
  })
  await page.goto('/')
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Our story', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Our story', exact: true })).toBeVisible()
  expect(await page.evaluate(() => window.__vt)).toBe(1)
})

test('reduced motion changes pages without a view transition', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.addInitScript(() => {
    const state = window
    state.__vt = 0
    const startViewTransition = document.startViewTransition.bind(document)
    document.startViewTransition = (...args) => {
      state.__vt += 1
      return startViewTransition(...args)
    }
  })
  await page.goto('/')
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Our story', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Our story', exact: true })).toBeVisible()
  expect(await page.evaluate(() => window.__vt)).toBe(0)
})

test('browsers without view transitions change pages without errors', async ({ page }) => {
  const errors: Error[] = []
  page.on('pageerror', (error) => errors.push(error))
  await page.addInitScript(() => {
    delete (Document.prototype as Partial<Document>).startViewTransition
  })
  await page.goto('/')
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Our story', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Our story', exact: true })).toBeVisible()
  expect(errors).toEqual([])
})
