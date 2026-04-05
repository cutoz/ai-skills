#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from google_sheets_skill.drafts import (
    clear_active_draft,
    create_draft,
    get_active_draft,
    remove_operations,
    save_active_draft,
)
from google_sheets_skill.formatting import operation_to_request, sheet_lookup
from google_sheets_skill.rich_text import apply_replace_chunks, chunks_payload, revision_hash
from google_sheets_skill.sheets import (
    build_sheets_service,
    get_single_cell_data,
    get_spreadsheet_metadata,
    parse_a1_cell,
    resolve_spreadsheet_target,
)


def active_target(args: argparse.Namespace) -> dict[str, Any]:
    return resolve_spreadsheet_target(args.spreadsheet) if getattr(args, "spreadsheet", None) else {}


def read_cell_state(service: Any, spreadsheet_id: str, tab: str, cell: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from google_sheets_skill.rich_text import grapheme_chunks

    sheet_props, cell_data = get_single_cell_data(service, spreadsheet_id, tab, cell)
    user_value = cell_data.get("userEnteredValue", {})
    if "formulaValue" in user_value:
        raise ValueError(f"{tab}!{cell} is a formula cell and cannot be edited with chunk operations.")
    text = user_value.get("stringValue", "")
    runs = cell_data.get("textFormatRuns", [])
    chunks = grapheme_chunks(text, runs)
    return sheet_props, {
        "tab": tab,
        "cell": cell,
        "text": text,
        "text_format_runs": runs,
        "revision": revision_hash(text, chunks),
        "chunks": chunks,
    }


def build_update_request(sheet_id: int, cell: str, text: str, runs: list[dict[str, Any]]) -> dict[str, Any]:
    row_index, column_index = parse_a1_cell(cell)
    return {
        "updateCells": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": row_index,
                "endRowIndex": row_index + 1,
                "startColumnIndex": column_index,
                "endColumnIndex": column_index + 1,
            },
            "rows": [{"values": [{"userEnteredValue": {"stringValue": text}, "textFormatRuns": runs}]}],
            "fields": "userEnteredValue,textFormatRuns",
        }
    }


