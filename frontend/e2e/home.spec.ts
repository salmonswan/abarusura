import { expect, test, type Page } from '@playwright/test'

test.use({ reducedMotion: 'reduce' })

const heading = "Kabalega's warriors play rugby"
const introduction = 'Named after the elite soldiers of Omukama Kabalega, we grow rugby across Bunyoro and give young players a place to belong.'
const values = ['Discipline', 'Integrity', 'Determination', 'Dedication', 'Diligence']
const stories = [
  {
    title: 'The name',
    description: 'The Abarusura defended the Bunyoro-Kitara Kingdom in the late 19th century.',
    action: 'Read our story →',
    href: '/story',
  },
  {
    title: 'The academy',
    description: '5 primary and 3 secondary schools play with us.',
    action: 'Meet the academy →',
    href: '/academy',
  },
  {
    title: 'Kabalega 7s',
    description: 'Our tournament for clubs across the region.',
    action: 'See the Kabalega 7s →',
    href: '/kabalega-7s',
  },
]

async function expectOpening(page: Page) {
  await expect(page).toHaveTitle('Abarusura RFC')
  const opening = page.getByRole('region', { name: heading })
  await expect(opening).toBeVisible()
  await expect(opening.locator('.kicker')).toHaveText('HOIMA · BUNYORO-KITARA · SINCE 2025')
  await expect(opening.getByRole('heading', { level: 1, name: heading, exact: true })).toBeVisible()
  await expect(opening.getByText(introduction, { exact: true })).toBeVisible()
  await expect(opening.getByRole('link', { name: 'Train with us', exact: true })).toHaveAttribute('href', '/story')
  await expect(opening.getByRole('link', { name: 'Our story', exact: true })).toHaveAttribute('href', '/story')
  await expect(opening.locator('.btn.red')).toHaveText('Train with us')
  await expect(opening.locator('.btn.ghost')).toHaveText('Our story')
}

async function expectPhotos(page: Page) {
  const opening = page.locator('.opening')
  await expect(opening.locator('img')).toHaveCount(0)
  await expect(opening).toHaveCSS('background-color', 'rgb(12, 20, 50)')
  const first = opening.getByRole('img', { name: "Abarusura women's side running in attack", exact: true })
  await expect(first).toBeVisible()
  await expect(first).toHaveCSS('opacity', '1')
  await expect(first).toHaveCSS('background-image', /\/images\/hero-wide\.jpg/)
  for (const alt of ['Players smiling before a match', 'A ball carrier breaks through']) {
    await expect(opening.getByRole('img', { name: alt, exact: true })).toHaveCount(0)
    const hiddenPhoto = opening.getByRole('img', { name: alt, exact: true, includeHidden: true })
    await expect(hiddenPhoto).toHaveAttribute('aria-hidden', 'true')
    await expect(hiddenPhoto).toHaveCSS('opacity', '0')
  }
}

async function expectValuesAndLinks(page: Page) {
  const valueItems = page.locator('.values li')
  await expect(valueItems).toHaveText(values)
  for (const value of await valueItems.all()) {
    await expect(value).toBeVisible()
    await expect(value).toHaveCSS('color', 'rgb(255, 255, 255)')
    expect(await value.evaluate((element) => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(24)
    await expect(value).toHaveCSS('font-family', /Oswald/)
  }
  const storyLinks = page.locator('.story-links').getByRole('link')
  await expect(storyLinks).toHaveCount(3)
  for (const [index, story] of stories.entries()) {
    const link = page.locator('.story-links').getByRole('link', {
      name: `${story.title} ${story.description} ${story.action}`,
      exact: true,
    })
    await expect(link).toBeVisible()
    await expect(link).toHaveAttribute('href', story.href)
    await expect(storyLinks.nth(index)).toHaveAttribute('href', story.href)
    await expect(link.getByRole('heading', { name: story.title, exact: true })).toBeVisible()
  }
}

test.beforeEach(async ({ page }) => {
  await page.route('**/images/*.jpg', (route) => route.fulfill({ status: 404, body: '' }))
  await page.clock.install()
  await page.goto('/')
})

test('home has the opening words and buttons', async ({ page }) => {
  await expectOpening(page)
})

test('home sections follow the opening in reading order', async ({ page }) => {
  const sections = [
    page.locator('.opening'),
    page.locator('.stripe'),
    page.locator('.values'),
    page.locator('.story-links'),
    page.getByRole('contentinfo'),
  ]
  let previousY = -Infinity
  for (const section of sections) {
    await expect(section).toBeVisible()
    const box = await section.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.y).toBeGreaterThan(previousY)
    previousY = box!.y
  }
})

test('home values are lit and story links have their destinations', async ({ page }) => {
  await expectValuesAndLinks(page)
})

test('missing photos retain the accessible first photo and navy fallback', async ({ page }) => {
  await expectPhotos(page)
})

test('home reflows at 320px without sideways scrolling', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 })
  await expectOpening(page)
  await expectValuesAndLinks(page)
  const dimensions = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }))
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport)
})

test.describe('with scripts off', () => {
  test.use({ javaScriptEnabled: false })

  test('words, first photo, values and links remain visible', async ({ page }) => {
    await expectOpening(page)
    await expectPhotos(page)
    await expectValuesAndLinks(page)
  })
})

test.describe('values motion', () => {
  test.use({ reducedMotion: 'no-preference', viewport: { width: 1280, height: 480 } })

  test('lights values once in order when the band enters view', async ({ page }) => {
    const items = page.locator('.values li')
    for (const item of await items.all()) {
      await expect(item).toHaveCSS('color', 'rgb(111, 119, 153)')
    }
    await page.locator('.values').scrollIntoViewIfNeeded()
    // Let the observer receive the scroll before advancing its staged timers.
    await expect(page.locator('.values')).toHaveClass(/revealing/)
    await page.clock.runFor(260)
    await expect(items.first()).toHaveCSS('color', 'rgb(255, 255, 255)')
    await expect(items.last()).toHaveCSS('color', 'rgb(111, 119, 153)')
    await page.clock.runFor(1100)
    for (const item of await items.all()) {
      await expect(item).toHaveCSS('color', 'rgb(255, 255, 255)')
    }
    await page.locator('.opening').scrollIntoViewIfNeeded()
    await page.locator('.values').scrollIntoViewIfNeeded()
    for (const item of await items.all()) {
      await expect(item).toHaveCSS('color', 'rgb(255, 255, 255)')
    }
  })
})

test('reduced motion leaves every value lit immediately', async ({ page }) => {
  for (const item of await page.locator('.values li').all()) {
    await expect(item).toHaveCSS('color', 'rgb(255, 255, 255)')
  }
})
