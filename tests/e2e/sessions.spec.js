import { test, expect } from '@playwright/test';

test('sidebar loads sessions', async ({ page }) => {
  await page.goto('/');
  const sidebar = page.locator('#sidebar, .sidebar, .session-list');
  await expect(sidebar).toBeVisible();
});

test('rename session via sidebar', async ({ page }) => {
  await page.goto('/');
  const renameBtn = page.locator('.act-rename').first();
  if (await renameBtn.isVisible()) {
    await renameBtn.click();
    const input = page.locator('.session-preview input, .si').first();
    await expect(input).toBeVisible();
  }
});

test('delete session shows confirmation', async ({ page }) => {
  await page.goto('/');
  const deleteBtn = page.locator('.act-delete').first();
  if (await deleteBtn.isVisible()) {
    await deleteBtn.click();
    await expect(page.locator('text=Eliminar')).toBeVisible();
  }
});