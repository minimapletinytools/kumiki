.PHONY: help setup test test-verbose test-cov typecheck typecheck-watch clean profile stepout

help:
	@echo "🦒 Kumiki Development Commands"
	@echo "=================================="
	@echo ""
	@echo "  make setup           - Setup development environment (create venv and install deps with uv)"
	@echo "  make test            - Run all tests"
	@echo "  make test-verbose    - Run tests with verbose output"
	@echo "  make test-cov        - Run tests with coverage report"
	@echo "  make typecheck       - Run type checking with ty"
	@echo "  make typecheck-watch - Run type checking in watch mode"
	@echo "  make clean           - Remove build artifacts and cache files"
	@echo "  make profile         - Profile all patterns (or PATTERNS='oscarshed kumiki')"
	@echo "  make stepout         - Export STEP files (or PATTERN=kumiki)"
	@echo ""

setup:
	uv sync

test:
	uv run pytest tests/

test-verbose:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ --cov=kumiki --cov-report=html --cov-report=term-missing
	@echo ""
	@echo "✅ Coverage report generated in htmlcov/index.html"

typecheck:
	uv run ty check
	@echo ""
	@echo "✅ Type checking complete"

typecheck-watch:
	uv run ty check --watch

profile:
	uv run python tools/test_profiling.py $(PATTERNS)

stepout:
	uv run python tools/test_step_output.py $(PATTERN)

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage
	@echo "✅ Clean complete"

