#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from google_sheets_skill.drafts import add_or_replace_operation, get_active_draft, save_active_draft
from google_sheets_skill.rich_text import (
    apply_replace_chunks,
    chunks_payload,
    parse_single_cell_grid_range,
    revision_hash,
)
from google_sheets_skill.sheets import (
    build_sheets_service,
    get_single_cell_data,
    load_payload,
    resolve_spreadsheet_target,
)


def read_cell_state(service: Any, spreadsheet_id: str, tab: str, cell: str) -> tuple[dict[str, Any], dict[str, Any]]:
    sheet_props, cell_data = get_single_cell_data(service, spreadsheet_id, tab, cell)
    user_value = cell_data.get("userEnteredValue", {})
    if "formulaValue" in user_value:
        raise ValueError(f"{tab}!{cell} is a formula cell and cannot be edited with chunk operations.")
    text = user_value.get("stringValue", "")
    runs = cell_data.get("textFormatRuns", [])
    from google_sheets_skill.rich_text import grapheme_chunks

    chunks = grapheme_chunks(text, runs)
    return sheet_props, {
        "tab": tab,
        "cell": cell,
        "text": text,
        "text_format_runs": runs,
        "revision": revision_hash(text, chunks),
        "chunk_count": len(chunks),
        "chunks": chunks_payload(chunks),
        "user_entered_format": cell_data.get("userEnteredFormat", {}),
        "note": cell_data.get("note"),
    }


def build_update_request(sheet_id: int, cell: str, text: str, runs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "updateCells": {
            "range": parse_single_cell_grid_range(sheet_id, cell),
            "rows": [
                {
                    "values": [
                        {
                            "userEnteredValue": {"stringValue": text},
                            "textFormatRuns": runs,
                        }
                    ]
                }
            ],
            "fields": "userEnteredValue,textFormatRuns",
        }
    }


def validate_operation_shape(operation: dict[str, Any]) -> None:
    if "range" in operation or "values" in operation:
        raise ValueError(
            "Legacy range/value payloads are no longer supported. "
            "Use per-cell replace_chunks operations with chunk IDs."
        )
    if operation.get("action") != "replace_chunks":
        raise ValueError("change_bulk_cell.py currently supports only action=replace_chunks")
    if not operation.get("cell"):
        raise ValueError("Each operation requires a cell")
    if not operation.get("chunk_ids"):
        raise ValueError("Each replace_chunks operation requires chunk_ids")
    if not operation.get("replacement_chunks"):
        raise ValueError("Each replace_chunks operation requires replacement_chunks")


def process_operation(service: Any, spreadsheet_id: str, operation: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    validate_operation_shape(operation)
    tab = operation.get("tab")
    if not tab:
        raise ValueError("Each operation requires a tab")

    sheet_props, before = read_cell_state(service, spreadsheet_id, tab, operation["cell"])
    if before["text"] == "":
        raise ValueError(
            f"{tab}!{operation['cell']} is empty. Use write_sheet.py for empty-cell fills."
        )

    expected_revision = operation.get("expected_revision")
    if expected_revision and expected_revision != before["revision"]:
        raise ValueError(
            f"Revision mismatch for {tab}!{operation['cell']}. Re-run inspect and retry with fresh chunk IDs."
        )

    rebuilt_text, rebuilt_runs, rebuilt_chunks, changed_chunk_ids = apply_replace_chunks(
        text=before["text"],
        text_format_runs=before["text_format_runs"],
        chunk_ids=operation["chunk_ids"],
        replacement_chunks=operation["replacement_chunks"],
    )

    after = {
        "text": rebuilt_text,
        "text_format_runs": rebuilt_runs,
        "revision": revision_hash(rebuilt_text, rebuilt_chunks),
        "chunk_count": len(rebuilt_chunks),
        "chunks": chunks_payload(rebuilt_chunks),
    }
    request = build_update_request(sheet_props["sheetId"], operation["cell"], rebuilt_text, rebuilt_runs)
    preview = {
        "tab": tab,
        "cell": operation["cell"],
        "action": operation["action"],
        "changed_chunk_ids": changed_chunk_ids,
        "before": before,
        "after": after,
        "formatting_changed_explicitly": any("format" in chunk for chunk in operation["replacement_chunks"]),
        "request": request,
    }

    if before["text"] == rebuilt_text and before["text_format_runs"] == rebuilt_runs:
        return preview, None
    return preview, request


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preview or apply chunk-based rich-text edits across multiple existing Google Sheets cells."
    )
    parser.add_argument("--spreadsheet", required=True, help="Spreadsheet URL, ID, or saved alias.")
    parser.add_argument("--input", help="Path to a JSON payload file.")
    parser.add_argument("--json", help="Inline JSON payload.")
    parser.add_argument("--apply", action="store_true", help="Apply the changes. Without this flag the command only previews.")
    parser.add_argument("--stage", action="store_true", help="Stage the operations into the active draft instead of applying immediately.")
    args = parser.parse_args()

    payload = load_payload(args.input, args.json)
    target = resolve_spreadsheet_target(args.spreadsheet)
    service = build_sheets_service()

    preview_operations: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []

    try:
        for operation in payload["operations"]:
            preview, request = process_operation(service, target["spreadsheet_id"], operation)
            preview_operations.append(preview)
            if request:
                requests.append(request)
    except ValueError as exc:
        print(
            json.dumps(
                {
                    "error": "bulk_chunk_edit_blocked",
                    "message": str(exc),
                },
                indent=2,
            )
        )
        sys.exit(1)

    preview_payload = {
        "spreadsheet_id": target["spreadsheet_id"],
        "operation_count": len(preview_operations),
        "apply_required": True,
        "operations": preview_operations,
    }

    if args.stage:
        draft = get_active_draft(required=True)
        if draft["spreadsheet_id"] != target["spreadsheet_id"]:
            raise SystemExit("Active draft targets a different spreadsheet.")
        for operation, preview in zip(payload["operations"], preview_operations):
            staged_operation = {
                "key": f"content:{operation['tab']}:{operation['cell']}",
                "kind": "content",
                "spreadsheet_id": target["spreadsheet_id"],
                "operation": operation,
                "summary": {
                    "tab": operation["tab"],
                    "cell": operation["cell"],
                    "changed_chunk_ids": preview["changed_chunk_ids"],
                    "before_text": preview["before"]["text"],
                    "after_text": preview["after"]["text"],
                    "revision": operation.get("expected_revision"),
                },
            }
            add_or_replace_operation(draft, staged_operation)
        save_active_draft(draft)
        print(json.dumps({**preview_payload, "staged": True, "draft_id": draft["id"]}, indent=2))
        return

    if not args.apply:
        print(json.dumps(preview_payload, indent=2))
        return

    if not requests:
        print(json.dumps({**preview_payload, "applied": False, "message": "No-op edit batch."}, indent=2))
        return

    response = (
        service.spreadsheets()
        .batchUpdate(
            spreadsheetId=target["spreadsheet_id"],
            body={"requests": requests, "includeSpreadsheetInResponse": False},
        )
        .execute()
    )
    print(json.dumps({**preview_payload, "applied": True, "response": response}, indent=2))


if __name__ == "__main__":
    main()
