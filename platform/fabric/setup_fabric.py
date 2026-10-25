"""
Fabric CI/CD Setup Script
==========================
Automates end-to-end Microsoft Fabric provisioning for the DriveThru demo:

1. Authenticate via AzureCliCredential
2. Find trial capacity (or use provided FABRIC_CAPACITY_ID)
3. Create workspace with capacity assignment
4. Create Fabric SQL Database
5. Get SQL connection string
6. Run schema from src/fabric/schema-setup.sql
7. Prompt to seed demo data via src/fabric/seed_demo_data.py

Usage:
    az login
    python platform/fabric/setup_fabric.py

Environment variables (all optional — sensible defaults provided):
    FABRIC_WORKSPACE_NAME  — workspace display name  (default: ws-drivethru-demo)
    FABRIC_CAPACITY_ID     — capacity GUID            (default: auto-detect trial)
    FABRIC_DB_NAME         — SQL database name         (default: DriveThru)
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import time

import pyodbc
import requests
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# ── Constants ───────────────────────────────────────────────────────
FABRIC_API = "https://api.fabric.microsoft.com/v1"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_SQL = REPO_ROOT / "src" / "fabric" / "schema-setup.sql"
POLL_INTERVAL = 5  # seconds between provisioning polls
POLL_TIMEOUT = 300  # max seconds to wait for async operations


def get_token() -> str:
    """Acquire a bearer token for the Fabric REST API via Azure CLI."""
    try:
        cred = AzureCliCredential()
        token = cred.get_token(FABRIC_SCOPE)
        print("✅ Authenticated via Azure CLI")
        return token.token
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        print("   Run 'az login' first, then retry.")
        sys.exit(1)


def api_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ── Capacity ────────────────────────────────────────────────────────
def find_trial_capacity(token: str) -> str | None:
    """List capacities and return the first trial capacity ID found."""
    resp = requests.get(f"{FABRIC_API}/capacities", headers=api_headers(token), timeout=30)
    resp.raise_for_status()
    capacities = resp.json().get("value", [])

    for cap in capacities:
        sku = cap.get("sku", "").lower()
        state = cap.get("state", "").lower()
        # Trial capacities use SKU "FT1" and state should be "Active"
        if sku.startswith("ft") and state == "active":
            print(f"✅ Found trial capacity: {cap['displayName']} ({cap['id']})")
            return cap["id"]

    # If no trial found, return the first active capacity
    for cap in capacities:
        if cap.get("state", "").lower() == "active":
            print(f"⚠️  No trial capacity found — using: {cap['displayName']} ({cap['id']})")
            return cap["id"]

    return None


# ── Workspace ───────────────────────────────────────────────────────
def find_workspace(token: str, name: str) -> str | None:
    """Find an existing workspace by display name. Returns workspace ID or None."""
    resp = requests.get(f"{FABRIC_API}/workspaces", headers=api_headers(token), timeout=30)
    resp.raise_for_status()
    for ws in resp.json().get("value", []):
        if ws["displayName"] == name:
            return ws["id"]
    return None


def create_workspace(token: str, name: str, capacity_id: str) -> str:
    """Create a Fabric workspace assigned to the given capacity. Returns workspace ID."""
    existing = find_workspace(token, name)
    if existing:
        print(f"✅ Workspace already exists: {name} ({existing})")
        return existing

    body = {
        "displayName": name,
        "capacityId": capacity_id,
        "description": "DriveThru Agent Demo — auto-provisioned by setup_fabric.py",
    }
    resp = requests.post(
        f"{FABRIC_API}/workspaces", json=body, headers=api_headers(token), timeout=30
    )
    resp.raise_for_status()
    ws = resp.json()
    ws_id = ws["id"]
    print(f"✅ Workspace created: {name} ({ws_id})")
    return ws_id


# ── SQL Database ────────────────────────────────────────────────────
def find_sql_database(token: str, workspace_id: str, db_name: str) -> dict | None:
    """Find an existing SQL database in the workspace. Returns item dict or None."""
    resp = requests.get(
        f"{FABRIC_API}/workspaces/{workspace_id}/sqlDatabases",
        headers=api_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    for db in resp.json().get("value", []):
        if db["displayName"] == db_name:
            return db
    return None


def poll_operation(token: str, location_url: str) -> dict:
    """Poll a long-running operation until completion."""
    elapsed = 0
    while elapsed < POLL_TIMEOUT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        resp = requests.get(location_url, headers=api_headers(token), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", "").lower()
        print(f"   ⏳ Provisioning... ({elapsed}s, status: {status})")
        if status in ("succeeded", "completed"):
            return data
        if status in ("failed", "cancelled"):
            raise RuntimeError(f"Operation failed: {data}")
    raise TimeoutError(f"Operation did not complete within {POLL_TIMEOUT}s")


def create_sql_database(token: str, workspace_id: str, db_name: str) -> dict:
    """Create a Fabric SQL Database. Returns the database item dict."""
    existing = find_sql_database(token, workspace_id, db_name)
    if existing:
        print(f"✅ SQL Database already exists: {db_name}")
        return existing

    body = {
        "displayName": db_name,
        "description": "DriveThru drive-through ordering database",
    }
    resp = requests.post(
        f"{FABRIC_API}/workspaces/{workspace_id}/sqlDatabases",
        json=body,
        headers=api_headers(token),
        timeout=60,
    )

    if resp.status_code == 201:
        db = resp.json()
        print(f"✅ SQL Database created: {db_name}")
        return db

    if resp.status_code == 202:
        print(f"   SQL Database creation started (async)...")
        location = resp.headers.get("Location") or resp.headers.get("Operation-Location")
        if location:
            poll_operation(token, location)
        else:
            # No location header — wait and re-fetch
            print("   Waiting for provisioning...")
            time.sleep(30)

        db = find_sql_database(token, workspace_id, db_name)
        if db:
            print(f"✅ SQL Database created: {db_name}")
            return db
        raise RuntimeError("SQL Database not found after creation")

    resp.raise_for_status()
    return resp.json()


def get_sql_connection_string(token: str, workspace_id: str, db_name: str) -> str:
    """Get the SQL connection endpoint and build an ODBC connection string."""
    resp = requests.get(
        f"{FABRIC_API}/workspaces/{workspace_id}/sqlDatabases",
        headers=api_headers(token),
        timeout=30,
    )
    resp.raise_for_status()

    for db in resp.json().get("value", []):
        if db["displayName"] == db_name:
            props = db.get("properties", {})
            server = props.get("serverFqdn", "")
            database = props.get("databaseName", db_name)

            if not server:
                # Fallback: construct from workspace info
                print("⚠️  Could not auto-detect server FQDN from API response.")
                print("   Check the Fabric portal for the SQL connection endpoint.")
                return ""

            conn_str = (
                f"Driver={{ODBC Driver 18 for SQL Server}};"
                f"Server={server};"
                f"Database={database};"
                f"Encrypt=yes;"
                f"TrustServerCertificate=yes;"
                f"Authentication=ActiveDirectoryInteractive"
            )
            return conn_str

    return ""


# ── Schema execution ────────────────────────────────────────────────
def run_schema(connection_string: str, cred: AzureCliCredential | None = None) -> None:
    """Execute schema-setup.sql against the Fabric SQL Database."""
    if not SCHEMA_SQL.exists():
        print(f"⚠️  Schema file not found: {SCHEMA_SQL}")
        return

    sql_text = SCHEMA_SQL.read_text(encoding="utf-8")

    # Split on GO statements (batch separator)
    batches = [b.strip() for b in sql_text.split("\nGO\n") if b.strip()]
    # Also handle GO at end of file
    if sql_text.rstrip().endswith("GO"):
        last = batches[-1] if batches else ""
        if last.endswith("GO"):
            batches[-1] = last[:-2].strip()

    print(f"   Running schema ({len(batches)} batches)...")

    try:
        conn_params = {}
        if cred:
            try:
                # Use access token for database authentication to bypass interactive prompt in non-interactive terminals
                db_token = cred.get_token("https://database.windows.net/.default")
                import struct
                token_bytes = db_token.token.encode("utf-16le")
                # SQL_COPT_SS_ACCESS_TOKEN = 1256
                token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
                conn_params["attrs_before"] = {1256: token_struct}
                # Remove Authentication option from connection string to avoid conflicts
                connection_string = connection_string.replace(";Authentication=ActiveDirectoryInteractive", "")
            except Exception as token_err:
                print(f"   ⚠️  Could not acquire database access token: {token_err}. Falling back to interactive login.")

        conn = pyodbc.connect(connection_string, **conn_params)
        conn.autocommit = True
        cursor = conn.cursor()

        for i, batch in enumerate(batches, 1):
            if not batch:
                continue
            try:
                cursor.execute(batch)
                print(f"   ✅ Batch {i}/{len(batches)} executed")
            except pyodbc.Error as e:
                # Skip "already exists" errors for idempotency
                err_msg = str(e).lower()
                if "already exists" in err_msg or "there is already an object" in err_msg:
                    print(f"   ⏭️  Batch {i}/{len(batches)} skipped (already exists)")
                else:
                    print(f"   ❌ Batch {i}/{len(batches)} failed: {e}")

        cursor.close()
        conn.close()
        print("✅ Schema setup complete")

    except pyodbc.Error as e:
        print(f"❌ Database connection failed: {e}")
        print("   You can run the schema manually later:")
        print(f"   Schema file: {SCHEMA_SQL}")


# ── Demo Data Seeding ────────────────────────────────────────────────
def seed_database(conn_str: str) -> None:
    """Seed the database with demo data using src.fabric.seed_demo_data."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    try:
        from src.fabric.seed_demo_data import main as seed_main
        os.environ["FABRIC_CONNECTION_STRING"] = conn_str
        print("   🌱 Seeding database with demo data...")
        result = seed_main([])
        if result == 0:
            print("✅ Demo data seeding complete")
        else:
            print(f"⚠️  Demo data seeding exited with code {result}")
    except Exception as e:
        print(f"❌ Failed to seed demo data: {e}")


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Provision Microsoft Fabric workspace + SQL database for DriveThru demo"
    )
    parser.add_argument(
        "--skip-schema", action="store_true", help="Skip running schema-setup.sql"
    )
    parser.add_argument(
        "--seed-demo-data", action="store_true", help="Seed the database with demo data without prompting"
    )
    parser.add_argument(
        "--skip-seed", action="store_true", help="Skip seeding demo data without prompting"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show config and exit without making changes"
    )
    args = parser.parse_args()

    # Load .env from repo root
    load_dotenv(REPO_ROOT / ".env", override=True)

    workspace_name = os.getenv("FABRIC_WORKSPACE_NAME", "ws-drivethru-demo")
    capacity_id = os.getenv("FABRIC_CAPACITY_ID", "")
    db_name = os.getenv("FABRIC_DB_NAME", "DriveThru")

    print("=" * 60)
    print("  Fabric CI/CD Setup — DriveThru Demo")
    print("=" * 60)
    print(f"  Workspace : {workspace_name}")
    print(f"  Capacity  : {capacity_id or '(auto-detect trial)'}")
    print(f"  Database  : {db_name}")
    print(f"  Schema    : {SCHEMA_SQL}")
    print("=" * 60)

    if args.dry_run:
        print("\n🔍 Dry run — no changes will be made.")
        return

    # Step 1: Authenticate
    print("\n🔑 Step 1: Authenticating...")
    cred = AzureCliCredential()
    try:
        token = cred.get_token(FABRIC_SCOPE).token
        print("✅ Authenticated via Azure CLI")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        print("   Run 'az login' first, then retry.")
        sys.exit(1)

    # Step 2: Find capacity
    print("\n📦 Step 2: Finding capacity...")
    if not capacity_id:
        capacity_id = find_trial_capacity(token)
        if not capacity_id:
            print("❌ No active capacity found. Please set FABRIC_CAPACITY_ID in .env")
            sys.exit(1)
    else:
        print(f"✅ Using provided capacity: {capacity_id}")

    # Step 3: Create workspace
    print("\n🏗️  Step 3: Creating workspace...")
    workspace_id = create_workspace(token, workspace_name, capacity_id)

    # Step 4: Create SQL Database
    print("\n🗄️  Step 4: Creating SQL Database...")
    create_sql_database(token, workspace_id, db_name)

    # Step 5: Get connection string
    print("\n🔗 Step 5: Getting connection string...")
    conn_str = get_sql_connection_string(token, workspace_id, db_name)

    # Step 6: Run schema
    if not args.skip_schema and conn_str:
        print("\n📋 Step 6: Running schema setup...")
        run_schema(conn_str, cred)
    elif args.skip_schema:
        print("\n⏭️  Step 6: Schema setup skipped (--skip-schema)")
    else:
        print("\n⚠️  Step 6: Schema skipped — connection string unavailable")

    # Step 7: Seed demo data
    if conn_str:
        print("\n🌱 Step 7: Demo data seeding...")
        should_seed = False
        if args.seed_demo_data:
            should_seed = True
        elif args.skip_seed:
            print("   ⏭️  Seeding skipped (--skip-seed)")
        else:
            try:
                answer = input("   Do you want to seed the database with demo data? [y/N]: ").strip().lower()
                should_seed = answer in {"y", "yes"}
            except (EOFError, KeyboardInterrupt):
                print("\n   ⏭️  Seeding skipped (non-interactive session)")
                should_seed = False

        if should_seed:
            seed_database(conn_str)
        elif not args.skip_seed:
            print("   ⏭️  Seeding skipped by user choice")
    else:
        print("\n⚠️  Step 7: Seeding skipped — connection string unavailable")

    # Summary
    print("\n" + "=" * 60)
    print("  ✅ Fabric provisioning complete!")
    print("=" * 60)
    print(f"\n  Workspace ID : {workspace_id}")
    print(f"  Database     : {db_name}")
    if conn_str:
        print(f"\n  Add to your .env file:")
        print(f'  FABRIC_CONNECTION_STRING="{conn_str}"')
    else:
        print("\n  ⚠️  Connection string not available from API.")
        print("  Open the Fabric portal → SQL Database → Settings → Connection strings")
    print()


if __name__ == "__main__":
    main()
