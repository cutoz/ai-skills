#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from google_sheets_skill.memory import (
    load_memory,
    save_context,
    set_alias,
    set_sheet_note,
)
from google_sheets_skill.sheets import extract_spreadsheet_id


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage alias and context memory for the Google Sheets skill.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    alias = subparsers.add_parser("alias-set", help="Create or update a friendly sheet alias.")
    alias.add_argument("--name", required=True)
    alias.add_argument("--spreadsheet", required=True, help="Spreadsheet URL or ID.")
    alias.add_argument("--tab")
    alias.add_argument("--range")

    note = subparsers.add_parser("note-set", help="Attach a short note to a spreadsheet.")
    note.add_argument("--spreadsheet", required=True, help="Spreadsheet URL or ID.")
    note.add_argument("--note", required=True)

    context = subparsers.add_parser("context-set", help="Persist a compact conversation summary.")
    context.add_argument("--key", required=True)
    context.add_argument("--summary", required=True)
    context.add_argument("--spreadsheet")
    context.add_argument("--tab")

    subparsers.add_parser("show", help="Dump the current persistent memory.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "alias-set":
        target = {
            "spreadsheet_id": extract_spreadsheet_id(args.spreadsheet),
            "tab": args.tab,
            "range": args.range,
        }
        print(json.dumps(set_alias(args.name, target), indent=2))
        return

    if args.command == "note-set":
        set_sheet_note(extract_spreadsheet_id(args.spreadsheet), args.note)
        print(json.dumps({"ok": True}, indent=2))
        return

    if args.command == "context-set":
        payload = {"summary": args.summary, "spreadsheet_id": None, "tab": args.tab}
        if args.spreadsheet:
            payload["spreadsheet_id"] = extract_spreadsheet_id(args.spreadsheet)
        save_context(args.key, payload)
        print(json.dumps(payload, indent=2))
        return

    print(json.dumps(load_memory(), indent=2))


if __name__ == "__main__":
    main()
