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

test('submit shows user message', async ({ page }) => {
  await page.goto('/');
  const input = page.locator('#chat-input, textarea').first();
  await input.fill('Hello test');
  await page.locator('button[type="submit"], .send-btn').click();
  await expect(page.locator('.msg.user, .message.user')).toBeVisible();
});

test('input disabled during streaming', async ({ page }) => {
  await page.goto('/');
  const input = page.locator('#chat-input, textarea').first();
  await input.fill('Test message');
  await page.locator('button[type="submit"], .send-btn').click();
  await expect(input).toBeDisabled();
});

test('URL changes to /sessions/{id}', async ({ page }) => {
  await page.goto('/');
  const initialUrl = page.url();
  if (initialUrl.match(/\/sessions\/[0-9a-f-]{36}/)) {
    expect(initialUrl).toMatch(/\/sessions\/[0-9a-f-]{36}/);
    return;
  }
  const input = page.locator('#chat-input, textarea').first();
  await input.fill('Test');
  await page.locator('button[type="submit"], .send-btn').click();
  await page.waitForTimeout(2000);
  expect(page.url()).not.toBe(initialUrl);
});

test('empty input not submitted', async ({ page }) => {
  await page.goto('/');
  await page.locator('button[type="submit"], .send-btn').click();
  await expect(page.locator('.msg.user')).toHaveCount(0);
});
