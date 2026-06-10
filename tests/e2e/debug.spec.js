import { test, expect } from '@playwright/test';

test('debug panel toggles', async ({ page }) => {
  await page.goto('/');
  const toggle = page.locator('.debug-toggle, #debug-toggle').first();
  if (await toggle.isVisible()) {
    await toggle.click();
    const panel = page.locator('.debug-panel, #debug-panel');
    await expect(panel).toBeVisible();
  }
});