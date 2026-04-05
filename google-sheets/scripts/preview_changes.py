#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import Any

from google_sheets_skill.sheets import (
    build_sheets_service,
    densify_rows,
    load_payload,
    normalize_range,
    resolve_spreadsheet_target,
)


def heuristic(total_cells: int, overwritten_cells: int, operation_count: int) -> bool:
    return total_cells > 12 or overwritten_cells > 0 or operation_count > 1


def count_overwrites(existing: list[list[Any]], incoming: list[list[Any]]) -> int:
    dense_existing = densify_rows(existing)
    dense_incoming = densify_rows(incoming)
    rows = max(len(dense_existing), len(dense_incoming))
    cols = max(max((len(row) for row in dense_existing), default=0), max((len(row) for row in dense_incoming), default=0))
    overwrites = 0
    for row_index in range(rows):
        before = dense_existing[row_index] if row_index < len(dense_existing) else [""] * cols
        after = dense_incoming[row_index] if row_index < len(dense_incoming) else [""] * cols
        for col_index in range(cols):
            if col_index < len(before) and col_index < len(after) and before[col_index] not in ("", None) and before[col_index] != after[col_index]:
                overwrites += 1
    return overwrites


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview Google Sheets range updates.")
    parser.add_argument("--spreadsheet", required=True, help="Spreadsheet URL, ID, or saved alias.")
    parser.add_argument("--input", help="Path to a JSON payload file.")
    parser.add_argument("--json", help="Inline JSON payload.")
    args = parser.parse_args()

    payload = load_payload(args.input, args.json)
    target = resolve_spreadsheet_target(args.spreadsheet)
    service = build_sheets_service()

    operations_preview = []
    total_cells = 0
    overwritten_cells = 0
    for operation in payload["operations"]:
        resolved_range = normalize_range(operation.get("tab"), operation.get("range"))
        existing = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=target["spreadsheet_id"], range=resolved_range)
            .execute()
            .get("values", [])
        )
        values = operation["values"]
        op_overwrites = count_overwrites(existing, values)
        overwritten_cells += op_overwrites
        total_cells += sum(len(row) for row in values)
        operations_preview.append(
            {
                "range": resolved_range,
                "incoming_rows": len(values),
                "incoming_columns": max((len(row) for row in values), default=0),
                "overwritten_cells": op_overwrites,
                "existing_preview": densify_rows(existing)[:5],
                "incoming_preview": densify_rows(values)[:5],
            }
        )

    print(
        json.dumps(
            {
                "spreadsheet_id": target["spreadsheet_id"],
                "operation_count": len(payload["operations"]),
                "total_cells": total_cells,
                "overwritten_cells": overwritten_cells,
                "requires_preview": heuristic(total_cells, overwritten_cells, len(payload["operations"])),
                "operations": operations_preview,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
