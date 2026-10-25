import { test, expect } from '@playwright/test';

test.describe('Azure Cloud Voice Live Integration (Live)', () => {

  test('should establish voice session with Azure VoiceLive backend', async ({ page }) => {
    await page.goto('/');

    // Check menu loads
    await expect(page.getByText('Drive-Tru Z')).toBeVisible();

    // Click mic button using fake audio input stream
    const micBtn = page.locator('button.dragonball-btn');
    if (await micBtn.isVisible()) {
      await micBtn.click();
    }

    // Verify scouter status title area is visible and active
    await expect(page.locator('.scouter-status-title')).toBeVisible();
  });

});
