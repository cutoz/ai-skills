#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from google_sheets_skill.drafts import add_or_replace_operation, get_active_draft, save_active_draft
from google_sheets_skill.formatting import operation_to_request, sheet_lookup
from google_sheets_skill.sheets import build_sheets_service, get_spreadsheet_metadata, load_payload, resolve_spreadsheet_target


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Google Sheets formatting and layout changes.")
    parser.add_argument("--spreadsheet", required=True, help="Spreadsheet URL, ID, or saved alias.")
    parser.add_argument("--input", help="Path to a JSON payload file.")
    parser.add_argument("--json", help="Inline JSON payload.")
    parser.add_argument("--stage", action="store_true", help="Stage formatting operations into the active draft instead of applying immediately.")
    args = parser.parse_args()

    payload = load_payload(args.input, args.json)
    target = resolve_spreadsheet_target(args.spreadsheet)
    service = build_sheets_service()
    metadata = get_spreadsheet_metadata(service, target["spreadsheet_id"])
    sheets_by_title = sheet_lookup(metadata)

    if args.stage:
        draft = get_active_draft(required=True)
        if draft["spreadsheet_id"] != target["spreadsheet_id"]:
            raise SystemExit("Active draft targets a different spreadsheet.")
        staged = []
        for index, operation in enumerate(payload["operations"], start=1):
            operation_to_request(sheets_by_title, operation)
            staged_operation = {
                "key": f"format:{operation['tab']}:{operation['type']}:{index}:{operation.get('range', operation.get('fields', 'op'))}",
                "kind": "format",
                "spreadsheet_id": target["spreadsheet_id"],
                "operation": operation,
                "summary": {
                    "tab": operation.get("tab"),
                    "type": operation.get("type"),
                    "range": operation.get("range"),
                },
            }
            add_or_replace_operation(draft, staged_operation)
            staged.append(staged_operation["summary"])
        save_active_draft(draft)
        print(json.dumps({"staged": True, "draft_id": draft["id"], "operations": staged}, indent=2))
        return

    requests = [operation_to_request(sheets_by_title, operation) for operation in payload["operations"]]
    response = (
        service.spreadsheets()
        .batchUpdate(
            spreadsheetId=target["spreadsheet_id"],
            body={"requests": requests, "includeSpreadsheetInResponse": False},
        )
        .execute()
    )
    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    main()
