import { useCallback, useEffect, useRef, useState } from "react";
import gokuEatingBurgers from "./assets/goku_eating_burgers.png";

// ── Types ──────────────────────────────────────────────────────────

type SessionStatus = "idle" | "connecting" | "listening" | "speaking";

type OrderingStage =
  | "burgers"
  | "chicken"
  | "sides"
  | "drinks"
  | "desserts"
  | "review";

interface BasketItem {
  menu_item_id: string;
  name: string;
  quantity: number;
  price: number;
  line_total?: number;
  customizations?: string;
}

interface OrderState {
  status: "empty" | "building" | "reviewing" | "confirmed";
  order_id?: string;
  items: BasketItem[];
  subtotal: number;
  tax: number;
  grand_total: number;
  item_count: number;
}

interface MenuItem {
  menu_item_id: string;
  name: string;
  category: string;
  description: string;
  price: number;
  calories?: number;
  allergens?: string | null;
}

interface ChatMessage {
  id: string;
  sender: "agent" | "user";
  text: string;
}

interface StageConfig {
  key: OrderingStage;
  stepNumber: number;
  label: string;
  jpSub: string;
  badge: string;
  guidePrompt: string;
}

// ── Helpers ────────────────────────────────────────────────────────

/** Resample Float32 audio from `fromRate` to `toRate` (linear interpolation). */
function resample(buffer: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate === toRate) return buffer;
  const ratio = fromRate / toRate;
  const newLength = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLength);
  for (let i = 0; i < newLength; i++) {
    const idx = i * ratio;
    const low = Math.floor(idx);
    const high = Math.min(low + 1, buffer.length - 1);
    const frac = idx - low;
    result[i] = buffer[low] * (1 - frac) + buffer[high] * frac;
  }
  return result;
}

