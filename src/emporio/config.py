"""Configuration read from environment (optionally a local .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader: KEY=VALUE lines, '#' comments. Never overwrites preset vars."""
    path = path or REPO_ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str
    model: str
    temperature: float
    max_tool_rounds: int
    db_path: Path
    data_dir: Path

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is not set. Copy .env.example to .env and fill it in, or export it."
            )
        return cls(
            api_key=key,
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            model=os.environ.get("MODEL", "deepseek-chat"),
            temperature=float(os.environ.get("TEMPERATURE", "0.3")),
            max_tool_rounds=int(os.environ.get("MAX_TOOL_ROUNDS", "6")),
            db_path=Path(os.environ.get("EMPORIO_DB", REPO_ROOT / "emporio.sqlite")),
            data_dir=Path(os.environ.get("EMPORIO_DATA", REPO_ROOT / "data")),
        )
