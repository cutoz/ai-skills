#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from google_sheets_skill.sheets import build_sheets_service, resolve_spreadsheet_target


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new tab in a Google spreadsheet.")
    parser.add_argument("--spreadsheet", required=True, help="Spreadsheet URL, ID, or saved alias.")
    parser.add_argument("--title", required=True, help="New tab title.")
    parser.add_argument("--rows", type=int, default=1000, help="Initial row count.")
    parser.add_argument("--cols", type=int, default=26, help="Initial column count.")
    args = parser.parse_args()

    target = resolve_spreadsheet_target(args.spreadsheet)
    service = build_sheets_service()
    response = (
        service.spreadsheets()
        .batchUpdate(
            spreadsheetId=target["spreadsheet_id"],
            body={
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": args.title,
                                "gridProperties": {
                                    "rowCount": args.rows,
                                    "columnCount": args.cols,
                                },
                            }
                        }
                    }
                ]
            },
        )
        .execute()
    )
    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    main()
