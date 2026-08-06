/**
 * Browser smoke: login → authenticated shell.
 * Uses Playwright Chromium API (not the test runner) so it works on OneDrive/Windows
 * where `@playwright/test` may hang. CI still runs `playwright test` on Ubuntu.
 */
import { chromium } from 'playwright'

const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5173'
const username = process.env.E2E_USERNAME || 'admin'
const password = process.env.E2E_PASSWORD || 'Admin123!'

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage()

try {
  await page.goto(`${baseURL}/login`, { waitUntil: 'domcontentloaded', timeout: 30_000 })
  await page.locator('#login-username').fill(username)
  await page.locator('#login-password').fill(password)
  await page.getByRole('button', { name: 'Sign In' }).click()
  await page.waitForURL(/\/(dashboard|catalog|agents|reports)/, { timeout: 45_000 })
  const shell = page.locator('nav, aside').first()
  await shell.waitFor({ state: 'visible', timeout: 15_000 })
  console.log(`e2e-login-smoke OK → ${page.url()}`)
} catch (err) {
  console.error('e2e-login-smoke FAILED:', err?.message || err)
  process.exitCode = 1
} finally {
  await browser.close()
}
