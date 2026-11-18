import { expect, test, type Page } from '@playwright/test'

const firstAlt = "Abarusura women's side running in attack"
const secondAlt = 'Players smiling before a match'
const heading = "Kabalega's warriors play rugby"

async function expectPhoto(page: Page, alt: string) {
  const exposed = page.locator('.opening').getByRole('img')
  await expect(exposed).toHaveCount(1)
  await expect(exposed).toHaveAttribute('aria-label', alt)
}

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.route('**/images/*.jpg', (route) => route.fulfill({ status: 404, body: '' }))
  await page.clock.install({ time: new Date('2026-11-18T00:00:00Z') })
})

test('plays through the photos with three hidden progress bars', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Pause', exact: true })).toBeVisible()
  await expect(page.locator('.progress')).toHaveAttribute('aria-hidden', 'true')
  await expect(page.locator('.progress .bar')).toHaveCount(3)
  await expectPhoto(page, firstAlt)
  await page.clock.runFor(6100)
  await expectPhoto(page, secondAlt)
})

test('pause saves the flag and stops photos, zoom and the bar', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Pause', exact: true }).click()
  const play = page.getByRole('button', { name: 'Play', exact: true })
  await expect(play).toBeVisible()
  await expect(play).not.toHaveAttribute('aria-pressed')
  expect(await page.evaluate(() => sessionStorage.getItem('abar-paused'))).toBe('1')
  await page.clock.runFor(20000)
  await expectPhoto(page, firstAlt)
  await expect(page.locator('.photo.active')).toHaveCSS('animation-play-state', 'paused')
  await expect(page.locator('.bar.active')).toHaveCSS('animation-play-state', 'paused')
})

test('play uses only the time left before pause', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Pause', exact: true })).toBeVisible()
  await page.clock.runFor(2000)
  await page.getByRole('button', { name: 'Pause', exact: true }).click()
  await page.clock.runFor(20000)
  await page.getByRole('button', { name: 'Play', exact: true }).click()
  expect(await page.evaluate(() => sessionStorage.getItem('abar-paused'))).toBe('0')
  await page.clock.runFor(3900)
  await expectPhoto(page, firstAlt)
  await page.clock.runFor(200)
  await expectPhoto(page, secondAlt)
})

test('pause survives navigation and returns to the first photo at the start', async ({ page }) => {
  // Freeze before loading so hydration and assertions cannot consume slideshow time.
  await page.clock.pauseAt(new Date('2026-11-18T00:00:01Z'))
  await page.goto('/')
  // The control appears only after onMount has started the slideshow.
  await expect(page.getByRole('button', { name: 'Pause', exact: true })).toBeVisible()
  await page.clock.runFor(6100)
  await expectPhoto(page, secondAlt)
  await page.getByRole('button', { name: 'Pause', exact: true }).click()
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Fixtures', exact: true }).click()
  await expect(page).toHaveURL(/\/fixtures$/)
  await page.getByRole('banner').getByRole('link', { name: 'Abarusura RFC', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Play', exact: true })).toBeVisible()
  await expectPhoto(page, firstAlt)
  await expect(page.locator('.bar.active')).toHaveCSS('transform', 'matrix(0, 0, 0, 1, 0, 0)')
  await page.clock.runFor(10000)
  await expectPhoto(page, firstAlt)
})

test('a new browser session plays even when the previous session paused', async ({ page, browser, baseURL }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Pause', exact: true }).click()
  const context = await browser.newContext({ baseURL, reducedMotion: 'no-preference' })
  try {
    const fresh = await context.newPage()
    await fresh.route('**/images/*.jpg', (route) => route.fulfill({ status: 404, body: '' }))
    await fresh.clock.install()
    await fresh.goto('/')
    await expect(fresh.getByRole('button', { name: 'Pause', exact: true })).toBeVisible()
    await fresh.clock.runFor(6100)
    await expectPhoto(fresh, secondAlt)
  } finally {
    await context.close()
  }
})

test('reduced motion keeps only the first photo and no motion controls', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await expect(page.getByRole('button', { name: /^(Pause|Play)$/ })).toHaveCount(0)
  await expect(page.locator('.progress')).toHaveCount(0)
  await expectPhoto(page, firstAlt)
  await expect(page.locator('.photo').first()).toHaveCSS('animation-name', 'none')
  await page.clock.runFor(20000)
  await expectPhoto(page, firstAlt)
})

test.describe('with scripts off', () => {
  test.use({ javaScriptEnabled: false })

  test('keeps the first photo still with no dead control', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('button', { name: /^(Pause|Play)$/ })).toHaveCount(0)
    await expect(page.locator('.progress')).toHaveCount(0)
    await expectPhoto(page, firstAlt)
    await expect(page.locator('.photo').first()).toHaveCSS('animation-name', 'none')
  })
})

test('missing photos leave readable text on navy and a working Pause', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
  await expect(page.locator('.opening')).toHaveCSS('background-color', 'rgb(12, 20, 50)')
  await page.getByRole('button', { name: 'Pause', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Play', exact: true })).toBeVisible()
  await page.clock.runFor(20000)
  await expectPhoto(page, firstAlt)
})
