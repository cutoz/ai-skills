from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from google.auth.exceptions import DefaultCredentialsError, RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .config import load_config, token_path
from .memory import resolve_alias
from .paths import ensure_state_dir


SPREADSHEET_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")
GID_RE = re.compile(r"[?#&]gid=(\d+)")


def extract_spreadsheet_id(value: str) -> str:
    value = value.strip()
    if match := SPREADSHEET_ID_RE.search(value):
        return match.group(1)
    return value


def extract_gid(value: str) -> int | None:
    value = value.strip()
    if match := GID_RE.search(value):
        return int(match.group(1))
    return None


def resolve_spreadsheet_target(target: str) -> dict[str, Any]:
    alias = resolve_alias(target)
    if alias:
        return {
            "spreadsheet_id": alias["spreadsheet_id"],
            "tab": alias.get("tab"),
            "range": alias.get("range"),
            "alias": alias.get("alias_name", target),
            "gid": alias.get("gid"),
        }
    return {
        "spreadsheet_id": extract_spreadsheet_id(target),
        "alias": None,
        "gid": extract_gid(target),
    }


def _load_token_credentials(config: dict[str, Any]) -> Credentials | None:
    path = token_path(config)
    if not path.exists():
        return None
    return Credentials.from_authorized_user_file(str(path), config["scopes"])


def login(force: bool = False) -> dict[str, Any]:
    config = load_config()
    secret_path = config.get("client_secret_path")
    if not secret_path:
        raise SystemExit(
            "No OAuth client configured. Run auth.py configure --client-secret /path/to/client_secret.json first."
        )

    creds = None if force else _load_token_credentials(config)
    if creds and creds.valid:
        return credential_summary(creds)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(secret_path, config["scopes"])
        creds = flow.run_local_server(port=0)

    ensure_state_dir()
    with token_path(config).open("w", encoding="utf-8") as handle:
        handle.write(creds.to_json())
    return credential_summary(creds)


def load_credentials() -> Credentials:
    config = load_config()
    creds = _load_token_credentials(config)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with token_path(config).open("w", encoding="utf-8") as handle:
            handle.write(creds.to_json())
        return creds

    raise SystemExit(
        "Google Sheets auth not initialized. Run auth.py login after configuring the OAuth client."
    )


def credential_summary(creds: Credentials) -> dict[str, Any]:
    return {
        "has_token": True,
        "scopes": sorted(creds.scopes or []),
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
        "account": getattr(creds, "account", None),
    }


def build_sheets_service():
    try:
        creds = load_credentials()
    except (DefaultCredentialsError, RefreshError) as exc:
        raise SystemExit(f"Unable to load Google credentials: {exc}") from exc
    return build("sheets", "v4", credentials=creds)


def get_spreadsheet_metadata(service: Any, spreadsheet_id: str) -> dict[str, Any]:
    return (
        service.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="spreadsheetId,properties.title,sheets.properties")
        .execute()
    )


def find_sheet_properties(metadata: dict[str, Any], tab: str) -> dict[str, Any]:
    for sheet in metadata.get("sheets", []):
        properties = sheet.get("properties", {})
        if properties.get("title") == tab:
            return properties
    raise ValueError(f"Unknown tab: {tab}")


def get_single_cell_data(service: Any, spreadsheet_id: str, tab: str, cell: str) -> tuple[dict[str, Any], dict[str, Any]]:
    target_range = f"{quoted_tab_name(tab)}!{cell}"
    response = (
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            ranges=[target_range],
            includeGridData=True,
            fields=(
                "sheets.properties,"
                "sheets.data.rowData.values("
                "userEnteredValue,"
                "textFormatRuns,"
                "userEnteredFormat,"
                "note)"
            ),
        )
        .execute()
    )
    sheet = response["sheets"][0]
    row_data = sheet.get("data", [{}])[0].get("rowData", [])
    cell_data = {}
    if row_data and row_data[0].get("values"):
        cell_data = row_data[0]["values"][0]
    return sheet["properties"], cell_data


def densify_rows(values: list[list[Any]]) -> list[list[Any]]:
    width = max((len(row) for row in values), default=0)
    return [row + [""] * (width - len(row)) for row in values]


def quoted_tab_name(tab: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_]+", tab):
        return tab
    escaped = tab.replace("'", "''")
    return f"'{escaped}'"


def normalize_range(tab: str | None, range_name: str | None) -> str | None:
    if range_name:
        if "!" in range_name or not tab:
            return range_name
        return f"{quoted_tab_name(tab)}!{range_name}"
    if tab:
        return quoted_tab_name(tab)
    return None


def column_letters(column_number: int) -> str:
    letters = []
    current = column_number
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


def expand_tab_to_grid_range(tab: str, row_count: int, column_count: int) -> str:
    if row_count < 1 or column_count < 1:
        return quoted_tab_name(tab)
    return f"{quoted_tab_name(tab)}!A1:{column_letters(column_count)}{row_count}"


CELL_RE = re.compile(r"^([A-Z]+)(\d+)$")
QUALIFIED_RANGE_RE = re.compile(r"^(?:(?P<tab>'(?:[^']|'')+'|[^!]+)!)?(?P<range>.+)$")


def column_index_from_letters(letters: str) -> int:
    value = 0
    for char in letters.upper():
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value - 1


def parse_a1_cell(cell: str) -> tuple[int, int]:
    match = CELL_RE.fullmatch(cell.upper())
    if not match:
        raise ValueError(f"Unsupported A1 cell reference: {cell}")
    column_letters_value, row_value = match.groups()
    return int(row_value) - 1, column_index_from_letters(column_letters_value)


def a1_range_to_grid_range(sheet_id: int, a1_range: str) -> dict[str, int]:
    normalized = a1_range.strip().upper()
    if ":" in normalized:
        start_cell, end_cell = normalized.split(":", 1)
    else:
        start_cell = end_cell = normalized

    start_row, start_col = parse_a1_cell(start_cell)
    end_row, end_col = parse_a1_cell(end_cell)

    return {
        "sheetId": sheet_id,
        "startRowIndex": min(start_row, end_row),
        "endRowIndex": max(start_row, end_row) + 1,
        "startColumnIndex": min(start_col, end_col),
        "endColumnIndex": max(start_col, end_col) + 1,
    }


def split_qualified_range(value: str) -> tuple[str | None, str]:
    match = QUALIFIED_RANGE_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"Unsupported A1 range: {value}")
    tab = match.group("tab")
    if tab:
        if tab.startswith("'") and tab.endswith("'"):
            tab = tab[1:-1].replace("''", "'")
    return tab, match.group("range")


def range_anchor(value: str) -> tuple[int, int]:
    _, range_part = split_qualified_range(value)
    start = range_part.split(":", 1)[0]
    return parse_a1_cell(start)


def absolute_a1_from_offset(anchor_row: int, anchor_col: int, row_offset: int, col_offset: int) -> str:
    return f"{column_letters(anchor_col + col_offset + 1)}{anchor_row + row_offset + 1}"


def load_payload(path: str | None, inline_json: str | None) -> dict[str, Any]:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    if inline_json:
        return json.loads(inline_json)
    return json.loads(input())
