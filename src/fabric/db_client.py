"""Fabric Database client for DriveThru agent tools."""

import logging
import os
from typing import Any, Iterable

import pyodbc
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

TAX_RATE = 0.08  # 8% tax


class FabricDBClient:
    """Client for interacting with Microsoft Fabric Database."""

    def __init__(self, connection_string: str | None = None):
        self.conn_str = connection_string or os.getenv("FABRIC_CONNECTION_STRING", "")
        if not self.conn_str:
            raise ValueError("FABRIC_CONNECTION_STRING is not set")

    def _get_connection(self) -> pyodbc.Connection:
        """Create a new database connection, utilizing Azure AD token auth if needed."""
        conn_str = self.conn_str
        conn_params = {}

        is_token_auth = (
            "Authentication=ActiveDirectoryInteractive" in conn_str
            or "Authentication=ActiveDirectoryDefault" in conn_str
            or "Authentication=ActiveDirectoryMsi" in conn_str
            or "Authentication=ActiveDirectoryManagedIdentity" in conn_str
            or "database.windows.net" in conn_str
            or "fabric.microsoft.com" in conn_str
            or "datawarehouse.pbidedicated.windows.net" in conn_str
        )

        if is_token_auth and "User ID=" not in conn_str and "Uid=" not in conn_str:
            try:
                from azure.identity import DefaultAzureCredential
                import struct

                # DefaultAzureCredential automatically acquires Entra ID token using Managed Identity in Azure
                cred = DefaultAzureCredential()
                db_token = cred.get_token("https://database.windows.net/.default")
                
                token_bytes = db_token.token.encode("utf-16le")
                # SQL_COPT_SS_ACCESS_TOKEN = 1256
                token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
                conn_params["attrs_before"] = {1256: token_struct}
                
                for opt in [
                    ";Authentication=ActiveDirectoryInteractive",
                    ";Authentication=ActiveDirectoryDefault",
                    ";Authentication=ActiveDirectoryMsi",
                    ";Authentication=ActiveDirectoryManagedIdentity",
                    "Authentication=ActiveDirectoryInteractive;",
                    "Authentication=ActiveDirectoryDefault;",
                    "Authentication=ActiveDirectoryMsi;",
                    "Authentication=ActiveDirectoryManagedIdentity;",
                ]:
                    conn_str = conn_str.replace(opt, "")
            except Exception as token_err:
                logger.warning(
                    "Failed to acquire Azure AD / Managed Identity token for DB connection: %s. "
                    "Falling back to base connection string.",
                    token_err
                )

        return pyodbc.connect(conn_str, **conn_params)

    # ── Menu queries ────────────────────────────────────────────────

    def get_menu(self, category: str | None = None) -> list[dict[str, Any]]:
        """
        Get available menu items, optionally filtered by category.

        Args:
            category: Filter by category (burgers, chicken, sides, drinks, desserts).
                      If None, returns all available items.

        Returns:
            List of menu item dicts with keys:
            menu_item_id, name, category, description, price, calories, allergens
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                if category:
                    cursor.execute(
                        """
                        SELECT MenuItemId, ItemName, Category, Description,
                               Price, CalorieCount, Allergens
                        FROM Menu
                        WHERE IsAvailable = 1 AND Category = ?
                        ORDER BY ItemName
                        """,
                        (category.lower(),),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT MenuItemId, ItemName, Category, Description,
                               Price, CalorieCount, Allergens
                        FROM Menu
                        WHERE IsAvailable = 1
                        ORDER BY Category, ItemName
                        """
                    )

                rows = cursor.fetchall()
                return [
                    {
                        "menu_item_id": row[0],
                        "name": row[1],
                        "category": row[2],
                        "description": row[3],
                        "price": float(row[4]),
                        "calories": row[5],
                        "allergens": row[6],
                    }
                    for row in rows
                ]

        except pyodbc.Error as e:
            logger.error("Database error in get_menu: %s", e)
            raise

    # ── Order mutations ─────────────────────────────────────────────

    def submit_order(
        self,
        items: list[dict[str, Any]],
        session_id: str = "",
    ) -> dict[str, Any]:
        """
        Submit a new order to Fabric Database.

        Args:
            items: List of dicts with keys: menu_item_id, name, quantity, price.
                   'price' is unit price per item.
            session_id: VoiceLive / agent session identifier.

        Returns:
            Dict with order_id, total, tax, grand_total, item_count.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Calculate totals
                subtotal = sum(
                    item["price"] * item["quantity"] for item in items
                )
                tax = round(subtotal * TAX_RATE, 2)
                grand_total = round(subtotal + tax, 2)

                # Insert order header
                cursor.execute(
                    """
                    INSERT INTO Orders
                        (OrderStatus, AgentSessionId, VoiceSessionId,
                         TotalAmount, TaxAmount)
                    OUTPUT INSERTED.OrderId
                    VALUES ('confirmed', ?, ?, ?, ?)
                    """,
                    (session_id, session_id, grand_total, tax),
                )
                order_id = str(cursor.fetchone()[0])

                # Insert each order item
                for item in items:
                    cursor.execute(
                        """
                        INSERT INTO OrderItems
                            (OrderId, MenuItemId, ItemName, Quantity, UnitPrice)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            order_id,
                            item["menu_item_id"],
                            item["name"],
                            item["quantity"],
                            item["price"],
                        ),
                    )

                conn.commit()

                logger.info("Order %s submitted (%d items, $%.2f)", order_id, len(items), grand_total)

                return {
                    "order_id": order_id,
                    "total": round(subtotal, 2),
                    "tax": tax,
                    "grand_total": grand_total,
                    "item_count": sum(i["quantity"] for i in items),
                }

        except pyodbc.Error as e:
            logger.error("Database error in submit_order: %s", e)
            raise

    # ── Analytics queries ───────────────────────────────────────────

    def get_order_analytics(self, metric: str, time_period: str = "today") -> list[dict[str, Any]] | dict[str, Any]:
        """
        Query order analytics from the database.
        
        Args:
            metric: "popular_items", "order_count", "revenue", "average_order_value"
            time_period: "today", "week", "month"
        """
        # Determine date filter
        if time_period == "today":
            date_filter = "CAST(GETUTCDATE() AS DATE)"
            time_filter = "OrderTimestamp >= CAST(GETUTCDATE() AS DATE)"
        elif time_period == "week":
            date_filter = "DATEADD(day, -7, CAST(GETUTCDATE() AS DATE))"
            time_filter = "OrderTimestamp >= DATEADD(day, -7, CAST(GETUTCDATE() AS DATE))"
        else:  # month
            date_filter = "DATEADD(month, -1, CAST(GETUTCDATE() AS DATE))"
            time_filter = "OrderTimestamp >= DATEADD(month, -1, CAST(GETUTCDATE() AS DATE))"

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                if metric == "popular_items":
                    sql = f"""
                        SELECT MenuItemId, ItemName, ItemCategory, SUM(TotalQuantitySold) AS TotalQty, SUM(ItemRevenue) AS TotalRev
                        FROM OrderAnalytics
                        WHERE OrderDate >= {date_filter}
                        GROUP BY MenuItemId, ItemName, ItemCategory
                        ORDER BY TotalQty DESC
                    """
                    cursor.execute(sql)
                    rows = cursor.fetchall()
                    return [
                        {
                            "menu_item_id": row[0],
                            "name": row[1],
                            "category": row[2],
                            "quantity_sold": int(row[3]) if row[3] is not None else 0,
                            "revenue": float(row[4]) if row[4] is not None else 0.0,
                        }
                        for row in rows
                    ]
                
                elif metric == "order_count":
                    sql = f"""
                        SELECT COUNT(OrderId) 
                        FROM Orders 
                        WHERE OrderStatus IN ('confirmed', 'preparing', 'ready', 'completed') AND {time_filter}
                    """
                    cursor.execute(sql)
                    row = cursor.fetchone()
                    count = row[0] if row and row[0] is not None else 0
                    return {"metric": "order_count", "time_period": time_period, "value": count}
                
                elif metric == "revenue":
                    sql = f"""
                        SELECT SUM(TotalAmount) 
                        FROM Orders 
                        WHERE OrderStatus IN ('confirmed', 'preparing', 'ready', 'completed') AND {time_filter}
                    """
                    cursor.execute(sql)
                    row = cursor.fetchone()
                    rev = float(row[0]) if row and row[0] is not None else 0.0
                    return {"metric": "revenue", "time_period": time_period, "value": rev}
                
                elif metric == "average_order_value":
                    sql = f"""
                        SELECT AVG(TotalAmount) 
                        FROM Orders 
                        WHERE OrderStatus IN ('confirmed', 'preparing', 'ready', 'completed') AND {time_filter}
                    """
                    cursor.execute(sql)
                    row = cursor.fetchone()
                    aov = float(row[0]) if row and row[0] is not None else 0.0
                    return {"metric": "average_order_value", "time_period": time_period, "value": aov}
                
                else:
                    raise ValueError(f"Unknown metric: {metric}")
                    
        except pyodbc.Error as e:
            logger.error("Database error in get_order_analytics: %s", e)
            raise

    # ── Demo data seeding ───────────────────────────────────────────

    def upsert_menu(self, items: Iterable[dict[str, Any]]) -> int:
        """
        MERGE-upsert menu items by MenuItemId. Returns number of rows processed.

        Each item dict requires: menu_item_id, name, category, description,
        price, calories, allergens (allergens may be None).
        """
        rows = list(items)
        if not rows:
            return 0
        merge_sql = """
            MERGE Menu AS target
            USING (SELECT ? AS MenuItemId, ? AS ItemName, ? AS Category,
                          ? AS Description, ? AS Price, ? AS CalorieCount,
                          ? AS Allergens) AS src
            ON target.MenuItemId = src.MenuItemId
            WHEN MATCHED THEN UPDATE SET
                ItemName = src.ItemName,
                Category = src.Category,
                Description = src.Description,
                Price = src.Price,
                CalorieCount = src.CalorieCount,
                Allergens = src.Allergens,
                IsAvailable = 1,
                UpdatedAt = GETUTCDATE()
            WHEN NOT MATCHED THEN INSERT
                (MenuItemId, ItemName, Category, Description, Price, CalorieCount, Allergens)
                VALUES (src.MenuItemId, src.ItemName, src.Category, src.Description,
                        src.Price, src.CalorieCount, src.Allergens);
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                for row in rows:
                    cursor.execute(
                        merge_sql,
                        (
                            row["menu_item_id"],
                            row["name"],
                            row["category"],
                            row.get("description"),
                            row["price"],
                            row.get("calories"),
                            row.get("allergens"),
                        ),
                    )
                conn.commit()
        except pyodbc.Error as e:
            logger.error("Database error in upsert_menu: %s", e)
            raise
        return len(rows)

    def upsert_customers(self, customers: Iterable[dict[str, Any]]) -> int:
        """MERGE-upsert customers by CustomerId. Returns number of rows processed."""
        rows = list(customers)
        if not rows:
            return 0
        merge_sql = """
            MERGE Customers AS target
            USING (SELECT ? AS CustomerId, ? AS FirstName, ? AS LastName,
                          ? AS Email, ? AS PhoneNumber,
                          ? AS PreferredPaymentMethod, ? AS LoyaltyPoints) AS src
            ON target.CustomerId = src.CustomerId
            WHEN MATCHED THEN UPDATE SET
                FirstName = src.FirstName,
                LastName = src.LastName,
                Email = src.Email,
                PhoneNumber = src.PhoneNumber,
                PreferredPaymentMethod = src.PreferredPaymentMethod,
                LoyaltyPoints = src.LoyaltyPoints
            WHEN NOT MATCHED THEN INSERT
                (CustomerId, FirstName, LastName, Email, PhoneNumber,
                 PreferredPaymentMethod, LoyaltyPoints)
                VALUES (src.CustomerId, src.FirstName, src.LastName, src.Email,
                        src.PhoneNumber, src.PreferredPaymentMethod, src.LoyaltyPoints);
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                for row in rows:
                    cursor.execute(
                        merge_sql,
                        (
                            row["customer_id"],
                            row.get("first_name"),
                            row.get("last_name"),
                            row.get("email"),
                            row.get("phone_number"),
                            row.get("preferred_payment"),
                            row.get("loyalty_points", 0),
                        ),
                    )
                conn.commit()
        except pyodbc.Error as e:
            logger.error("Database error in upsert_customers: %s", e)
            raise
        return len(rows)

    def insert_orders_bulk(self, orders: Iterable[Any]) -> int:
        """
        Bulk-insert orders with their items. Each order is a `GeneratedOrder`
        (or any object exposing the same attributes: order_id, customer_id,
        timestamp, status, payment_method, total_amount, tax_amount, items).

        Inserts use the explicit OrderId so we can deterministically link
        OrderItems without a SELECT round-trip.
        """
        order_list = list(orders)
        if not order_list:
            return 0

        order_sql = """
            INSERT INTO Orders
                (OrderId, CustomerId, OrderTimestamp, OrderStatus,
                 TotalAmount, TaxAmount, PaymentMethod, PaymentStatus,
                 AgentSessionId)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        item_sql = """
            INSERT INTO OrderItems
                (OrderId, MenuItemId, ItemName, Quantity, UnitPrice)
            VALUES (?, ?, ?, ?, ?)
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.fast_executemany = True

                order_rows = [
                    (
                        o.order_id,
                        o.customer_id,
                        o.timestamp,
                        o.status,
                        o.total_amount,
                        o.tax_amount,
                        o.payment_method,
                        "paid" if o.status != "cancelled" else "refunded",
                        f"demo-seed-{o.order_id[:8]}",
                    )
                    for o in order_list
                ]
                cursor.executemany(order_sql, order_rows)

                item_rows = [
                    (
                        o.order_id,
                        it["menu_item_id"],
                        it["name"],
                        it["quantity"],
                        it["price"],
                    )
                    for o in order_list
                    for it in o.items
                ]
                cursor.executemany(item_sql, item_rows)
                conn.commit()
        except pyodbc.Error as e:
            logger.error("Database error in insert_orders_bulk: %s", e)
            raise
        return len(order_list)

    def reset_orders(self) -> None:
        """DELETE all rows from OrderItems and Orders. Use with care."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM OrderItems")
                cursor.execute("DELETE FROM Orders")
                conn.commit()
        except pyodbc.Error as e:
            logger.error("Database error in reset_orders: %s", e)
            raise
