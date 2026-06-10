default: check

# Run lint, typecheck, and tests — same as CI.
check: lint typecheck test

test *ARGS:
    uv run pytest {{ARGS}}

lint:
    uv run ruff check
    uv run ruff format --check

typecheck:
    uv run mypy

fmt:
    uv run ruff format
    uv run ruff check --fix