def validate_content_operation(service: Any, spreadsheet_id: str, operation: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
    payload = operation["operation"]
    tab = payload["tab"]
    cell = payload["cell"]
    sheet_props, before = read_cell_state(service, spreadsheet_id, tab, cell)
    if before["revision"] != payload["expected_revision"]:
        return (
            {
                "key": operation["key"],
                "kind": "content",
                "tab": tab,
                "cell": cell,
                "status": "conflict",
                "message": "Revision mismatch. Re-inspect and restage.",
                "expected_revision": payload["expected_revision"],
                "actual_revision": before["revision"],
            },
            None,
            operation["key"],
        )

    rebuilt_text, rebuilt_runs, rebuilt_chunks, changed_chunk_ids = apply_replace_chunks(
        text=before["text"],
        text_format_runs=before["text_format_runs"],
        chunk_ids=payload["chunk_ids"],
        replacement_chunks=payload["replacement_chunks"],
    )
    preview = {
        "key": operation["key"],
        "kind": "content",
        "tab": tab,
        "cell": cell,
        "status": "valid",
        "changed_chunk_ids": changed_chunk_ids,
        "before_text": before["text"],
        "after_text": rebuilt_text,
        "before_chunks": chunks_payload(before["chunks"]),
        "after_chunks": chunks_payload(rebuilt_chunks),
    }
    request = build_update_request(sheet_props["sheetId"], cell, rebuilt_text, rebuilt_runs)
    return preview, request, None


def validate_format_operation(service: Any, spreadsheet_id: str, operation: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
    metadata = get_spreadsheet_metadata(service, spreadsheet_id)
    sheets_by_title = sheet_lookup(metadata)
    try:
        request = operation_to_request(sheets_by_title, operation["operation"])
    except ValueError as exc:
        return (
            {
                "key": operation["key"],
                "kind": "format",
                "status": "conflict",
                "message": str(exc),
            },
            None,
            operation["key"],
        )

    return (
        {
            "key": operation["key"],
            "kind": "format",
            "status": "valid",
            "summary": operation.get("summary", {}),
        },
        request,
        None,
    )


def validate_operations(service: Any, draft: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[tuple[str, dict[str, Any]]]]:
    valid_previews: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    requests: list[tuple[str, dict[str, Any]]] = []
    for operation in draft["operations"]:
        if operation["kind"] == "content":
            preview, request, conflict_key = validate_content_operation(service, draft["spreadsheet_id"], operation)
        else:
            preview, request, conflict_key = validate_format_operation(service, draft["spreadsheet_id"], operation)
        if conflict_key:
            conflicts.append(preview)
        else:
            valid_previews.append(preview)
            if request:
                requests.append((operation["key"], request))
    return valid_previews, conflicts, requests


def create_command(args: argparse.Namespace) -> None:
    target = active_target(args)
    draft = create_draft(args.name, target["spreadsheet_id"], args.tab or target.get("tab"))
    print(json.dumps(draft, indent=2))


def status_command(_: argparse.Namespace) -> None:
    draft = get_active_draft(required=False)
    if not draft:
        print(json.dumps({"active_draft": None}, indent=2))
        return
    print(
        json.dumps(
            {
                "active_draft_id": draft["id"],
                "name": draft["name"],
                "spreadsheet_id": draft["spreadsheet_id"],
                "tab": draft.get("tab"),
                "operation_count": len(draft["operations"]),
                "updated_at": draft["updated_at"],
            },
            indent=2,
        )
    )


def show_command(_: argparse.Namespace) -> None:
    draft = get_active_draft(required=True)
    print(
        json.dumps(
            {
                "id": draft["id"],
                "name": draft["name"],
                "spreadsheet_id": draft["spreadsheet_id"],
                "tab": draft.get("tab"),
                "operation_count": len(draft["operations"]),
                "operations": draft["operations"],
            },
            indent=2,
        )
    )


def clear_command(_: argparse.Namespace) -> None:
    draft = clear_active_draft()
    print(json.dumps({"cleared": True, "draft_id": draft["id"]}, indent=2))


def commit_command(args: argparse.Namespace) -> None:
    draft = get_active_draft(required=True)
    service = build_sheets_service()
    valid_previews, conflicts, requests = validate_operations(service, draft)
    preview = {
        "draft_id": draft["id"],
        "valid_operation_count": len(valid_previews),
        "conflict_count": len(conflicts),
        "valid_operations": valid_previews,
        "conflicts": conflicts,
    }

    if conflicts and not args.apply_valid:
        print(json.dumps(preview, indent=2))
        return

    if not args.apply and not args.apply_valid:
        print(json.dumps(preview, indent=2))
        return

    if not requests:
        print(json.dumps({**preview, "applied": False, "message": "No valid operations to apply."}, indent=2))
        return

    response = (
        service.spreadsheets()
        .batchUpdate(
            spreadsheetId=draft["spreadsheet_id"],
            body={"requests": [request for _, request in requests], "includeSpreadsheetInResponse": False},
        )
        .execute()
    )
    remove_operations(draft, {key for key, _ in requests})
    save_active_draft(draft)
    print(
        json.dumps(
            {
                **preview,
                "applied": True,
                "applied_count": len(requests),
                "remaining_operation_count": len(draft["operations"]),
                "response": response,
            },
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage local Google Sheets drafts and commit staged changes.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create and select a new active draft.")
    create.add_argument("--spreadsheet", required=True, help="Spreadsheet URL, ID, or saved alias.")
    create.add_argument("--name", required=True, help="Draft name.")
    create.add_argument("--tab", help="Optional default tab context.")
    create.set_defaults(handler=create_command)

    status = subparsers.add_parser("status", help="Show active draft status.")
    status.set_defaults(handler=status_command)

    show = subparsers.add_parser("show", help="Show active draft contents.")
    show.set_defaults(handler=show_command)

    clear = subparsers.add_parser("clear", help="Discard the active draft.")
    clear.set_defaults(handler=clear_command)

    commit = subparsers.add_parser("commit", help="Validate and optionally apply the active draft.")
    commit.add_argument("--apply", action="store_true", help="Apply all staged operations only if there are no conflicts.")
    commit.add_argument("--apply-valid", action="store_true", help="Apply only valid operations and keep conflicts staged.")
    commit.set_defaults(handler=commit_command)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
