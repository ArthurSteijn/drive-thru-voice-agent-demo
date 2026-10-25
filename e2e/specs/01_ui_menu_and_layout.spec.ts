import { test, expect } from '@playwright/test';
import {
  MOCK_MENU_RESPONSE,
  MOCK_SESSION_CREATED,
  MOCK_TRANSCRIPT_COMPLETED,
  MOCK_ORDER_STATE_UPDATED,
  MOCK_AUDIO_TRANSCRIPT_DELTA,
  MOCK_ORDER_CONFIRMED,
} from '../fixtures/mock_events';

test.use({
  permissions: ['microphone'],
});

test.describe('DriveThru UI, Stage Menu & Live Basket (Mocked)', () => {

  test.beforeEach(async ({ page }) => {
    await page.route('/api/menu', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_MENU_RESPONSE),
      });
    });
  });

  test('should display stage-guided menu board without scrolling and switch categories', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByText('Drive-Thru Z')).toBeVisible();

    // Stage 1 (Burgers) is active by default
    await expect(page.getByTestId('stage-pill-burgers')).toHaveClass(/active/);
    await expect(page.getByText('Classic Cheeseburger')).toBeVisible();

    // Live basket starts empty and visible
    await expect(page.getByTestId('live-basket-panel')).toBeVisible();
    await expect(page.getByTestId('basket-empty-state')).toBeVisible();

    // Switch stage to Drinks and verify Drinks menu is shown
    await page.getByTestId('stage-pill-drinks').click();
    await expect(page.getByText('Super Senzu Shake')).toBeVisible();
  });

  test('should update live basket and menu stage from WebSocket events', async ({ page }) => {
    await page.addInitScript(() => {
      const origAddModule = AudioWorklet.prototype.addModule;
      AudioWorklet.prototype.addModule = async function () {
        const jsCode = `
          class CaptureProcessor extends AudioWorkletProcessor {
            process(inputs) {
              const input = inputs[0];
              if (input && input[0] && input[0].length > 0) {
                this.port.postMessage(input[0]);
              }
              return true;
            }
          }
          registerProcessor("capture-processor", CaptureProcessor);
        `;
        const blob = new Blob([jsCode], { type: 'application/javascript' });
        const url = URL.createObjectURL(blob);
        return origAddModule.call(this, url);
      };
    });

    let serverWs: any = null;

    await page.routeWebSocket('/ws/voice', (ws) => {
      serverWs = ws;
      ws.send(JSON.stringify(MOCK_SESSION_CREATED));

      let handled = false;
      ws.onMessage((msg) => {
        const parsed = JSON.parse(msg.toString());
        if (parsed.type === 'input_audio_buffer.append' && !handled) {
          handled = true;
          ws.send(JSON.stringify(MOCK_TRANSCRIPT_COMPLETED));
          ws.send(JSON.stringify(MOCK_ORDER_STATE_UPDATED));
          ws.send(JSON.stringify(MOCK_AUDIO_TRANSCRIPT_DELTA));
        }
      });
    });

    await page.goto('/');
    await expect(page.getByText('Drive-Thru Z')).toBeVisible();

    const micBtn = page.locator('button.dragonball-btn');
    await expect(micBtn).toBeVisible();
    await micBtn.click();

    // Assert stage updated to drinks and basket updated
    await expect(page.getByTestId('stage-pill-drinks')).toHaveClass(/active/);
    await expect(page.getByTestId('basket-item-BURGER_001')).toBeVisible();
    await expect(page.getByTestId('basket-item-BURGER_001')).toContainText('no pickles');
    await expect(page.getByTestId('basket-grand-total')).toHaveText('$9.71');

    // Super Senzu Shake card should be visible with highlighted state
    const shakeCard = page.getByTestId('menu-card-DRINK_001');
    await expect(shakeCard).toBeVisible();
    await expect(shakeCard).toHaveClass(/highlighted-card/);
    await expect(shakeCard).toContainText('Super Senzu Shake');

    // Send order confirmation
    if (serverWs) {
      serverWs.send(JSON.stringify(MOCK_ORDER_CONFIRMED));
    }

    // Assert confirmed state
    await expect(page.getByTestId('basket-status-badge')).toHaveText('READY FOR DISPATCH');
    await expect(page.getByTestId('basket-grand-total')).toHaveText('$15.10');
  });

});
