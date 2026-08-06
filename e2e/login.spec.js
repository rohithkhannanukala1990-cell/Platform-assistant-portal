import { expect, test } from '@playwright/test'

test('login reaches dashboard', async ({ page }) => {
  await page.goto('/login')

  await page.locator('#login-username').fill('admin')
  await page.locator('#login-password').fill('Admin123!')
  await page.getByRole('button', { name: 'Sign In' }).click()

  await page.waitForURL(/\/(dashboard|catalog|agents|reports)/, { timeout: 45_000 })
  await expect(page.locator('nav, aside').first()).toBeVisible()
})
