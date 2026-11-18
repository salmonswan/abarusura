import { expect, test } from '@playwright/test'

const pages = [
  { path: '/', title: 'Abarusura RFC' },
  { path: '/story', title: 'Our story · Abarusura RFC', kicker: 'SINCE 2025' },
  { path: '/fixtures', title: 'Fixtures and results · Abarusura RFC', kicker: 'SEASON 2026/27' },
  { path: '/academy', title: 'Academy · Abarusura RFC', kicker: '5 PRIMARY · 3 SECONDARY SCHOOLS' },
  { path: '/kabalega-7s', title: 'Kabalega 7s · Abarusura RFC', kicker: 'OUR TOURNAMENT' },
  { path: '/partners', title: 'Partners · Abarusura RFC', kicker: 'HOIMA' },
]

for (const { path, title, kicker } of pages) {
  test(`${path} has the shared shell and page title`, async ({ page }) => {
    await page.goto(path)
    await expect(page).toHaveTitle(title)
    const header = page.getByRole('banner')
    await expect(header).toHaveCount(1)
    const home = header.getByRole('link', { name: 'Abarusura RFC', exact: true })
    await expect(home).toHaveCount(1)
    await expect(home).toHaveAttribute('href', '/')
    const nav = header.getByRole('navigation', { name: 'Main' })
    await expect(nav.getByRole('link')).toHaveText([
      'Our story', 'Fixtures', 'Academy', 'Kabalega 7s', 'Partners',
    ])
    const hrefs = await nav.getByRole('link').evaluateAll((links) => links.map((link) => link.getAttribute('href')))
    expect(hrefs).toEqual(['/story', '/fixtures', '/academy', '/kabalega-7s', '/partners'])
    await expect(header.getByRole('link', { name: 'Join the club', exact: true })).toHaveAttribute('href', '/story')
    await expect(page.getByRole('contentinfo')).toHaveText('Abarusura Rugby Football Club · A member of Uganda Rugby Union · Hoima')
    if (kicker) {
      const stripe = page.locator('.stripe')
      await expect(stripe).toHaveCount(1)
      await expect(stripe).toHaveCSS('height', '12px')
      await expect(stripe).toHaveCSS('background-image', /repeating-linear-gradient/)
      await expect(page.locator('.kicker')).toHaveText(kicker)
      await expect(page.locator('.kicker')).toHaveCSS('color', 'rgb(247, 37, 41)')
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(title.split(' · ')[0])
    }
  })

  test(`${path} starts keyboard navigation with the skip link`, async ({ page }) => {
    await page.goto(path)
    await page.keyboard.press('Tab')
    await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(page.locator('#main')).toBeFocused()
  })
}

test('all six page titles are different', async ({ page }) => {
  const titles = []
  for (const { path } of pages) {
    await page.goto(path)
    titles.push(await page.title())
  }
  expect(titles[0]).toBe('Abarusura RFC')
  expect(new Set(titles).size).toBe(6)
})

test('Oswald is served locally without Google Fonts requests', async ({ page }) => {
  const googleRequests: string[] = []
  page.on('request', (request) => {
    if (['fonts.googleapis.com', 'fonts.gstatic.com'].includes(new URL(request.url()).hostname)) {
      googleRequests.push(request.url())
    }
  })
  const fontResponse = page.waitForResponse((response) => new URL(response.url()).pathname === '/fonts/oswald-latin-700-normal.woff2')
  await page.goto('/story')
  expect((await fontResponse).status()).toBe(200)
  const loaded = await page.evaluate(async () => {
    await document.fonts.ready
    return document.fonts.check('700 20px Oswald')
  })
  expect(loaded).toBe(true)
  expect(googleRequests).toEqual([])
})
