#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import Any

from google_sheets_skill.drafts import add_or_replace_operation, get_active_draft, save_active_draft
from google_sheets_skill.rich_text import (
    apply_replace_chunks,
    grapheme_chunks,
    chunks_payload,
    parse_single_cell_grid_range,
    revision_hash,
)
from google_sheets_skill.sheets import (
    build_sheets_service,
    get_single_cell_data,
    resolve_spreadsheet_target,
)


def read_cell_payload(service: Any, spreadsheet_id: str, tab: str, cell: str) -> tuple[dict[str, Any], dict[str, Any]]:
    sheet_props, cell_data = get_single_cell_data(service, spreadsheet_id, tab, cell)
    user_value = cell_data.get("userEnteredValue", {})
    if "formulaValue" in user_value:
        raise SystemExit("Rich text editing does not support formula cells.")
    text = user_value.get("stringValue", "")
    runs = cell_data.get("textFormatRuns", [])
    chunks = grapheme_chunks(text, runs)
    payload = {
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
    return sheet_props, payload


def inspect_command(args: argparse.Namespace) -> None:
    target = resolve_spreadsheet_target(args.spreadsheet)
    tab = args.tab or target.get("tab")
    if not tab:
        raise SystemExit("A tab is required for rich text cell inspection.")
    service = build_sheets_service()
    _, payload = read_cell_payload(service, target["spreadsheet_id"], tab, args.cell)
    print(json.dumps(payload, indent=2))


def replace_chunks_command(args: argparse.Namespace) -> None:
    target = resolve_spreadsheet_target(args.spreadsheet)
    tab = args.tab or target.get("tab")
    if not tab:
        raise SystemExit("A tab is required for rich text cell edits.")

    service = build_sheets_service()
    sheet_props, payload = read_cell_payload(service, target["spreadsheet_id"], tab, args.cell)
    if args.expected_revision and args.expected_revision != payload["revision"]:
        raise SystemExit(
            json.dumps(
                {
                    "error": "stale_revision",
                    "message": "Cell content changed since inspect. Re-run inspect and retry with fresh chunk IDs.",
                    "expected_revision": args.expected_revision,
                    "actual_revision": payload["revision"],
                },
                indent=2,
            )
        )

    replacement_chunks = load_replacement_chunks(args)
    rebuilt_text, rebuilt_runs, rebuilt_chunks, changed_chunk_ids = apply_replace_chunks(
        text=payload["text"],
        text_format_runs=payload["text_format_runs"],
        chunk_ids=args.chunk_ids,
        replacement_chunks=replacement_chunks,
    )

    request = {
        "updateCells": {
            "range": parse_single_cell_grid_range(sheet_props["sheetId"], args.cell),
            "rows": [
                {
                    "values": [
                        {
                            "userEnteredValue": {"stringValue": rebuilt_text},
                            "textFormatRuns": rebuilt_runs,
                        }
                    ]
                }
            ],
            "fields": "userEnteredValue,textFormatRuns",
        }
    }

    if args.stage:
        draft = get_active_draft(required=True)
        if draft["spreadsheet_id"] != target["spreadsheet_id"]:
            raise SystemExit("Active draft targets a different spreadsheet.")
        staged_operation = {
            "key": f"content:{tab}:{args.cell}",
            "kind": "content",
            "spreadsheet_id": target["spreadsheet_id"],
            "operation": {
                "tab": tab,
                "cell": args.cell,
                "action": "replace_chunks",
                "expected_revision": payload["revision"],
                "chunk_ids": args.chunk_ids,
                "replacement_chunks": replacement_chunks,
            },
            "summary": {
                "tab": tab,
                "cell": args.cell,
                "changed_chunk_ids": changed_chunk_ids,
                "before_text": payload["text"],
                "after_text": rebuilt_text,
                "revision": payload["revision"],
            },
        }
        add_or_replace_operation(draft, staged_operation)
        save_active_draft(draft)
        print(json.dumps({"staged": True, "draft_id": draft["id"], "operation": staged_operation["summary"]}, indent=2))
        return

    if args.dry_run:
        print(
            json.dumps(
                {
                    "tab": tab,
                    "cell": args.cell,
                    "changed_chunk_ids": changed_chunk_ids,
                    "before": payload,
                    "after": {
                        "text": rebuilt_text,
                        "text_format_runs": rebuilt_runs,
                        "revision": revision_hash(rebuilt_text, rebuilt_chunks),
                        "chunk_count": len(rebuilt_chunks),
                        "chunks": chunks_payload(rebuilt_chunks),
                    },
                    "request": request,
                },
                indent=2,
            )
        )
        return

    response = (
        service.spreadsheets()
        .batchUpdate(
            spreadsheetId=target["spreadsheet_id"],
            body={"requests": [request], "includeSpreadsheetInResponse": False},
        )
        .execute()
    )
    print(
        json.dumps(
            {
                "spreadsheet_id": target["spreadsheet_id"],
                "tab": tab,
                "cell": args.cell,
                "revision": revision_hash(rebuilt_text, rebuilt_chunks),
                "changed_chunk_ids": changed_chunk_ids,
                "updated_text": rebuilt_text,
                "text_format_runs": rebuilt_runs,
                "response": response,
            },
            indent=2,
        )
    )


def deprecated_replace_span_command(_: argparse.Namespace) -> None:
    raise SystemExit(
        json.dumps(
            {
                "error": "replace_span_deprecated",
                "message": "replace-span is deprecated. Use inspect to get chunk IDs, then call replace-chunks.",
            },
            indent=2,
        )
    )


def load_replacement_chunks(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.replacement_chunks_json:
        return json.loads(args.replacement_chunks_json)
    if args.text is None:
        raise SystemExit("Provide --replacement-chunks-json or --text for replace-chunks.")
    replacement_chunk: dict[str, Any] = {"text": args.text}
    if args.format_json:
        replacement_chunk["format"] = json.loads(args.format_json)
    return [replacement_chunk]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and edit a single Google Sheets cell as grapheme chunks.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Show grapheme chunks and formatting for a single cell.")
    inspect_parser.add_argument("--spreadsheet", required=True, help="Spreadsheet URL, ID, or saved alias.")
    inspect_parser.add_argument("--tab", help="Tab name. Falls back to alias default if available.")
    inspect_parser.add_argument("--cell", required=True, help="Single A1 cell reference, for example B4.")
    inspect_parser.set_defaults(handler=inspect_command)

    replace_chunks = subparsers.add_parser("replace-chunks", help="Replace contiguous chunk IDs in a cell.")
    replace_chunks.add_argument("--spreadsheet", required=True, help="Spreadsheet URL, ID, or saved alias.")
    replace_chunks.add_argument("--tab", help="Tab name. Falls back to alias default if available.")
    replace_chunks.add_argument("--cell", required=True, help="Single A1 cell reference, for example B4.")
    replace_chunks.add_argument("--chunk-id", dest="chunk_ids", action="append", required=True, help="Chunk ID from inspect output. Repeat for contiguous chunks.")
    replace_chunks.add_argument("--text", help="Replacement text. Shorthand for one replacement chunk.")
    replace_chunks.add_argument("--replacement-chunks-json", help="JSON array of replacement chunk objects.")
    replace_chunks.add_argument("--format-json", help="Optional JSON TextFormat override when using --text.")
    replace_chunks.add_argument("--expected-revision", help="Revision hash from inspect output.")
    replace_chunks.add_argument("--stage", action="store_true", help="Stage this edit into the active draft instead of applying immediately.")
    replace_chunks.add_argument("--dry-run", action="store_true", help="Preview the rebuilt value and request without writing.")
    replace_chunks.set_defaults(handler=replace_chunks_command)

    replace_span = subparsers.add_parser("replace-span", help="Deprecated. Use replace-chunks instead.")
    replace_span.set_defaults(handler=deprecated_replace_span_command)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
