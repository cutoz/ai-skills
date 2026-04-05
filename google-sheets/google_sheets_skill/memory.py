from __future__ import annotations

from typing import Any

from .paths import MEMORY_PATH, load_json, save_json


DEFAULT_MEMORY: dict[str, Any] = {
    "aliases": {},
    "sheet_notes": {},
    "conversation_context": {},
}


def load_memory() -> dict[str, Any]:
    memory = DEFAULT_MEMORY.copy()
    raw = load_json(MEMORY_PATH, DEFAULT_MEMORY)
    memory["aliases"] = raw.get("aliases", {})
    memory["sheet_notes"] = raw.get("sheet_notes", {})
    memory["conversation_context"] = raw.get("conversation_context", {})
    return memory


def save_memory(memory: dict[str, Any]) -> None:
    save_json(MEMORY_PATH, memory)


def alias_key(name: str) -> str:
    return name.strip().lower()


def set_alias(name: str, target: dict[str, Any]) -> dict[str, Any]:
    memory = load_memory()
    stored_target = target.copy()
    stored_target["alias_name"] = name
    memory["aliases"][alias_key(name)] = stored_target
    save_memory(memory)
    return stored_target


def resolve_alias(name: str) -> dict[str, Any] | None:
    memory = load_memory()
    return memory["aliases"].get(alias_key(name))


def set_sheet_note(spreadsheet_id: str, note: str) -> None:
    memory = load_memory()
    memory["sheet_notes"][spreadsheet_id] = note
    save_memory(memory)


def save_context(name: str, context: dict[str, Any]) -> None:
    memory = load_memory()
    memory["conversation_context"][name] = context
    save_memory(memory)
