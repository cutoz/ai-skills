#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from google_sheets_skill.memory import save_context
from google_sheets_skill.sheets import (
    build_sheets_service,
    densify_rows,
    expand_tab_to_grid_range,
    get_spreadsheet_metadata,
    normalize_range,
    resolve_spreadsheet_target,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read Google Sheets data as a dense matrix.")
    parser.add_argument("--spreadsheet", required=True, help="Spreadsheet URL, ID, or saved alias.")
    parser.add_argument("--tab", help="Tab name to read.")
    parser.add_argument("--range", dest="range_name", help="A1 range to read.")
    parser.add_argument("--value-render-option", choices=["FORMATTED_VALUE", "UNFORMATTED_VALUE", "FORMULA"], default="FORMATTED_VALUE")
    parser.add_argument("--datetime-render-option", choices=["SERIAL_NUMBER", "FORMATTED_STRING"], default="FORMATTED_STRING")
    parser.add_argument("--context-key", help="Optional memory key for a compact conversation handoff.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    spreadsheet_ref = args.spreadsheet
    target = resolve_spreadsheet_target(spreadsheet_ref)
    service = build_sheets_service()
    metadata = get_spreadsheet_metadata(service, target["spreadsheet_id"])
    sheets = metadata.get("sheets", [])

    tab = args.tab or target.get("tab")
    if not tab and target.get("gid") is not None:
        for sheet in sheets:
            if sheet["properties"].get("sheetId") == target["gid"]:
                tab = sheet["properties"]["title"]
                break

    requested_range = normalize_range(tab, args.range_name or target.get("range"))
    if tab and "!" not in (requested_range or "") and not (args.range_name or target.get("range")):
        for sheet in sheets:
            if sheet["properties"]["title"] == tab:
                grid = sheet["properties"].get("gridProperties", {})
                requested_range = expand_tab_to_grid_range(
                    tab,
                    grid.get("rowCount", 0),
                    grid.get("columnCount", 0),
                )
                break

    values_response = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=target["spreadsheet_id"],
            range=requested_range,
            valueRenderOption=args.value_render_option,
            dateTimeRenderOption=args.datetime_render_option,
        )
        .execute()
        if requested_range
        else {"range": None, "values": []}
    )
    dense = densify_rows(values_response.get("values", []))

    payload = {
        "spreadsheet_id": target["spreadsheet_id"],
        "alias": target.get("alias"),
        "spreadsheet_title": metadata["properties"]["title"],
        "tabs": [
            {
                "title": sheet["properties"]["title"],
                "sheet_id": sheet["properties"]["sheetId"],
                "grid_properties": sheet["properties"].get("gridProperties", {}),
            }
            for sheet in sheets
        ],
        "requested_range": requested_range,
        "returned_range": values_response.get("range"),
        "row_count": len(dense),
        "column_count": max((len(row) for row in dense), default=0),
        "values": dense,
    }

    if args.context_key:
        save_context(
            args.context_key,
            {
                "summary": f"Read {payload['spreadsheet_title']} {payload['returned_range'] or ''}".strip(),
                "spreadsheet_id": payload["spreadsheet_id"],
                "tab": tab,
            },
        )

    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
