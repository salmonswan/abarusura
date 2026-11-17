import { expect, test } from '@playwright/test'

test('the site loads', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveTitle(/Abarusura RFC/)
})

test('Directus is up', async ({ request }) => {
  const res = await request.get('http://localhost:8065/server/ping')
  expect(res.ok()).toBe(true)
})
