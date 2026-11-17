import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: 'e2e',
  workers: 2,
  outputDir: '../results/screenshots',
  use: { baseURL: 'http://localhost:4173', browserName: 'chromium', screenshot: 'on' },
  webServer: [
    { command: 'docker compose -f ../directus/docker-compose.yml up', url:
  'http://localhost:8065/server/ping', timeout: 120_000, reuseExistingServer: !process.env.CI },
    { command: 'npm run preview -- --port 4173 --strictPort', url:
  'http://localhost:4173' },
    ],
})
