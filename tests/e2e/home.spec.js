import { test, expect } from '@playwright/test';

test('home page loads', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/Kairos|K-Chat/);
});

test('sidebar shows sessions', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.session-item').first()).toBeVisible();
});

test('new session has UUID in URL', async ({ page }) => {
  await page.goto('/');
  const url = page.url();
  expect(url).toMatch(/\/sessions\/[0-9a-f-]{36}/);
});

test('model selector is visible', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#model-select, select')).toBeVisible();
});

test('empty state message shown', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.empty-state, .msg-empty')).toBeVisible();
});

test('new chat button exists', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('a[href="/"], .btn-new')).toBeVisible();
});

test('debug toggle visible', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.debug-toggle, #debug-toggle')).toBeVisible();
});

test('favicon returns 200', async ({ request }) => {
  const response = await request.get('/favicon.ico');
  expect(response.status()).toBe(200);
});
