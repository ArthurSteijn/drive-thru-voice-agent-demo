"""
Pure-Python demo data generators for the DriveThru Fabric database.

These functions return plain dicts/lists with no database dependency,
so they're easy to unit-test. The CLI wrapper in `seed_demo_data.py`
uses `FabricDBClient` to persist them.

Distributions:
- Order arrival times follow a bimodal day curve (lunch peak 11–13,
  dinner peak 17–20) with a weekend bump.
- Item selection is popularity-weighted (burgers/fries/drinks dominate).
- Order status mix: ~85% completed, ~10% ready/preparing, ~5% cancelled.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

# ── Constants ───────────────────────────────────────────────────────

TAX_RATE = 0.08

# Hourly weights for the bimodal day curve (24 entries, sum > 0).
# Index = hour of day. Lunch peak 11–13, dinner peak 17–20, quiet at night.
HOURLY_WEIGHTS: tuple[float, ...] = (
    0.1, 0.05, 0.05, 0.05, 0.1, 0.3,   # 00–05
    0.6, 1.0, 1.5, 1.5, 2.0, 4.0,      # 06–11
    5.0, 4.5, 2.5, 2.0, 2.5, 4.5,      # 12–17
    5.0, 4.5, 3.5, 2.0, 1.0, 0.4,      # 18–23
)

ORDER_STATUS_WEIGHTS: dict[str, float] = {
    "completed": 0.85,
    "ready": 0.05,
    "preparing": 0.05,
    "cancelled": 0.05,
}

PAYMENT_METHODS: tuple[str, ...] = ("card", "cash", "mobile")

# ── Menu seed (richer than schema-setup.sql starter) ────────────────

MENU_SEED: list[dict[str, Any]] = [
    # Burgers
    {"menu_item_id": "BURGER_001", "name": "Classic Cheeseburger",     "category": "burgers",  "description": "Our signature cheeseburger with lettuce, tomato, and special sauce", "price":  8.99, "calories": 650, "allergens": "gluten,dairy"},
    {"menu_item_id": "BURGER_002", "name": "DriveThru Deluxe",          "category": "burgers",  "description": "Double patty with bacon, cheese, and all the fixings",               "price": 12.99, "calories": 920, "allergens": "gluten,dairy"},
    {"menu_item_id": "BURGER_003", "name": "Mushroom Swiss Burger",    "category": "burgers",  "description": "Beef patty topped with sautéed mushrooms and Swiss cheese",          "price": 10.99, "calories": 780, "allergens": "gluten,dairy"},
    {"menu_item_id": "BURGER_004", "name": "Veggie Burger",            "category": "burgers",  "description": "Plant-based patty with avocado and sprouts",                          "price":  9.99, "calories": 540, "allergens": "gluten,soy"},
    {"menu_item_id": "BURGER_005", "name": "Spicy Jalapeño Burger",    "category": "burgers",  "description": "Pepper-jack cheese, jalapeños, chipotle mayo",                        "price": 10.49, "calories": 810, "allergens": "gluten,dairy"},

    # Chicken
    {"menu_item_id": "CHICKEN_001", "name": "Crispy Chicken Sandwich", "category": "chicken",  "description": "Breaded chicken breast with pickles and mayo",                        "price":  9.99, "calories": 580, "allergens": "gluten,egg"},
    {"menu_item_id": "CHICKEN_002", "name": "Grilled Chicken Wrap",    "category": "chicken",  "description": "Grilled chicken with lettuce, tomato, ranch in a flour tortilla",     "price":  8.49, "calories": 460, "allergens": "gluten,dairy"},
    {"menu_item_id": "CHICKEN_003", "name": "Chicken Tenders (5pc)",   "category": "chicken",  "description": "Five hand-breaded tenders with dipping sauce",                        "price":  7.99, "calories": 540, "allergens": "gluten,egg"},
    {"menu_item_id": "CHICKEN_004", "name": "Buffalo Chicken Sandwich","category": "chicken",  "description": "Crispy chicken tossed in buffalo sauce with blue cheese",             "price": 10.49, "calories": 670, "allergens": "gluten,dairy,egg"},

    # Sides
    {"menu_item_id": "SIDE_001", "name": "French Fries",              "category": "sides",    "description": "Golden crispy fries (Medium)",                                        "price":  3.49, "calories": 380, "allergens": None},
    {"menu_item_id": "SIDE_002", "name": "Onion Rings",                "category": "sides",    "description": "Beer-battered onion rings",                                           "price":  4.49, "calories": 410, "allergens": "gluten"},
    {"menu_item_id": "SIDE_003", "name": "Sweet Potato Fries",         "category": "sides",    "description": "Crispy sweet potato fries with cinnamon sugar",                       "price":  4.29, "calories": 340, "allergens": None},
    {"menu_item_id": "SIDE_004", "name": "Side Salad",                 "category": "sides",    "description": "Mixed greens, tomato, cucumber, vinaigrette",                         "price":  4.99, "calories": 180, "allergens": None},
    {"menu_item_id": "SIDE_005", "name": "Mozzarella Sticks (4pc)",    "category": "sides",    "description": "Breaded mozzarella with marinara sauce",                              "price":  5.49, "calories": 470, "allergens": "gluten,dairy"},

    # Drinks
    {"menu_item_id": "DRINK_001", "name": "Soft Drink",                "category": "drinks",   "description": "Cold soft drink (Medium)",                                            "price":  2.49, "calories": 210, "allergens": None},
    {"menu_item_id": "DRINK_002", "name": "Milkshake",                 "category": "drinks",   "description": "Creamy milkshake (vanilla, chocolate, or strawberry)",                "price":  4.99, "calories": 520, "allergens": "dairy"},
    {"menu_item_id": "DRINK_003", "name": "Iced Coffee",               "category": "drinks",   "description": "Cold-brew iced coffee",                                               "price":  3.49, "calories":  90, "allergens": "dairy"},
    {"menu_item_id": "DRINK_004", "name": "Fresh Lemonade",            "category": "drinks",   "description": "Hand-squeezed lemonade",                                              "price":  3.29, "calories": 150, "allergens": None},
    {"menu_item_id": "DRINK_005", "name": "Bottled Water",             "category": "drinks",   "description": "16 oz purified bottled water",                                        "price":  1.99, "calories":   0, "allergens": None},

    # Desserts
    {"menu_item_id": "DESSERT_001", "name": "Apple Pie",               "category": "desserts", "description": "Warm apple pie",                                                      "price":  3.99, "calories": 320, "allergens": "gluten"},
    {"menu_item_id": "DESSERT_002", "name": "Chocolate Brownie",       "category": "desserts", "description": "Fudgy chocolate brownie",                                             "price":  3.49, "calories": 410, "allergens": "gluten,dairy,egg"},
    {"menu_item_id": "DESSERT_003", "name": "Ice Cream Sundae",        "category": "desserts", "description": "Vanilla ice cream with chocolate sauce and a cherry",                 "price":  4.49, "calories": 480, "allergens": "dairy"},
    {"menu_item_id": "DESSERT_004", "name": "Cookie (3pc)",            "category": "desserts", "description": "Three warm chocolate chip cookies",                                   "price":  2.99, "calories": 360, "allergens": "gluten,dairy,egg"},
]

# Per-category popularity weight when picking what goes into an order
CATEGORY_WEIGHTS: dict[str, float] = {
    "burgers": 4.0,
    "chicken": 2.5,
    "sides": 4.0,
    "drinks": 4.5,
    "desserts": 1.5,
}

# ── Customer seed ───────────────────────────────────────────────────

CUSTOMER_SEED: list[dict[str, Any]] = [
    {"customer_id": "CUST_001", "first": "Alice",   "last": "Andersen",  "phone": "+15551110001", "payment": "card"},
    {"customer_id": "CUST_002", "first": "Bashir",  "last": "Bakr",      "phone": "+15551110002", "payment": "mobile"},
    {"customer_id": "CUST_003", "first": "Chen",    "last": "Cao",       "phone": "+15551110003", "payment": "card"},
    {"customer_id": "CUST_004", "first": "Dana",    "last": "Davis",     "phone": "+15551110004", "payment": "cash"},
    {"customer_id": "CUST_005", "first": "Esi",     "last": "Edusei",    "phone": "+15551110005", "payment": "card"},
    {"customer_id": "CUST_006", "first": "Farah",   "last": "Fadel",     "phone": "+15551110006", "payment": "mobile"},
    {"customer_id": "CUST_007", "first": "Gus",     "last": "Garcia",    "phone": "+15551110007", "payment": "card"},
    {"customer_id": "CUST_008", "first": "Hana",    "last": "Hayashi",   "phone": "+15551110008", "payment": "card"},
    {"customer_id": "CUST_009", "first": "Idris",   "last": "Iqbal",     "phone": "+15551110009", "payment": "mobile"},
    {"customer_id": "CUST_010", "first": "Jordan",  "last": "Johnson",   "phone": "+15551110010", "payment": "cash"},
    {"customer_id": "CUST_011", "first": "Kai",     "last": "Kowalski",  "phone": "+15551110011", "payment": "card"},
    {"customer_id": "CUST_012", "first": "Lila",    "last": "Lindgren",  "phone": "+15551110012", "payment": "mobile"},
]

# ── Generators ──────────────────────────────────────────────────────


def generate_menu() -> list[dict[str, Any]]:
    """Return the canonical demo menu (deep-copied to prevent mutation)."""
    return [dict(item) for item in MENU_SEED]


def generate_customers() -> list[dict[str, Any]]:
    """Return demo customer profiles ready for upsert."""
    return [
        {
            "customer_id": c["customer_id"],
            "first_name": c["first"],
            "last_name": c["last"],
            "email": f"{c['first'].lower()}.{c['last'].lower()}@example.com",
            "phone_number": c["phone"],
            "preferred_payment": c["payment"],
            "loyalty_points": (i + 1) * 50,
        }
        for i, c in enumerate(CUSTOMER_SEED)
    ]


@dataclass
class GeneratedOrder:
    """An order ready for bulk insertion."""

    order_id: str
    customer_id: str | None
    timestamp: datetime
    status: str
    payment_method: str
    total_amount: float       # subtotal + tax
    tax_amount: float
    items: list[dict[str, Any]] = field(default_factory=list)


def _weighted_choice(rng: random.Random, options: list[Any], weights: list[float]) -> Any:
    return rng.choices(options, weights=weights, k=1)[0]


def _pick_hour(rng: random.Random, day_weight_multiplier: float) -> int:
    weights = [w * day_weight_multiplier for w in HOURLY_WEIGHTS]
    return rng.choices(range(24), weights=weights, k=1)[0]


def _pick_status(rng: random.Random) -> str:
    statuses = list(ORDER_STATUS_WEIGHTS.keys())
    weights = list(ORDER_STATUS_WEIGHTS.values())
    return str(_weighted_choice(rng, statuses, weights))


def _pick_items(
    rng: random.Random,
    menu: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pick 1–5 items biased by category popularity. No duplicate menu items."""
    n = rng.choices([1, 2, 3, 4, 5], weights=[15, 35, 30, 15, 5], k=1)[0]
    weights = [CATEGORY_WEIGHTS.get(item["category"], 1.0) for item in menu]
    chosen: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    attempts = 0
    while len(chosen) < n and attempts < n * 5:
        item = rng.choices(menu, weights=weights, k=1)[0]
        attempts += 1
        if item["menu_item_id"] in seen_ids:
            continue
        seen_ids.add(item["menu_item_id"])
        quantity = rng.choices([1, 2, 3], weights=[75, 20, 5], k=1)[0]
        chosen.append(
            {
                "menu_item_id": item["menu_item_id"],
                "name": item["name"],
                "quantity": quantity,
                "price": float(item["price"]),
            }
        )
    return chosen


