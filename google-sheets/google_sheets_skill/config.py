from __future__ import annotations

from pathlib import Path
from typing import Any

from .paths import CONFIG_PATH, STATE_DIR, load_json, save_json


DEFAULT_CONFIG: dict[str, Any] = {
    "client_secret_path": None,
    "token_path": str(STATE_DIR / "token.json"),
    "scopes": ["https://www.googleapis.com/auth/spreadsheets"],
    "default_account_label": None,
}


def load_config() -> dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    config.update(load_json(CONFIG_PATH, DEFAULT_CONFIG))
    return config


def save_config(config: dict[str, Any]) -> None:
    save_json(CONFIG_PATH, config)


def token_path(config: dict[str, Any]) -> Path:
    return Path(config["token_path"]).expanduser()
