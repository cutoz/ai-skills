#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

from google_sheets_skill.sheets import build_sheets_service, densify_rows, load_payload, normalize_range, resolve_spreadsheet_target


def find_non_empty_conflicts(existing: list[list[object]], incoming: list[list[object]]) -> list[dict[str, object]]:
    dense_existing = densify_rows(existing)
    dense_incoming = densify_rows(incoming)
    rows = max(len(dense_existing), len(dense_incoming))
    cols = max(
        max((len(row) for row in dense_existing), default=0),
        max((len(row) for row in dense_incoming), default=0),
    )
    conflicts: list[dict[str, object]] = []
    for row_index in range(rows):
        before = dense_existing[row_index] if row_index < len(dense_existing) else [""] * cols
        after = dense_incoming[row_index] if row_index < len(dense_incoming) else [""] * cols
        for col_index in range(cols):
            existing_value = before[col_index] if col_index < len(before) else ""
            incoming_value = after[col_index] if col_index < len(after) else ""
            if incoming_value in ("", None):
                continue
            if existing_value not in ("", None):
                conflicts.append(
                    {
                        "row_offset": row_index,
                        "column_offset": col_index,
                        "existing_value": existing_value,
                        "incoming_value": incoming_value,
                    }
                )
    return conflicts


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Google Sheets range updates.")
    parser.add_argument("--spreadsheet", required=True, help="Spreadsheet URL, ID, or saved alias.")
    parser.add_argument("--input", help="Path to a JSON payload file.")
    parser.add_argument("--json", help="Inline JSON payload.")
    args = parser.parse_args()

    payload = load_payload(args.input, args.json)
    target = resolve_spreadsheet_target(args.spreadsheet)
    service = build_sheets_service()

    data = []
    blocked_operations = []
    for operation in payload["operations"]:
        resolved_range = normalize_range(operation.get("tab"), operation.get("range"))
        values = operation["values"]
        existing = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=target["spreadsheet_id"], range=resolved_range)
            .execute()
            .get("values", [])
        )
        conflicts = find_non_empty_conflicts(existing, values)
        if conflicts:
            blocked_operations.append(
                {
                    "range": resolved_range,
                    "conflicts": conflicts[:10],
                    "conflict_count": len(conflicts),
                }
            )
            continue
        data.append({"range": resolved_range, "values": values})

    if blocked_operations:
        print(
            json.dumps(
                {
                    "error": "non_empty_cell_write_blocked",
                    "message": (
                        "write_sheet.py only writes into empty cells. "
                        "Use change_cell.py for single-cell edits or change_bulk_cell.py for explicit populated-range changes."
                    ),
                    "blocked_operations": blocked_operations,
                },
                indent=2,
            )
        )
        sys.exit(1)

    response = (
        service.spreadsheets()
        .values()
        .batchUpdate(
            spreadsheetId=target["spreadsheet_id"],
            body={
                "valueInputOption": payload.get("value_input_option", "USER_ENTERED"),
                "data": data,
                "includeValuesInResponse": payload.get("include_values_in_response", False),
            },
        )
        .execute()
    )
    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    main()
