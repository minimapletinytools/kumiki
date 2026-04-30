## Quick Start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Setup (creates .venv, installs everything)
make setup

# Run tests
make test

# Run type checker
make typecheck
```

## Development Setup

The `make setup` command runs `uv sync`, which automatically manages your virtual environment (`.venv`), Python version, and project dependencies.

### Note on CAD Integrations

CAD applications ship with their own Python environments use their own Python environments. This is why dependencies are also vendored in `fusion360/libs/` for CAD environments. The venv setup does not affect CAD integrations. FreeCAD does not seem to require this.

## Running Tests

To run the test suite manually with `uv`:

```bash
# Run all tests
uv run pytest tests/

# Run tests with verbose output
uv run pytest tests/ -v

# Run a specific test file
uv run pytest tests/test_rule.py -v

# Run with coverage (or use make test-cov)
uv run pytest tests/ --cov=kumiki --cov-report=html
```

Tests flagged with # 🐪 have been hand reviewed, the rest are AI slop

## Type Checking

This project uses [ty](https://docs.astral.sh/ty/), an extremely fast Python type checker written in Rust by Astral (the creators of Ruff). ty is 10x-100x faster than traditional type checkers like mypy and Pyright.

`ty` is automatically installed as a development dependency when you run `make setup`.

### Running Type Checking

Use these `make` commands:

```bash
make typecheck        # Run type checking on all files
make typecheck-watch  # Run type checking in watch mode (auto-checks on file changes)
```

or manually via `uv`:

```bash
# Run ty
uv run ty check

# Check specific files or directories
uv run ty check kumiki/timber.py
uv run ty check kumiki/

# Watch mode - automatically re-checks when files change
uv run ty check --watch
```

### Cleaning Build Artifacts

To clean up Python cache files and test artifacts:

```bash
make clean

# Or manually:
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
rm -rf htmlcov/ .coverage .pytest_cache/
```
