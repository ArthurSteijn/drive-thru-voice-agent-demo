export const MOCK_MENU_RESPONSE = {
  success: true,
  items: [
    {
      menu_item_id: "BURGER_001",
      name: "Classic Cheeseburger",
      category: "burgers",
      description: "Our signature cheeseburger with fries.",
      price: 8.99,
      calories: 650,
      allergens: "gluten,dairy",
    },
    {
      menu_item_id: "SIDE_001",
      name: "French Fries",
      category: "sides",
      description: "Golden crispy fries (Medium).",
      price: 3.49,
      calories: 380,
      allergens: null,
    },
    {
      menu_item_id: "DRINK_001",
      name: "Super Senzu Shake",
      category: "drinks",
      description: "Refreshing Senzu bean shake.",
      price: 4.99,
      calories: 320,
      allergens: "dairy",
    },
  ],
};

export const MOCK_SESSION_CREATED = {
  type: "session.created",
  session: { id: "sess_mock_playwright_123" },
};

export const MOCK_TRANSCRIPT_COMPLETED = {
  type: "conversation.item.input_audio_transcription.completed",
  transcript: "I would like a Classic Cheeseburger with no pickles please.",
};

export const MOCK_ORDER_STATE_UPDATED = {
  type: "order_state_updated",
  stage: "drinks",
  items: [
    {
      menu_item_id: "BURGER_001",
      name: "Classic Cheeseburger",
      quantity: 1,
      price: 8.99,
      line_total: 8.99,
      customizations: "no pickles",
    },
  ],
  subtotal: 8.99,
  tax: 0.72,
  grand_total: 9.71,
  item_count: 1,
  highlighted_item_ids: ["DRINK_001"],
};

export const MOCK_AUDIO_TRANSCRIPT_DELTA = {
  type: "response.audio_transcript.delta",
  delta: "Got it, one Classic Cheeseburger with no pickles! What can I get you to drink?",
  item_id: "item_resp_001",
};

export const MOCK_TOOL_INVOKED = {
  type: "tool.invoked",
  name: "submit_order",
  call_id: "call_mock_999",
};

export const MOCK_ORDER_CONFIRMED = {
  type: "order_confirmed",
  order_id: "ORD-PLAYWRIGHT-12345",
  subtotal: 13.98,
  tax: 1.12,
  grand_total: 15.10,
  item_count: 2,
  items: [
    {
      menu_item_id: "BURGER_001",
      name: "Classic Cheeseburger",
      quantity: 1,
      price: 8.99,
      line_total: 8.99,
      customizations: "no pickles",
    },
    {
      menu_item_id: "DRINK_001",
      name: "Super Senzu Shake",
      quantity: 1,
      price: 4.99,
      line_total: 4.99,
    },
  ],
};
