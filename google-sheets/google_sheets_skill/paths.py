from __future__ import annotations

import json
from pathlib import Path
from typing import Any


STATE_DIR = Path.home() / ".codex" / "google-sheets"
CONFIG_PATH = STATE_DIR / "config.json"
MEMORY_PATH = STATE_DIR / "memory.json"
DRAFTS_PATH = STATE_DIR / "drafts.json"


def ensure_state_dir() -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default.copy()
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_state_dir()
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
