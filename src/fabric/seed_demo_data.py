"""
CLI to seed the DriveThru Fabric database with realistic demo data.

Usage:
    python -m src.fabric.seed_demo_data --help
    python -m src.fabric.seed_demo_data                       # seed default 60 days
    python -m src.fabric.seed_demo_data --days 90 --orders-per-day 30
    python -m src.fabric.seed_demo_data --reset --yes         # wipe + reseed
    python -m src.fabric.seed_demo_data --dry-run             # no DB writes

Requires the FABRIC_CONNECTION_STRING environment variable.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter

from src.fabric.db_client import FabricDBClient
from src.fabric.demo_data import (
    generate_customers,
    generate_menu,
    generate_orders,
)

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.fabric.seed_demo_data",
        description="Seed the DriveThru Fabric DB with realistic demo data.",
    )
    parser.add_argument("--days", type=int, default=60,
                        help="Days of order history to generate (default: 60).")
    parser.add_argument("--orders-per-day", type=int, default=25,
                        help="Average orders per day (default: 25).")
    parser.add_argument("--reset", action="store_true",
                        help="Delete existing Orders/OrderItems before seeding.")
    parser.add_argument("--yes", action="store_true",
                        help="Skip the confirmation prompt for --reset.")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility (default: 42).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate data and print a summary without writing to the DB.")
    return parser


def _summarize_orders(orders: list) -> dict:
    """Return a small summary dict for printing."""
    if not orders:
        return {"count": 0}
    statuses = Counter(o.status for o in orders)
    item_count = sum(len(o.items) for o in orders)
    revenue = sum(o.total_amount for o in orders)
    return {
        "count": len(orders),
        "first_order": orders[0].timestamp.isoformat(),
        "last_order": orders[-1].timestamp.isoformat(),
        "total_items": item_count,
        "total_revenue": round(revenue, 2),
        "by_status": dict(statuses),
    }


def _confirm_reset(args: argparse.Namespace) -> bool:
    if not args.reset or args.yes:
        return True
    print("WARNING: --reset will DELETE all rows from OrderItems and Orders.")
    answer = input("Proceed? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = _build_parser().parse_args(argv)

    # ── Generate data (no DB needed yet) ────────────────────────────
    menu = generate_menu()
    customers = generate_customers()
    orders = generate_orders(
        menu=menu,
        customers=customers,
        days=args.days,
        orders_per_day=args.orders_per_day,
        seed=args.seed,
    )
    summary = _summarize_orders(orders)

    print("Generated demo data:")
    print(f"  Menu items:    {len(menu)}")
    print(f"  Customers:     {len(customers)}")
    print(f"  Orders:        {summary['count']}")
    if summary["count"]:
        print(f"  Date range:    {summary['first_order']} -> {summary['last_order']}")
        print(f"  Total items:   {summary['total_items']}")
        print(f"  Total revenue: ${summary['total_revenue']:.2f}")
        print(f"  By status:     {summary['by_status']}")

    if args.dry_run:
        print("\n[--dry-run] No database writes performed.")
        return 0

    # ── DB writes ───────────────────────────────────────────────────
    if not os.getenv("FABRIC_CONNECTION_STRING"):
        print(
            "\nERROR: FABRIC_CONNECTION_STRING is not set. Either configure it "
            "in your .env file or pass --dry-run.",
            file=sys.stderr,
        )
        return 2

    if not _confirm_reset(args):
        print("Aborted by user.")
        return 1

    db = FabricDBClient()

    if args.reset:
        logger.info("Resetting OrderItems and Orders…")
        db.reset_orders()

    logger.info("Upserting %d menu items…", len(menu))
    db.upsert_menu(menu)

    logger.info("Upserting %d customers…", len(customers))
    db.upsert_customers(customers)

    logger.info("Inserting %d orders (with %d order items)…",
                summary["count"], summary["total_items"])
    db.insert_orders_bulk(orders)

    print("\nDemo data seeded successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
