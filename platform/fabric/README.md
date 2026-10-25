# Fabric CI/CD Setup

Automates Microsoft Fabric provisioning for the DriveThru demo.

## What it does

1. **Authenticates** via Azure CLI (`az login`)
2. **Finds trial capacity** (or uses `FABRIC_CAPACITY_ID` from `.env`)
3. **Creates workspace** with capacity assignment
4. **Creates Fabric SQL Database**
5. **Runs schema** from `src/fabric/schema-setup.sql`
6. **Outputs** `FABRIC_CONNECTION_STRING` to paste into `.env`

## Prerequisites

- Python 3.13+ with project dependencies installed (`uv pip install -e .`)
- Azure CLI logged in: `az login`
- A Fabric capacity (trial is auto-detected, or set `FABRIC_CAPACITY_ID`)
- ODBC Driver 18 for SQL Server installed

## Usage

```powershell
# 1. Login to Azure
az login

# 2. (Optional) Configure in .env
#    FABRIC_WORKSPACE_NAME="ws-drivethru-demo"
#    FABRIC_CAPACITY_ID=""          # leave empty for trial auto-detect
#    FABRIC_DB_NAME="DriveThru"

# 3. Run the setup script
python platform/fabric/setup_fabric.py

# 4. Copy the output FABRIC_CONNECTION_STRING into your .env file
```

### CLI options

| Flag | Description |
|------|-------------|
| `--skip-schema` | Skip running `schema-setup.sql` |
| `--dry-run` | Show configuration and exit without making changes |
| `-h`, `--help` | Show help |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FABRIC_WORKSPACE_NAME` | `ws-drivethru-demo` | Workspace display name |
| `FABRIC_CAPACITY_ID` | *(auto-detect)* | Capacity GUID; leave empty to find trial |
| `FABRIC_DB_NAME` | `DriveThru` | SQL database display name |

## Idempotency

The script is safe to re-run:
- Skips workspace/database creation if they already exist
- Skips schema objects that already exist (catches "already exists" errors)

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Authentication failed` | Run `az login` first |
| `No active capacity found` | Start a Fabric trial or set `FABRIC_CAPACITY_ID` |
| `ODBC Driver 18 not found` | Install from [Microsoft ODBC Driver](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server) |
| `Connection string unavailable` | Check Fabric portal → SQL Database → Settings |
