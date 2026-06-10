import { test, expect } from '@playwright/test';

test('widget system loads without errors', async ({ page }) => {
  const errors = [];
  page.on('pageerror', err => errors.push(err.message));
  await page.goto('/');
  await page.waitForTimeout(2000);
  expect(errors).toHaveLength(0);
});
