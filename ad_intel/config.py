"""Paths, settings and API clients. Keys come from .env, never from code."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPORTS = ROOT / "reports"

LABEL_MODEL = "claude-haiku-5-5"    # cheap, high-volume labeling
REPORT_MODEL = "claude-sonnet-5-5"  # analysis and final report


def load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if value.strip():
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def load_niches() -> dict:
    return json.loads((ROOT / "niches.json").read_text(encoding="utf-8"))


def anthropic_client():
    import anthropic

    load_env()
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY is missing. Copy .env.example to .env and add your key.")
    # Pin the public endpoint so a proxy URL left in the shell does not hijack the run.
    return anthropic.Anthropic(api_key=key, base_url="https://api.anthropic.com", max_retries=4)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
