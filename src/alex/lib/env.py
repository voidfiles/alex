import os
from collections.abc import MutableMapping
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[3]
SOURCE_DOTENV_PATH = SOURCE_ROOT / ".env"


def load_source_dotenv(
    dotenv_path: Path = SOURCE_DOTENV_PATH,
    environ: MutableMapping[str, str] | None = None,
) -> None:
    if not dotenv_path.exists():
        return

    target_environ = os.environ if environ is None else environ

    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        parsed = parse_dotenv_line(line)
        if parsed is None:
            continue

        key, value = parsed
        if key not in target_environ:
            target_environ[key] = value


def parse_dotenv_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None

    if stripped.startswith("export "):
        stripped = stripped.removeprefix("export ").lstrip()

    key, value = stripped.split("=", 1)
    key = key.strip()
    if not key:
        return None

    return key, strip_dotenv_quotes(value.strip())


def strip_dotenv_quotes(value: str) -> str:
    if len(value) < 2:
        return value

    quote = value[0]
    if quote not in {"'", '"'} or value[-1] != quote:
        return value

    return value[1:-1]
