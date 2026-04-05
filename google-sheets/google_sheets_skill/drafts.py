from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .paths import DRAFTS_PATH, load_json, save_json


DEFAULT_DRAFTS: dict[str, Any] = {
    "active_draft_id": None,
    "drafts": {},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_drafts() -> dict[str, Any]:
    drafts = DEFAULT_DRAFTS.copy()
    raw = load_json(DRAFTS_PATH, DEFAULT_DRAFTS)
    drafts["active_draft_id"] = raw.get("active_draft_id")
    drafts["drafts"] = raw.get("drafts", {})
    return drafts


def save_drafts(payload: dict[str, Any]) -> None:
    save_json(DRAFTS_PATH, payload)


def create_draft(name: str, spreadsheet_id: str, tab: str | None = None) -> dict[str, Any]:
    payload = load_drafts()
    draft_id = f"draft-{uuid4().hex[:10]}"
    draft = {
        "id": draft_id,
        "name": name,
        "spreadsheet_id": spreadsheet_id,
        "tab": tab,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "operations": [],
    }
    payload["drafts"][draft_id] = draft
    payload["active_draft_id"] = draft_id
    save_drafts(payload)
    return draft


def get_active_draft(required: bool = True) -> dict[str, Any] | None:
    payload = load_drafts()
    active_id = payload.get("active_draft_id")
    if not active_id:
        if required:
            raise ValueError("No active draft. Create one first with draft.py create.")
        return None
    draft = payload["drafts"].get(active_id)
    if not draft and required:
        raise ValueError("Active draft not found. Create a new draft.")
    return draft


def save_active_draft(draft: dict[str, Any]) -> dict[str, Any]:
    payload = load_drafts()
    active_id = payload.get("active_draft_id")
    if not active_id or active_id != draft["id"]:
        raise ValueError("Active draft changed. Reload and retry.")
    draft["updated_at"] = utc_now()
    payload["drafts"][draft["id"]] = draft
    save_drafts(payload)
    return draft


def clear_active_draft() -> dict[str, Any]:
    payload = load_drafts()
    active_id = payload.get("active_draft_id")
    if not active_id:
        raise ValueError("No active draft to clear.")
    draft = payload["drafts"].pop(active_id, None)
    payload["active_draft_id"] = None
    save_drafts(payload)
    if not draft:
        raise ValueError("Active draft not found.")
    return draft


def add_or_replace_operation(draft: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    key = operation["key"]
    remaining = [item for item in draft["operations"] if item["key"] != key]
    remaining.append(operation)
    draft["operations"] = remaining
    return draft


def remove_operations(draft: dict[str, Any], keys: set[str]) -> dict[str, Any]:
    draft["operations"] = [item for item in draft["operations"] if item["key"] not in keys]
    return draft
