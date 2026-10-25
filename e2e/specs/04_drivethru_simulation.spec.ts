import { test, expect } from '@playwright/test';

test.describe('Drive-Thru Physical Simulation & Interactive Flow', () => {

  test('simulate full multi-step car drive-thru experience with live visual capture', async ({ page }) => {
    // AudioWorklet shim for headless mode
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

    // 1. Route menu API with real demo items
    await page.route('/api/menu', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          items: [
            {
              menu_item_id: "BURGER_001",
              name: "Classic Cheeseburger",
              category: "burgers",
              description: "Signature cheeseburger, packed with power levels.",
              price: 8.99,
              calories: 650,
              allergens: "gluten,dairy"
            },
            {
              menu_item_id: "SIDE_001",
              name: "French Fries",
              category: "sides",
              description: "Golden crispy fries (Medium).",
              price: 3.49,
              calories: 380,
              allergens: null
            },
            {
              menu_item_id: "DRINK_002",
              name: "Milkshake",
              category: "drinks",
              description: "Creamy milkshake (vanilla, chocolate, or strawberry).",
              price: 4.99,
              calories: 520,
              allergens: "dairy"
            },
            {
              menu_item_id: "DESSERT_001",
              name: "Apple Pie",
              category: "desserts",
              description: "Warm apple pie.",
              price: 3.99,
              calories: 320,
              allergens: "gluten"
            }
          ]
        }),
      });
    });

    let wsConnection: any = null;
    let step = 0;

    await page.routeWebSocket('/ws/voice', (ws) => {
      wsConnection = ws;
      ws.send(JSON.stringify({
        type: "session.created",
        session: { id: "sess_interactive_sim_42" }
      }));

      ws.onMessage((rawMsg) => {
        const msg = JSON.parse(rawMsg.toString());
        if (msg.type === 'input_audio_buffer.append') {
          step++;
          if (step === 1) {
            // Step 1: Customer orders Burger -> Screen switches to SIDES
            ws.send(JSON.stringify({
              type: "conversation.item.input_audio_transcription.completed",
              transcript: "Hi, I'd like to start with a Classic Cheeseburger please!"
            }));
            ws.send(JSON.stringify({
              type: "order_state_updated",
              stage: "sides",
              items: [
                {
                  menu_item_id: "BURGER_001",
                  name: "Classic Cheeseburger",
                  quantity: 1,
                  price: 8.99,
                  line_total: 8.99
                }
              ],
              subtotal: 8.99,
              tax: 0.72,
              grand_total: 9.71,
              item_count: 1,
              highlighted_item_ids: ["SIDE_001"]
            }));
          }
        }
      });
    });

    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto('/');

    // Check Header & Non-scrollable Menu Board loaded
    await expect(page.getByText('Drive-Thru Z')).toBeVisible();
    await expect(page.getByTestId('live-basket-panel')).toBeVisible();
    await expect(page.getByTestId('basket-empty-state')).toBeVisible();

    // Verify stage 1 (Burgers) is active by default
    await expect(page.getByTestId('stage-pill-burgers')).toHaveClass(/active/);
    await expect(page.getByText('Classic Cheeseburger')).toBeVisible();

    // Click Dragon Ball Mic to start voice session
    await page.locator('button.dragonball-btn').click();

    // Verify screen automatically moved to SIDES without driver touching screen
    await expect(page.getByTestId('stage-pill-sides')).toHaveClass(/active/);
    await expect(page.getByText('French Fries')).toBeVisible();

    // Verify live basket now has 1 item and $9.71 total
    await expect(page.getByTestId('basket-item-BURGER_001')).toBeVisible();
    await expect(page.getByTestId('basket-grand-total')).toHaveText('$9.71');

    // --- STEP 2: Customer adds Fries & Milkshake -> Agent updates state to DESSERTS ---
    wsConnection.send(JSON.stringify({
      type: "order_state_updated",
      stage: "desserts",
      items: [
        {
          menu_item_id: "BURGER_001",
          name: "Classic Cheeseburger",
          quantity: 1,
          price: 8.99,
          line_total: 8.99
        },
        {
          menu_item_id: "SIDE_001",
          name: "French Fries",
          quantity: 1,
          price: 3.49,
          line_total: 3.49
        },
        {
          menu_item_id: "DRINK_002",
          name: "Milkshake",
          quantity: 1,
          price: 4.99,
          line_total: 4.99,
          customizations: "chocolate"
        }
      ],
      subtotal: 17.47,
      tax: 1.40,
      grand_total: 18.87,
      item_count: 3,
      highlighted_item_ids: ["DESSERT_001"]
    }));

    // Verify screen automatically advanced to DESSERTS
    await expect(page.getByTestId('stage-pill-desserts')).toHaveClass(/active/);
    await expect(page.getByTestId('menu-card-DESSERT_001')).toBeVisible();
    await expect(page.getByTestId('basket-grand-total')).toHaveText('$18.87');

    // --- STEP 3: Customer is ready -> Agent transitions to REVIEW ---
    wsConnection.send(JSON.stringify({
      type: "order_state_updated",
      stage: "review",
      items: [
        {
          menu_item_id: "BURGER_001",
          name: "Classic Cheeseburger",
          quantity: 1,
          price: 8.99,
          line_total: 8.99
        },
        {
          menu_item_id: "SIDE_001",
          name: "French Fries",
          quantity: 1,
          price: 3.49,
          line_total: 3.49
        },
        {
          menu_item_id: "DRINK_002",
          name: "Milkshake",
          quantity: 1,
          price: 4.99,
          line_total: 4.99,
          customizations: "chocolate"
        }
      ],
      subtotal: 17.47,
      tax: 1.40,
      grand_total: 18.87,
      item_count: 3,
      highlighted_item_ids: []
    }));

    // Verify Left panel is now displaying the full Order Review Board
    await expect(page.getByTestId('review-stage-board')).toBeVisible();
    await expect(page.getByText('ORDER REVIEW — PLEASE CONFIRM WITH AGENT')).toBeVisible();

    // --- STEP 4: Customer confirms -> Agent submits and receives ORDER_CONFIRMED ---
    wsConnection.send(JSON.stringify({
      type: "order_confirmed",
      order_id: "ORD-SAIYAN-9999",
      subtotal: 17.47,
      tax: 1.40,
      grand_total: 18.87,
      item_count: 3,
      items: [
        {
          menu_item_id: "BURGER_001",
          name: "Classic Cheeseburger",
          quantity: 1,
          price: 8.99,
          line_total: 8.99
        },
        {
          menu_item_id: "SIDE_001",
          name: "French Fries",
          quantity: 1,
          price: 3.49,
          line_total: 3.49
        },
        {
          menu_item_id: "DRINK_002",
          name: "Milkshake",
          quantity: 1,
          price: 4.99,
          line_total: 4.99,
          customizations: "chocolate"
        }
      ]
    }));

    // Verify finalized invoice state
    await expect(page.getByTestId('basket-status-badge')).toHaveText('READY FOR DISPATCH');
    await expect(page.getByTestId('confirmed-order-id')).toContainText('ORD-SAIY');
    await expect(page.getByText('ORDER DISPATCHED TO CAPSULE KITCHEN!')).toBeVisible();

    // Save visual snapshot
    await page.screenshot({ path: 'drivethru_live_simulation.png', fullPage: true });
  });

});
