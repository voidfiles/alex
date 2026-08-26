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

# Live end-to-end vault retrieval and collision run. Requires OPENROUTER_API_KEY
# and OPENAI_API_KEY, rebuilds the disposable cache, and makes provider calls.
# It is intentionally separate from `just test`.
brain-e2e VAULT QUESTION:
    uv run alex brain index "{{VAULT}}" --embedding-model voyageai/voyage-4 --rebuild
    uv run alex brain status "{{VAULT}}" --embedding-model voyageai/voyage-4 --json
    uv run alex lsd "{{QUESTION}}" --vault "{{VAULT}}" --limit 1 --embedding-model voyageai/voyage-4 --model openai/gpt-5.6-terra --judge-model openai/gpt-5.6-terra --json

brain-e2e-example:
    just brain-e2e \
        /Users/alex/Dropbox/obsidian/Alex3/projects \
        'How can a leader maintain team performance during organizational chaos?'

brain-index:
    uv run alex brain index "/Users/alex/Dropbox/obsidian/Alex3/" --embedding-model voyageai/voyage-4 --rebuild
    uv run alex brain status "/Users/alex/Dropbox/obsidian/Alex3/" --embedding-model voyageai/voyage-4 --json

brain-query VAULT QUESTION:
    uv run alex brain index "{{VAULT}}" --embedding-model voyageai/voyage-4 --defer-embeddings
    uv run alex lsd "{{QUESTION}}" --vault "{{VAULT}}" --limit 1 --embedding-model voyageai/voyage-4 --model openai/gpt-5.6-terra --judge-model openai/gpt-5.6-terra --json

brain-query-example:
    just brain-query \
        /Users/alex/Dropbox/obsidian/Alex3/ \
        'How can a leader maintain team performance during organizational chaos?'