def _compute_totals(items: list[dict[str, Any]]) -> tuple[float, float]:
    """Return (total_amount_with_tax, tax_amount)."""
    subtotal = sum(it["price"] * it["quantity"] for it in items)
    tax = round(subtotal * TAX_RATE, 2)
    total = round(subtotal + tax, 2)
    return total, tax


def generate_orders(
    *,
    menu: list[dict[str, Any]],
    customers: list[dict[str, Any]],
    days: int = 60,
    orders_per_day: int = 25,
    end_date: datetime | None = None,
    customer_attach_rate: float = 1.0,
    seed: int = 42,
) -> list[GeneratedOrder]:
    """
    Generate a list of synthetic orders ending at `end_date` (default: now UTC).

    The number of orders per day is drawn from N(orders_per_day, sqrt(orders_per_day))
    and weekends get a +30% multiplier. Hours follow HOURLY_WEIGHTS.
    """
    if not menu:
        raise ValueError("menu must not be empty")
    if days < 1 or orders_per_day < 1:
        raise ValueError("days and orders_per_day must be >= 1")

    rng = random.Random(seed)
    end_date = end_date or datetime.now(timezone.utc)
    end_day = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

    orders: list[GeneratedOrder] = []
    for day_offset in range(days):
        day = end_day - timedelta(days=days - 1 - day_offset)
        is_weekend = day.weekday() >= 5
        day_multiplier = 1.3 if is_weekend else 1.0

        # Vary daily volume around the mean
        daily_count = max(
            1,
            int(rng.gauss(orders_per_day * day_multiplier, max(1.0, orders_per_day**0.5))),
        )

        for _ in range(daily_count):
            hour = _pick_hour(rng, day_multiplier)
            minute = rng.randint(0, 59)
            second = rng.randint(0, 59)
            ts = day.replace(hour=hour, minute=minute, second=second)

            items = _pick_items(rng, menu)
            if not items:
                continue
            total, tax = _compute_totals(items)

            customer_id: str | None = None
            if customers and rng.random() < customer_attach_rate:
                customer_id = rng.choice(customers)["customer_id"]

            orders.append(
                GeneratedOrder(
                    order_id=str(uuid.UUID(int=rng.getrandbits(128))),
                    customer_id=customer_id,
                    timestamp=ts,
                    status=_pick_status(rng),
                    payment_method=rng.choice(PAYMENT_METHODS),
                    total_amount=total,
                    tax_amount=tax,
                    items=items,
                )
            )

    orders.sort(key=lambda o: o.timestamp)
    return orders


__all__ = [
    "TAX_RATE",
    "HOURLY_WEIGHTS",
    "ORDER_STATUS_WEIGHTS",
    "MENU_SEED",
    "CUSTOMER_SEED",
    "GeneratedOrder",
    "generate_menu",
    "generate_customers",
    "generate_orders",
]
