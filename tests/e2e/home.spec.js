import { test, expect } from '@playwright/test';

test('home page loads', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/Kairos|K-Chat/);
});

test('sidebar shows sessions', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.session-item')).toBeVisible();
});
