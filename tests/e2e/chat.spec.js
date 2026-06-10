import { test, expect } from '@playwright/test';

test('chat page loads with input', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#chat-input, textarea, input[type="text"]')).toBeVisible();
});

test('can type in chat input', async ({ page }) => {
  await page.goto('/');
  const input = page.locator('#chat-input, textarea, input[type="text"]');
  await input.fill('Hello');
  await expect(input).toHaveValue('Hello');
});
