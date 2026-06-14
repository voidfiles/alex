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

# Summary-quality evals; makes real LLM calls, never runs in CI.
# Cheaper iteration: ALEX_FINAL_SUMMARY_MODEL=anthropic/claude-sonnet-4-6 just eval
eval *ARGS:
    uv run alex eval-summary {{ARGS}}