/** Convert Float32 [-1, 1] → Int16 PCM → base64 string. */
function float32ToBase64Pcm16(float32: Float32Array): string {
  const int16 = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  const bytes = new Uint8Array(int16.buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/** Decode base64 PCM16 → Float32 for AudioContext playback. */
function base64Pcm16ToFloat32(b64: string): Float32Array {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const int16 = new Int16Array(bytes.buffer);
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / (int16[i] < 0 ? 0x8000 : 0x7fff);
  }
  return float32;
}

// ── Constants ──────────────────────────────────────────────────────

const TARGET_SAMPLE_RATE = 24000;
const TAX_RATE = 0.08;
const WS_URL =
  (window.location.protocol === "https:" ? "wss://" : "ws://") +
  window.location.host +
  "/ws/voice";

const CAPTURE_PROCESSOR_CODE = `
class CaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (input && input[0] && input[0].length > 0) {
      this.port.postMessage(new Float32Array(input[0]));
    }
    return true;
  }
}
registerProcessor("capture-processor", CaptureProcessor);
`;

const STAGE_CONFIGS: StageConfig[] = [
  {
    key: "burgers",
    stepNumber: 1,
    label: "BURGERS",
    jpSub: "戦闘力",
    badge: "🔥 STEP 1: MAINS",
    guidePrompt: "START WITH A SIGNATURE BURGER — OR ASK FOR ANY CATEGORY!",
  },
  {
    key: "chicken",
    stepNumber: 2,
    label: "CHICKEN",
    jpSub: "超戦士",
    badge: "⚡ STEP 2: POULTRY",
    guidePrompt: "CRISPY SANDWICHES, WRAPS & HAND-BREADED TENDERS",
  },
  {
    key: "sides",
    stepNumber: 3,
    label: "SIDES",
    jpSub: "仙豆",
    badge: "🍟 STEP 3: SIDES",
    guidePrompt: "POWER UP YOUR MEAL WITH FRIES, RINGS, SALAD OR STICKS",
  },
  {
    key: "drinks",
    stepNumber: 4,
    label: "DRINKS",
    jpSub: "元気玉",
    badge: "❄️ STEP 4: DRINKS",
    guidePrompt: "RECHARGE WITH SHAKES, LEMONADE, ICED COFFEE OR SODA",
  },
  {
    key: "desserts",
    stepNumber: 5,
    label: "DESSERTS",
    jpSub: "魔人",
    badge: "🍦 STEP 5: SWEETS",
    guidePrompt: "FINISH STRONG WITH WARM PIE, BROWNIE, SUNDAE OR COOKIES",
  },
  {
    key: "review",
    stepNumber: 6,
    label: "REVIEW",
    jpSub: "確認",
    badge: "✅ STEP 6: CONFIRM",
    guidePrompt: "VERIFY YOUR ORDER ON SCREEN & CONFIRM WITH THE AGENT",
  },
];

const INITIAL_ORDER_STATE: OrderState = {
  status: "empty",
  items: [],
  subtotal: 0,
  tax: 0,
  grand_total: 0,
  item_count: 0,
};

const INITIAL_MENU_ITEMS: MenuItem[] = [
  // Burgers
  { menu_item_id: "BURGER_001", name: "Classic Cheeseburger",     category: "burgers",  description: "Our signature cheeseburger, packed with power levels.", price:  8.99, calories: 650, allergens: "gluten,dairy" },
  { menu_item_id: "BURGER_002", name: "DriveThru Deluxe",          category: "burgers",  description: "Kaioken double patty with bacon, cheese, and all the fixings.",               price: 12.99, calories: 920, allergens: "gluten,dairy" },
  { menu_item_id: "BURGER_003", name: "Mushroom Swiss Burger",    category: "burgers",  description: "Premium beef patty topped with sautéed mushrooms and Swiss cheese.",          price: 10.99, calories: 780, allergens: "gluten,dairy" },
  { menu_item_id: "BURGER_004", name: "Veggie Burger",            category: "burgers",  description: "Senzu-infused plant-based patty with fresh avocado and sprouts.",                          price:  9.99, calories: 540, allergens: "gluten,soy" },
  { menu_item_id: "BURGER_005", name: "Spicy Jalapeño Burger",    category: "burgers",  description: "Explosive pepper-jack cheese, fresh jalapeños, chipotle mayo.",                        price: 10.49, calories: 810, allergens: "gluten,dairy" },

  // Chicken
  { menu_item_id: "CHICKEN_001", name: "Crispy Chicken Sandwich", category: "chicken",  description: "Golden breaded chicken breast with pickles and mayo.",                        price:  9.99, calories: 580, allergens: "gluten,egg" },
  { menu_item_id: "CHICKEN_002", name: "Grilled Chicken Wrap",    category: "chicken",  description: "Grilled chicken with lettuce, tomato, ranch in a flour tortilla.",     price:  8.49, calories: 460, allergens: "gluten,dairy" },
  { menu_item_id: "CHICKEN_003", name: "Chicken Tenders (5pc)",   category: "chicken",  description: "Five hand-breaded tenders with dipping sauce.",                        price:  7.99, calories: 540, allergens: "gluten,egg" },
  { menu_item_id: "CHICKEN_004", name: "Buffalo Chicken Sandwich",category: "chicken",  description: "Crispy chicken tossed in buffalo sauce with blue cheese.",             price: 10.49, calories: 670, allergens: "gluten,dairy,egg" },

  // Sides
  { menu_item_id: "SIDE_001", name: "French Fries",              category: "sides",    description: "Golden crispy fries (Medium).",                                        price:  3.49, calories: 380, allergens: null },
  { menu_item_id: "SIDE_002", name: "Onion Rings",                category: "sides",    description: "Beer-battered onion rings.",                                           price:  4.49, calories: 410, allergens: "gluten" },
  { menu_item_id: "SIDE_003", name: "Sweet Potato Fries",         category: "sides",    description: "Crispy sweet potato fries with cinnamon sugar.",                       price:  4.29, calories: 340, allergens: null },
  { menu_item_id: "SIDE_004", name: "Side Salad",                 category: "sides",    description: "Mixed greens, tomato, cucumber, vinaigrette.",                         price:  4.99, calories: 180, allergens: null },
  { menu_item_id: "SIDE_005", name: "Mozzarella Sticks (4pc)",    category: "sides",    description: "Breaded mozzarella with marinara sauce.",                              price:  5.49, calories: 470, allergens: "gluten,dairy" },

  // Drinks
  { menu_item_id: "DRINK_001", name: "Soft Drink",                category: "drinks",   description: "Cold soft drink (Medium).",                                            price:  2.49, calories: 210, allergens: null },
  { menu_item_id: "DRINK_002", name: "Milkshake",                 category: "drinks",   description: "Creamy milkshake (vanilla, chocolate, or strawberry).",                price:  4.99, calories: 520, allergens: "dairy" },
  { menu_item_id: "DRINK_003", name: "Iced Coffee",               category: "drinks",   description: "Cold-brew iced coffee.",                                               price:  3.49, calories:  90, allergens: "dairy" },
  { menu_item_id: "DRINK_004", name: "Fresh Lemonade",            category: "drinks",   description: "Hand-squeezed lemonade.",                                              price:  3.29, calories: 150, allergens: null },
  { menu_item_id: "DRINK_005", name: "Bottled Water",             category: "drinks",   description: "16 oz purified bottled water.",                                        price:  1.99, calories:   0, allergens: null },

  // Desserts
  { menu_item_id: "DESSERT_001", name: "Apple Pie",               category: "desserts", description: "Warm apple pie.",                                                      price:  3.99, calories: 320, allergens: "gluten" },
  { menu_item_id: "DESSERT_002", name: "Chocolate Brownie",       category: "desserts", description: "Fudgy chocolate brownie.",                                             price:  3.49, calories: 410, allergens: "gluten,dairy,egg" },
  { menu_item_id: "DESSERT_003", name: "Ice Cream Sundae",        category: "desserts", description: "Vanilla ice cream with chocolate sauce and a cherry.",                 price:  4.49, calories: 480, allergens: "dairy" },
  { menu_item_id: "DESSERT_004", name: "Cookie (3pc)",            category: "desserts", description: "Three warm chocolate chip cookies.",                                   price:  2.99, calories: 360, allergens: "gluten,dairy,egg" },
];

function isValidStage(stage: string): stage is OrderingStage {
  return STAGE_CONFIGS.some((cfg) => cfg.key === stage);
}

// ── Component ──────────────────────────────────────────────────────

export default function App() {
  const [status, setStatus] = useState<SessionStatus>("idle");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [currentAgentMessage, setCurrentAgentMessage] = useState("");
  const [menuItems, setMenuItems] = useState<MenuItem[]>(INITIAL_MENU_ITEMS);
  const [activeStage, setActiveStage] = useState<OrderingStage>("burgers");
  const [highlightedIds, setHighlightedIds] = useState<string[]>([]);
  const [orderState, setOrderState] = useState<OrderState>(INITIAL_ORDER_STATE);

  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const playbackTimeRef = useRef(0);
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const currentAgentTextRef = useRef("");
  const interruptedRef = useRef(false);

  const chatEndRef = useRef<HTMLDivElement | null>(null);

  // Dynamic menu query
  useEffect(() => {
    fetch("/api/menu")
      .then((res) => res.json())
      .then((data) => {
        if (data.success && data.items && data.items.length > 0) {
          setMenuItems(data.items);
        }
      })
      .catch((err) => console.error("Error fetching database menu:", err));
  }, []);

  // Auto-scroll chat history
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, currentAgentMessage]);

  // ── Playback ───────────────────────────────────────────────────

  const playPcm16Chunk = useCallback((b64: string) => {
    const ctx = audioCtxRef.current;
    if (!ctx) return;

    const float32 = base64Pcm16ToFloat32(b64);
    const resampled = resample(float32, TARGET_SAMPLE_RATE, ctx.sampleRate);
    const buffer = ctx.createBuffer(1, resampled.length, ctx.sampleRate);
    buffer.copyToChannel(new Float32Array(resampled.buffer.slice(0)) as unknown as Float32Array<ArrayBuffer>, 0);

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);

    activeSourcesRef.current.push(source);
    source.onended = () => {
      activeSourcesRef.current = activeSourcesRef.current.filter((s) => s !== source);
    };

    const now = ctx.currentTime;
    const startAt = Math.max(now, playbackTimeRef.current);
    source.start(startAt);
    playbackTimeRef.current = startAt + buffer.duration;
  }, []);

  // ── Start session ──────────────────────────────────────────────

  const start = useCallback(async () => {
    try {
      setStatus("connecting");
      setMessages([]);
      setCurrentAgentMessage("");
      currentAgentTextRef.current = "";
      setActiveStage("burgers");
      setHighlightedIds([]);
      setOrderState(INITIAL_ORDER_STATE);
      playbackTimeRef.current = 0;
      interruptedRef.current = false;

      // Audio context
      const audioCtx = new AudioContext({ sampleRate: 48000 });
      if (audioCtx.state === "suspended") {
        await audioCtx.resume();
      }
      audioCtxRef.current = audioCtx;

      // Microphone
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 48000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      streamRef.current = stream;

      // AudioWorklet for capture via inline blob URL (works in all environments without external file loading)
      const blob = new Blob([CAPTURE_PROCESSOR_CODE], { type: "application/javascript" });
      const workletUrl = URL.createObjectURL(blob);
      try {
        await audioCtx.audioWorklet.addModule(workletUrl);
      } finally {
        URL.revokeObjectURL(workletUrl);
      }
      const source = audioCtx.createMediaStreamSource(stream);
      const workletNode = new AudioWorkletNode(audioCtx, "capture-processor");
      workletNodeRef.current = workletNode;
      source.connect(workletNode);

      // WebSocket
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

    ws.onopen = () => {
      setStatus("listening");

      workletNode.port.onmessage = (e: MessageEvent<Float32Array>) => {
        if (ws.readyState !== WebSocket.OPEN) return;
        const resampled = resample(e.data, audioCtx.sampleRate, TARGET_SAMPLE_RATE);
        const b64 = float32ToBase64Pcm16(resampled);
        ws.send(
          JSON.stringify({
            type: "input_audio_buffer.append",
            audio: b64,
          })
        );
      };
    };

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        const type: string = msg.type ?? "";

        if (type === "response.created") {
          interruptedRef.current = false;
        } else if (type === "response.audio.delta") {
          if (interruptedRef.current) return;
          setStatus("speaking");
          playPcm16Chunk(msg.delta);
        } else if (type === "response.audio.done") {
          setStatus("listening");
        } else if (type === "input_audio_buffer.speech_started") {
          setStatus("listening");
          interruptedRef.current = true;
          playbackTimeRef.current = 0;
          activeSourcesRef.current.forEach((s) => {
            try {
              s.stop(0);
              s.disconnect();
            } catch {
              // Ignore if already stopped
            }
          });
          activeSourcesRef.current = [];

          currentAgentTextRef.current = "";
          setCurrentAgentMessage("");
        } else if (type === "response.audio_transcript.delta") {
          if (interruptedRef.current) return;
          currentAgentTextRef.current += msg.delta ?? "";
          setCurrentAgentMessage(currentAgentTextRef.current);
        } else if (
          type === "response.audio_transcript.done" ||
          type === "response.audio.done" ||
          type === "response.done"
        ) {
          if (interruptedRef.current) return;
          if (currentAgentTextRef.current.trim()) {
            const agentText = currentAgentTextRef.current.trim();
            currentAgentTextRef.current = "";
            setCurrentAgentMessage("");
            setMessages((prev) => [
              ...prev,
              { id: Math.random().toString(), sender: "agent", text: agentText },
            ]);
          }
        } else if (type === "conversation.item.input_audio_transcription.completed") {
          if (msg.transcript && msg.transcript.trim()) {
            const userText = msg.transcript.trim();
            const pendingAgentText = interruptedRef.current
              ? ""
              : currentAgentTextRef.current.trim();
            currentAgentTextRef.current = "";
            setCurrentAgentMessage("");

            setMessages((prev) => {
              const nextMessages = [...prev];
              if (pendingAgentText) {
                nextMessages.push({
                  id: Math.random().toString(),
                  sender: "agent",
                  text: pendingAgentText,
                });
              }
              nextMessages.push({
                id: Math.random().toString(),
                sender: "user",
                text: userText,
              });
              return nextMessages;
            });
          }
        } else if (type === "order_state_updated") {
          const nextStageRaw = (msg.stage ?? "").toLowerCase();
          if (isValidStage(nextStageRaw)) {
            setActiveStage(nextStageRaw);
          }
          const incomingItems: BasketItem[] = Array.isArray(msg.items) ? msg.items : [];
          const subtotal =
            typeof msg.subtotal === "number"
              ? msg.subtotal
              : incomingItems.reduce((acc, it) => acc + it.price * it.quantity, 0);
          const tax =
            typeof msg.tax === "number" ? msg.tax : Math.round(subtotal * TAX_RATE * 100) / 100;
          const grandTotal =
            typeof msg.grand_total === "number"
              ? msg.grand_total
              : Math.round((subtotal + tax) * 100) / 100;
          const itemCount =
            typeof msg.item_count === "number"
              ? msg.item_count
              : incomingItems.reduce((acc, it) => acc + it.quantity, 0);

          setHighlightedIds(
            Array.isArray(msg.highlighted_item_ids) ? msg.highlighted_item_ids : []
          );
          setOrderState({
            status:
              nextStageRaw === "review"
                ? "reviewing"
                : incomingItems.length > 0
                ? "building"
                : "empty",
            items: incomingItems,
            subtotal,
            tax,
            grand_total: grandTotal,
            item_count: itemCount,
          });
        } else if (type === "menu_stage_updated") {
          const nextStageRaw = (msg.stage ?? "").toLowerCase();
          if (isValidStage(nextStageRaw)) {
            setActiveStage(nextStageRaw);
          }
        } else if (type === "order_confirmed") {
          setActiveStage("review");
          setOrderState((prev) => {
            const confirmedItems: BasketItem[] =
              Array.isArray(msg.items) && msg.items.length > 0 ? msg.items : prev.items;
            const grandTotal =
              typeof msg.grand_total === "number" ? msg.grand_total : prev.grand_total;
            const subtotal =
              typeof msg.subtotal === "number"
                ? msg.subtotal
                : prev.subtotal > 0
                ? prev.subtotal
                : Math.round((grandTotal / (1 + TAX_RATE)) * 100) / 100;
            const tax =
              typeof msg.tax === "number"
                ? msg.tax
                : Math.round((grandTotal - subtotal) * 100) / 100;
            const itemCount =
              typeof msg.item_count === "number" ? msg.item_count : prev.item_count;

            return {
              status: "confirmed",
              order_id: msg.order_id,
              items: confirmedItems,
              subtotal,
              tax,
              grand_total: grandTotal,
              item_count: itemCount,
            };
          });
        } else if (type === "error") {
          console.error("VoiceLive error:", msg);
        }
      } catch {
        // non-JSON message, ignore
      }
    };

    ws.onclose = () => {
      setStatus("idle");
    };

    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
      setStatus("idle");
    };
    } catch (err: any) {
      console.error("Failed to start voice connection:", err);
      setStatus("idle");
      setMessages((prev) => [
        ...prev,
        {
          id: String(Date.now()),
          sender: "agent",
          text: `⚠️ Could not initialize voice connection: ${err?.message || err}. Please ensure microphone permission is granted in your browser.`,
        },
      ]);
    }
  }, [playPcm16Chunk]);

  // ── Stop session ───────────────────────────────────────────────

  const stop = useCallback(() => {
    workletNodeRef.current?.disconnect();
    workletNodeRef.current = null;

    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;

    activeSourcesRef.current.forEach((source) => {
      try {
        source.stop();
      } catch {
        // ignore
      }
    });
    activeSourcesRef.current = [];

    audioCtxRef.current?.close();
    audioCtxRef.current = null;

    wsRef.current?.close();
    wsRef.current = null;

    setStatus("idle");
  }, []);

  // Clean up on unmount
  useEffect(() => stop, [stop]);

  // ── Derived UI Data ────────────────────────────────────────────

  const isActive = status !== "idle";
  const currentStageConfig =
    STAGE_CONFIGS.find((cfg) => cfg.key === activeStage) ?? STAGE_CONFIGS[0];

  const basketQtyByMenuId = orderState.items.reduce<Record<string, number>>((acc, item) => {
    acc[item.menu_item_id] = (acc[item.menu_item_id] ?? 0) + item.quantity;
    return acc;
  }, {});

  const visibleMenuItems =
    activeStage === "review"
      ? []
      : menuItems.filter((item) => item.category.toLowerCase() === activeStage);

  // ── Render ─────────────────────────────────────────────────────

  return (
    <div className="app">
      <header className="header-panel">
        <div className="header-title-area">
          <h1>Drive-Thru Z</h1>
          <p>Saga of the Hungry Saiyan</p>
        </div>

        <div className="header-goku-badge">
          <img
            src={gokuEatingBurgers}
            alt="Goku eating burgers"
            className="header-goku-image"
          />
        </div>

        <div className="header-decor">POWER LEVEL: 9000+</div>
      </header>

      <div className="manga-grid">
        {/* Left Column: Non-Scrollable Stage-Guided Menu Board */}
        <div className="manga-panel menu-panel" data-testid="menu-board-panel">
          <div className="panel-banner">
            <h2>
              DRIVE-THRU DISPLAY BOARD <span>{currentStageConfig.badge}</span>
            </h2>
          </div>

          {/* Ordering Process Stepper */}
          <nav className="stage-stepper" aria-label="Ordering Process Stages">
            {STAGE_CONFIGS.map((stage) => {
              const isCurrent = stage.key === activeStage;
              const categoryCount = orderState.items
                .filter((b) => {
                  const found = menuItems.find((m) => m.menu_item_id === b.menu_item_id);
                  return found?.category.toLowerCase() === stage.key;
                })
                .reduce((sum, b) => sum + b.quantity, 0);

              return (
                <button
                  key={stage.key}
                  type="button"
                  onClick={() => setActiveStage(stage.key)}
                  className={`stage-pill ${isCurrent ? "active" : ""} ${
                    categoryCount > 0 ? "has-items" : ""
                  }`}
                  data-testid={`stage-pill-${stage.key}`}
                >
                  <span className="stage-step-num">{stage.stepNumber}</span>
                  <span className="stage-step-label">{stage.label}</span>
                  {categoryCount > 0 && (
                    <span className="stage-item-count">{categoryCount}</span>
                  )}
                </button>
              );
            })}
          </nav>

          {/* Guided Process Banner */}
          <div className="stage-guide-banner" data-testid="stage-guide-banner">
            <div className="stage-guide-title">
              <span>
                {currentStageConfig.label} [{currentStageConfig.jpSub}]
              </span>
              <span className="stage-flex-hint">VOICE GUIDED • ASK FOR ANY CATEGORY ANYTIME</span>
            </div>
            <p className="stage-guide-subtitle">{currentStageConfig.guidePrompt}</p>
          </div>

          {/* Active Stage Content: 2-Column Card Grid OR Full Order Review */}
          {activeStage !== "review" ? (
            <div className="stage-cards-grid" data-testid="stage-cards-grid">
              {visibleMenuItems.map((item) => {
                const qtyInBasket = basketQtyByMenuId[item.menu_item_id] ?? 0;
                const isHighlighted = highlightedIds.includes(item.menu_item_id);

                return (
                  <div
                    className={`menu-card ${qtyInBasket > 0 ? "in-basket" : ""} ${
                      isHighlighted ? "highlighted-card" : ""
                    }`}
                    key={item.menu_item_id}
                    data-testid={`menu-card-${item.menu_item_id}`}
                  >
                    <div className="menu-card-top">
                      <span className="menu-item-name">{item.name}</span>
                      <span className="menu-item-price">${item.price.toFixed(2)}</span>
                    </div>

                    <p className="menu-item-desc">{item.description}</p>

                    <div className="menu-card-footer">
                      <div className="menu-item-meta">
                        {item.calories ? <span>{item.calories} CAL</span> : null}
                        {item.allergens ? <span>ALLERGENS: {item.allergens}</span> : null}
                      </div>

                      <div className="menu-card-badges">
                        {isHighlighted && (
                          <span className="badge-recommended">★ POPULAR</span>
                        )}
                        {qtyInBasket > 0 && (
                          <span className="badge-in-basket">IN BASKET ×{qtyInBasket}</span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="review-stage-board" data-testid="review-stage-board">
              <div className="review-board-header">
                <h3>
                  {orderState.status === "confirmed"
                    ? "ORDER DISPATCHED TO CAPSULE KITCHEN!"
                    : "ORDER REVIEW — PLEASE CONFIRM WITH AGENT"}
                </h3>
                <p>
                  {orderState.status === "confirmed"
                    ? "Please pull forward to the collection window."
                    : "Check your items on screen. Say 'Confirm my order' or ask to change any item."}
                </p>
              </div>

              {orderState.items.length === 0 ? (
                <div className="review-empty-box">
                  NO ITEMS IN BASKET YET — ASK THE AGENT TO ADD BURGERS, CHICKEN, SIDES, OR DRINKS!
                </div>
              ) : (
                <div className="review-items-grid">
                  {orderState.items.map((item, idx) => (
                    <div className="review-item-card" key={`${item.menu_item_id}-${idx}`}>
                      <div className="review-item-main">
                        <span className="review-item-qty">{item.quantity}x</span>
                        <div>
                          <div className="review-item-name">{item.name}</div>
                          {item.customizations && (
                            <div className="review-item-custom">
                              NOTE: {item.customizations}
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="review-item-price">
                        ${((item.line_total ?? item.price * item.quantity)).toFixed(2)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Compact Next-Step Footer Bar */}
          <div className="menu-board-footer">
            <span>
              CATEGORIES: BURGERS • CHICKEN • SIDES • DRINKS • DESSERTS
            </span>
            <span>HANDS-FREE CAR DISPLAY</span>
          </div>
        </div>

        {/* Right Column: Live Basket + Voice Scouter Console */}
        <div className="manga-panel console-panel">
          <div className="panel-banner">
            <h2>
              ORDER BASKET & COMM LINK <span>STATUS HUD</span>
            </h2>
          </div>

          {/* Always-Visible Capsule Corp Live Basket / Order Summary */}
          <div
            className={`order-summary-panel status-${orderState.status}`}
            data-testid="live-basket-panel"
          >
            <div className="capsule-corp-header">
              <div className="capsule-logo-area">
                <div className="capsule-logo-mark" />
                <div className="capsule-corp-title">
                  CAPSULE CORP. BASKET
                  <span>
                    {orderState.status === "confirmed"
                      ? "ORDER CONFIRMED"
                      : orderState.status === "reviewing"
                      ? "AWAITING CONFIRMATION"
                      : "LIVE DRIVE-THRU ORDER"}
                  </span>
                </div>
              </div>
              <div className="invoice-badge" data-testid="basket-status-badge">
                {orderState.status === "confirmed" && "READY FOR DISPATCH"}
                {orderState.status === "reviewing" && "CONFIRM ORDER"}
                {orderState.status === "building" && `${orderState.item_count} IN BASKET`}
                {orderState.status === "empty" && "BASKET EMPTY"}
              </div>
            </div>

            {orderState.items.length === 0 ? (
              <div className="basket-empty-state" data-testid="basket-empty-state">
                YOUR CAPSULE BASKET IS EMPTY. SPEAK TO THE AGENT TO ADD ITEMS!
              </div>
            ) : (
              <div className="basket-items-list" data-testid="basket-items-list">
                {orderState.items.map((item, idx) => {
                  const lineTotal = item.line_total ?? item.price * item.quantity;
                  return (
                    <div
                      className="basket-line-item"
                      key={`${item.menu_item_id}-${idx}`}
                      data-testid={`basket-item-${item.menu_item_id}`}
                    >
                      <div className="basket-line-left">
                        <span className="basket-item-qty">{item.quantity}x</span>
                        <div className="basket-item-info">
                          <span className="basket-item-name">{item.name}</span>
                          {item.customizations && (
                            <span className="basket-item-custom">
                              ({item.customizations})
                            </span>
                          )}
                        </div>
                      </div>
                      <span className="basket-item-price">${lineTotal.toFixed(2)}</span>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="receipt-body">
              {orderState.order_id && (
                <div className="receipt-row">
                  <span className="receipt-label">CAPSULE ID:</span>
                  <span className="receipt-value" data-testid="confirmed-order-id">
                    {orderState.order_id.slice(0, 8).toUpperCase()}...
                  </span>
                </div>
              )}
              <div className="receipt-row">
                <span className="receipt-label">ITEMS CONTAINER:</span>
                <span className="receipt-value" data-testid="basket-item-count">
                  {orderState.item_count} UNITS
                </span>
              </div>
              <div className="receipt-row">
                <span className="receipt-label">SUBTOTAL:</span>
                <span className="receipt-value">${orderState.subtotal.toFixed(2)}</span>
              </div>
              <div className="receipt-row">
                <span className="receipt-label">TAX (8%):</span>
                <span className="receipt-value">${orderState.tax.toFixed(2)}</span>
              </div>
              <div className="receipt-row receipt-grand-total">
                <span className="receipt-label">POWER COST (TOTAL):</span>
                <span
                  className="receipt-value"
                  style={{ color: "var(--orange-gi)" }}
                  data-testid="basket-grand-total"
                >
                  ${orderState.grand_total.toFixed(2)}
                </span>
              </div>
            </div>

            {orderState.status === "confirmed" && (
              <div className="receipt-footer">
                <div className="barcode">|||| | |||| || | |||</div>
                <div className="receipt-thankyou">PREPARE FOR SHIFT TO NEXT SAGA!</div>
              </div>
            )}
          </div>

          {/* Scouter HUD + Dragon Ball Mic Row */}
          <div className="comm-link-row">
            <div
              className={`scouter-terminal ${isActive ? "active-hud" : ""} ${
                status === "listening" ? "listening-hud" : ""
              }`}
            >
              <div className="scouter-scanline" />
              <div className="scouter-grid" />
              <div className="scouter-header">
                <span>HUD SYSTEM v4.12</span>
                <span>STAGE: {currentStageConfig.label}</span>
              </div>

              <div className="scouter-body">
                <div className="scouter-status-title">
                  <span className="target-brackets">[</span>
                  {status === "idle" && "SCANNING FOR SIGNALS"}
                  {status === "connecting" && "ESTABLISHING COMM LINK"}
                  {status === "listening" && "WAVEFORM DETECTED"}
                  {status === "speaking" && "TRANSMITTING RESPONSE"}
                  <span className="target-brackets">]</span>
                </div>
                <div className="scouter-status-text">
                  {status === "idle" && "TAP THE 4-STAR DRAGON BALL TO COMMENCE ORDERING."}
                  {status === "connecting" && "CALIBRATING COMM LINK CHANNELS..."}
                  {status === "listening" && "VOICE CAPTURE ACTIVE. SPEAK YOUR ORDER!"}
                  {status === "speaking" && "DRIVE-THRU AGENT IS RESPONDING..."}
                </div>
              </div>

              <div className="scouter-footer">
                <span>DBZ COMM MODE</span>
                {isActive ? (
                  <div className="audio-visualizer">
                    <div
                      className={`visualizer-bar ${
                        status === "speaking"
                          ? "active-speaking"
                          : status === "listening"
                          ? "active-listening"
                          : ""
                      }`}
                      style={{ animationDelay: "0.1s" }}
                    />
                    <div
                      className={`visualizer-bar ${
                        status === "speaking"
                          ? "active-speaking"
                          : status === "listening"
                          ? "active-listening"
                          : ""
                      }`}
                      style={{ animationDelay: "0.3s" }}
                    />
                    <div
                      className={`visualizer-bar ${
                        status === "speaking"
                          ? "active-speaking"
                          : status === "listening"
                          ? "active-listening"
                          : ""
                      }`}
                      style={{ animationDelay: "0.5s" }}
                    />
                    <div
                      className={`visualizer-bar ${
                        status === "speaking"
                          ? "active-speaking"
                          : status === "listening"
                          ? "active-listening"
                          : ""
                      }`}
                      style={{ animationDelay: "0.2s" }}
                    />
                    <div
                      className={`visualizer-bar ${
                        status === "speaking"
                          ? "active-speaking"
                          : status === "listening"
                          ? "active-listening"
                          : ""
                      }`}
                      style={{ animationDelay: "0.4s" }}
                    />
                  </div>
                ) : (
                  <span>POWER LEVEL: 0</span>
                )}
              </div>
            </div>

            <div className="mic-section">
              <button
                className={`dragonball-btn ${isActive ? "active" : ""}`}
                onClick={isActive ? stop : start}
                aria-label={isActive ? "Stop" : "Start ordering"}
              >
                <div className="db-stars">
                  <div className="db-star">★</div>
                  <div className="db-star">★</div>
                  <div className="db-star">★</div>
                  <div className="db-star">★</div>
                </div>
                <span className="db-mic-icon">{isActive ? "■" : "🎤"}</span>
              </button>
              <div className="ssj-aura" />
              <div className="ssj-sparks" />
              <div className="voice-tip">{isActive ? "TAP TO END" : "TAP TO ORDER"}</div>
            </div>
          </div>

          {/* Compact Conversation Transcript */}
          {(messages.length > 0 || currentAgentMessage) && (
            <div className="transcript-section">
              <div
                className="chat-container"
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.75rem",
                  maxHeight: "190px",
                  overflowY: "auto",
                  paddingRight: "0.25rem",
                }}
              >
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`speech-bubble ${
                      msg.sender === "user" ? "user-bubble" : "agent-bubble"
                    }`}
                    style={{
                      alignSelf: msg.sender === "user" ? "flex-end" : "flex-start",
                      backgroundColor:
                        msg.sender === "user" ? "var(--blue-belt)" : "var(--paper-white)",
                      color: msg.sender === "user" ? "#fff" : "var(--text-dark)",
                      border: "3px solid #000",
                      boxShadow: "4px 4px 0px #000",
                      borderRadius: "12px",
                      padding: "0.65rem 0.9rem 1rem 0.9rem",
                      maxWidth: "85%",
                      position: "relative",
                      fontFamily: "'Outfit', sans-serif",
                    }}
                  >
                    <div
                      className="speech-bubble-speaker"
                      style={{
                        fontFamily: "'Bangers', cursive",
                        fontSize: "0.85rem",
                        color:
                          msg.sender === "user" ? "var(--yellow-ssj)" : "var(--orange-gi)",
                        borderBottom:
                          msg.sender === "user"
                            ? "2px solid rgba(255,255,255,0.3)"
                            : "2px solid #000",
                        paddingBottom: "0.1rem",
                        marginBottom: "0.25rem",
                        display: "inline-block",
                      }}
                    >
                      {msg.sender === "user" ? "SAIYAN CUSTOMER" : "DBZ AGENT"}
                    </div>
                    <div
                      style={{
                        fontSize: "0.88rem",
                        lineHeight: "1.35",
                        wordBreak: "break-word",
                      }}
                    >
                      {msg.text}
                    </div>
                  </div>
                ))}

                {currentAgentMessage && (
                  <div
                    className="speech-bubble agent-bubble"
                    style={{
                      alignSelf: "flex-start",
                      backgroundColor: "var(--paper-white)",
                      color: "var(--text-dark)",
                      border: "3px solid #000",
                      boxShadow: "4px 4px 0px #000",
                      borderRadius: "12px",
                      padding: "0.65rem 0.9rem 1rem 0.9rem",
                      maxWidth: "85%",
                      position: "relative",
                      fontFamily: "'Outfit', sans-serif",
                    }}
                  >
                    <div
                      className="speech-bubble-speaker"
                      style={{
                        fontFamily: "'Bangers', cursive",
                        fontSize: "0.85rem",
                        color: "var(--orange-gi)",
                        borderBottom: "2px solid #000",
                        paddingBottom: "0.1rem",
                        marginBottom: "0.25rem",
                        display: "inline-block",
                      }}
                    >
                      DBZ AGENT (SPEAKING...)
                    </div>
                    <div style={{ fontSize: "0.88rem", lineHeight: "1.35" }}>
                      {currentAgentMessage}
                    </div>
                  </div>
                )}

                <div ref={chatEndRef} />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
