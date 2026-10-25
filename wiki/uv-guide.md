# Using UV for Python Package Management

This project uses **uv** - an ultra-fast Python package installer and resolver written in Rust.

## Why uv?

- ⚡ **10-100x faster** than pip
- 🎯 **Better dependency resolution** - resolves conflicts more reliably
- 🔒 **Lockfile support** - reproducible builds
- 🚀 **Written in Rust** - blazing fast performance
- 🔄 **Drop-in pip replacement** - familiar commands

## Installation

### Windows (PowerShell)
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Alternative: Install via pip
```powershell
pip install uv
```

### Verify Installation
```powershell
uv --version
```

## Common Commands

### Virtual Environment Management

```powershell
# Create virtual environment (one-time)
uv venv

# Activate virtual environment
.venv\Scripts\Activate.ps1

# Create with specific Python version
uv venv --python 3.13
```

### Package Installation

```powershell
# Install all project dependencies
uv pip install -e .

# Install with dev dependencies
uv pip install -e ".[dev]"

# Install specific package
uv pip install azure-ai-projects

# Install multiple packages
uv pip install azure-identity pyodbc jupyter

# Install from requirements
uv pip install -r requirements.txt
```

### Package Management

```powershell
# List installed packages
uv pip list

# Show package info
uv pip show azure-ai-projects

# Upgrade a package
uv pip install --upgrade azure-identity

# Uninstall a package
uv pip uninstall package-name

# Generate lockfile (for reproducibility)
uv pip compile pyproject.toml -o requirements.txt
```

### Sync Dependencies

```powershell
# Sync environment with pyproject.toml
uv pip sync requirements.txt
```

## Comparison with pip

### Speed Comparison (typical)

| Operation | pip | uv | Speedup |
|-----------|-----|-----|---------|
| Install Django | ~5s | ~0.2s | 25x |
| Install pandas | ~8s | ~0.3s | 27x |
| Resolve conflicts | ~30s | ~1s | 30x |

### Command Mapping

| pip command | uv equivalent |
|------------|---------------|
| `pip install package` | `uv pip install package` |
| `pip install -e .` | `uv pip install -e .` |
| `pip list` | `uv pip list` |
| `pip freeze` | `uv pip freeze` |
| `pip uninstall` | `uv pip uninstall` |

## Project Workflow

### First-Time Setup

```powershell
# 1. Clone repository
git clone <repo-url>
cd voiceliveapi-drivethru-agent-demo

# 2. Install uv
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 3. Create virtual environment
uv venv

# 4. Activate
.venv\Scripts\Activate.ps1

# 5. Install dependencies
uv pip install -e .
```

### Daily Development

```powershell
# Activate environment
.venv\Scripts\Activate.ps1

# Add new package
uv pip install new-package

# Update pyproject.toml
# (manually add to dependencies list)

# Reinstall to sync
uv pip install -e .
```

### Adding Dependencies

When you need a new package:

1. Install it with uv:
```powershell
uv pip install azure-some-package
```

2. Add to `pyproject.toml`:
```toml
[project]
dependencies = [
    "azure-some-package>=1.0.0",
    # ... other packages
]
```

3. Reinstall in editable mode:
```powershell
uv pip install -e .
```

## Troubleshooting

### uv command not found
- Restart your terminal after installation
- Check PATH: `$env:PATH` should include uv location
- Reinstall: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`

### Virtual environment won't activate
- Ensure you created it first: `uv venv`
- Check execution policy: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
- Try from PowerShell (not Command Prompt)

### Package installation fails
- Check internet connection
- Try with verbose output: `uv pip install -v package-name`
- Check Python version: `python --version` (should be 3.13+)

### Dependency conflicts
- uv has better conflict resolution than pip
- If still issues, try: `uv pip install --force-reinstall package-name`

## Advanced Usage

### Creating Lockfiles

For reproducible environments:

```powershell
# Generate lockfile
uv pip compile pyproject.toml -o requirements.lock

# Install from lockfile
uv pip sync requirements.lock
```

### Working with Multiple Projects

```powershell
# Create project-specific virtual environment
uv venv --python 3.13 --name myproject-env

# Activate specific environment
.\myproject-env\Scripts\Activate.ps1
```

### Cache Management

```powershell
# Check cache size
uv cache info

# Clear cache if needed
uv cache clean
```

## uv vs Traditional pip

### Benefits
- ✅ Much faster installation
- ✅ Better dependency resolution
- ✅ More reliable builds
- ✅ Modern Rust implementation
- ✅ Active development

### Considerations
- ⚠️ Relatively new (but stable)
- ⚠️ Some advanced pip features still being added
- ✅ Compatible with pip and pyproject.toml

## Resources

- [uv Documentation](https://github.com/astral-sh/uv)
- [Installation Guide](https://astral.sh/uv)
- [GitHub Repository](https://github.com/astral-sh/uv)

## Configuration in This Project

This project is configured to use uv in:
- [pyproject.toml](../pyproject.toml) — Project dependencies and tool configurations
- [README.md](../README.md) — Setup instructions and full stack run commands
- [agent-workflow.md](./agent-workflow.md) — Daily development cycle and environment management

---

**Pro Tip**: Once you try uv, you won't want to go back to regular pip! 🚀
