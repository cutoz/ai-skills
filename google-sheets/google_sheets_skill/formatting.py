from __future__ import annotations

from typing import Any

from .sheets import a1_range_to_grid_range


def sheet_lookup(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        sheet["properties"]["title"]: sheet["properties"]
        for sheet in metadata.get("sheets", [])
    }


def build_repeat_cell_request(sheet_props: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    return {
        "repeatCell": {
            "range": a1_range_to_grid_range(sheet_props["sheetId"], operation["range"]),
            "cell": {"userEnteredFormat": operation["format"]},
            "fields": operation.get("fields", "userEnteredFormat"),
        }
    }


def build_update_dimension_request(sheet_props: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    dimension = operation["dimension"].upper()
    if dimension not in {"ROWS", "COLUMNS"}:
        raise ValueError("dimension must be ROWS or COLUMNS")
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_props["sheetId"],
                "dimension": dimension,
                "startIndex": operation["start_index"],
                "endIndex": operation["end_index"],
            },
            "properties": operation["properties"],
            "fields": operation["fields"],
        }
    }


def build_sheet_properties_request(sheet_props: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    properties = {"sheetId": sheet_props["sheetId"]}
    properties.update(operation["properties"])
    return {
        "updateSheetProperties": {
            "properties": properties,
            "fields": operation["fields"],
        }
    }


def operation_to_request(sheets_by_title: dict[str, dict[str, Any]], operation: dict[str, Any]) -> dict[str, Any]:
    tab = operation.get("tab")
    if not tab:
        raise ValueError("Each formatting operation requires a tab")
    if tab not in sheets_by_title:
        raise ValueError(f"Unknown tab: {tab}")
    sheet_props = sheets_by_title[tab]

    kind = operation["type"]
    if kind == "repeatCell":
        return build_repeat_cell_request(sheet_props, operation)
    if kind == "updateDimensionProperties":
        return build_update_dimension_request(sheet_props, operation)
    if kind == "updateSheetProperties":
        return build_sheet_properties_request(sheet_props, operation)
    raise ValueError(f"Unsupported formatting operation type: {kind}")
