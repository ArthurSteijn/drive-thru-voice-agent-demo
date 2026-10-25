# Database Guide

> Last Updated: 2026-03-31

## Overview

The DriveThru demo uses **Microsoft Fabric SQL Database** for transactional storage. The database stores menu items, customer orders, and analytics data used by the AI agents.

## Provisioning

### Automated (Recommended)

Run the setup script to create the workspace, database, and schema automatically:

```powershell
az login
python platform/fabric/setup_fabric.py
```

See [platform/fabric/README.md](../platform/fabric/README.md) for full usage details.

### Manual

1. Open the [Fabric Portal](https://app.fabric.microsoft.com)
2. Create a workspace → assign a capacity (trial works)
3. Create a **SQL Database** named `DriveThru`
4. Open the SQL query editor
5. Paste and run `src/fabric/schema-setup.sql`
6. Copy the connection string from **Settings → Connection strings**

## Schema

The schema is defined in [`src/fabric/schema-setup.sql`](../src/fabric/schema-setup.sql).

### Tables

#### Menu
| Column | Type | Description |
|--------|------|-------------|
| `MenuItemId` | VARCHAR(50) PK | Item identifier (e.g., `BURGER_001`) |
| `ItemName` | VARCHAR(100) | Display name |
| `Category` | VARCHAR(50) | burgers, chicken, sides, drinks, desserts |
| `Description` | NVARCHAR(500) | Item description |
| `Price` | DECIMAL(10,2) | Unit price |
| `IsAvailable` | BIT | Whether currently available |
| `Allergens` | NVARCHAR(200) | Allergen info |
| `CalorieCount` | INT | Calories |
| `ImageUrl` | VARCHAR(500) | Menu image URL |

#### Orders
| Column | Type | Description |
|--------|------|-------------|
| `OrderId` | UNIQUEIDENTIFIER PK | Auto-generated GUID |
| `CustomerId` | VARCHAR(50) | Optional customer reference |
| `OrderTimestamp` | DATETIME2 | When order was placed |
| `OrderStatus` | VARCHAR(20) | pending → confirmed → preparing → ready → completed |
| `TotalAmount` | DECIMAL(10,2) | Grand total including tax |
| `TaxAmount` | DECIMAL(10,2) | Tax amount |
| `AgentSessionId` | VARCHAR(100) | Foundry agent session |
| `VoiceSessionId` | VARCHAR(100) | VoiceLive session |

#### OrderItems
| Column | Type | Description |
|--------|------|-------------|
| `OrderItemId` | UNIQUEIDENTIFIER PK | Auto-generated GUID |
| `OrderId` | UNIQUEIDENTIFIER FK | References Orders |
| `MenuItemId` | VARCHAR(50) FK | References Menu |
| `ItemName` | VARCHAR(100) | Item name at time of order |
| `Quantity` | INT | Number of items |
| `UnitPrice` | DECIMAL(10,2) | Price per item |
| `Subtotal` | Computed | Quantity × UnitPrice |

#### Customers (Optional)
Stores customer profiles for loyalty and preferences.

### Views

#### OrderAnalytics
Aggregated view for the analytics agent — shows daily/hourly order trends, popular items, and revenue by category.

## Connection String

The connection string format for Fabric SQL Database:

```
Driver={ODBC Driver 18 for SQL Server};Server=<server>.datawarehouse.fabric.microsoft.com;Database=DriveThru;Encrypt=yes;TrustServerCertificate=no;Authentication=ActiveDirectoryInteractive
```

Set this as `FABRIC_CONNECTION_STRING` in your `.env` file.

## Client Code

The database client is at [`src/fabric/db_client.py`](../src/fabric/db_client.py). It provides:

- `get_menu(category?)` — query available menu items
- `submit_order(items, session_id)` — insert order with items, calculate tax

Used by the agent tools in `src/agent_tools/`:
- `menu_tools.py` → calls `db_client.get_menu()`
- `order_tools.py` → calls `db_client.submit_order()`

## Seed Demo Data

The starter `schema-setup.sql` only inserts 8 menu items and leaves
`Customers` / `Orders` / `OrderItems` empty. For richer demos (popular-items
recommendations, time-of-day trends, returning customers) run the Python
seeder once the schema exists:

```powershell
# Preview what will be generated (no DB writes)
python -m src.fabric.seed_demo_data --dry-run

# Wipe Orders/OrderItems and seed 60 days × ~25 orders/day (default)
python -m src.fabric.seed_demo_data --reset --yes

# Custom volume
python -m src.fabric.seed_demo_data --days 90 --orders-per-day 30 --reset --yes
```

Flags:

| Flag | Default | Purpose |
|------|---------|---------|
| `--days` | 60 | Days of order history |
| `--orders-per-day` | 25 | Average orders per day (Gaussian + weekend bump) |
| `--reset` | off | DELETE OrderItems + Orders before seeding |
| `--yes` | off | Skip the `--reset` confirmation prompt |
| `--seed` | 42 | Random seed (same seed → same data) |
| `--dry-run` | off | Generate + summarize, no DB writes |

What the seeder does:

- **Menu** — upserts ~25 items across burgers/chicken/sides/drinks/desserts (idempotent via `MERGE`)
- **Customers** — upserts 12 synthetic profiles with loyalty points and payment preferences
- **Orders** — generates realistic timestamps (lunch peak 11–13, dinner peak 17–20, weekend bump),
  1–5 items per order weighted toward popular categories, ~85% completed / ~10% in-progress / ~5% cancelled
- **Totals** — pre-computes `TotalAmount` and `TaxAmount` (8% tax) so `OrderAnalytics` view returns useful rows immediately

Requires `FABRIC_CONNECTION_STRING` in `.env` unless `--dry-run` is used.

## Sample Queries

```sql
-- Check menu items
SELECT * FROM Menu WHERE IsAvailable = 1 ORDER BY Category;

-- Recent orders
SELECT TOP 10 * FROM Orders ORDER BY OrderTimestamp DESC;

-- Popular items today
SELECT oi.ItemName, SUM(oi.Quantity) AS TotalSold
FROM OrderItems oi
JOIN Orders o ON oi.OrderId = o.OrderId
WHERE CAST(o.OrderTimestamp AS DATE) = CAST(GETUTCDATE() AS DATE)
GROUP BY oi.ItemName
ORDER BY TotalSold DESC;
```

## Related Pages

- [README](../README.md)
- [Architecture Specs](./architecture-specs.md)
- [Agent Workflow](./agent-workflow.md)
