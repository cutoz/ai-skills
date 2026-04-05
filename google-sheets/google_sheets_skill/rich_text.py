from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
from typing import Any

import regex

from .sheets import parse_a1_cell, quoted_tab_name


@dataclass
class GraphemeChunk:
    chunk_id: str
    index: int
    text: str
    utf16_start: int
    utf16_end: int
    format: dict[str, Any]


def utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def clone_format(value: dict[str, Any] | None) -> dict[str, Any]:
    return deepcopy(value or {})


def grapheme_chunks(text: str, text_format_runs: list[dict[str, Any]] | None) -> list[GraphemeChunk]:
    runs = sorted(text_format_runs or [], key=lambda item: item.get("startIndex", 0))
    chunks: list[GraphemeChunk] = []
    utf16_offset = 0
    run_index = 0
    current_format: dict[str, Any] = {}

    graphemes = regex.findall(r"\X", text)
    for index, grapheme in enumerate(graphemes, start=1):
        while run_index < len(runs) and runs[run_index].get("startIndex", 0) <= utf16_offset:
            current_format = clone_format(runs[run_index].get("format", {}))
            run_index += 1
        end_offset = utf16_offset + utf16_length(grapheme)
        chunks.append(
            GraphemeChunk(
                chunk_id=f"c{index}",
                index=index,
                text=grapheme,
                utf16_start=utf16_offset,
                utf16_end=end_offset,
                format=clone_format(current_format),
            )
        )
        utf16_offset = end_offset
    return chunks


def compress_text_format_runs(chunks: list[GraphemeChunk]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    current_format: dict[str, Any] = {}
    for chunk in chunks:
        if chunk.format != current_format:
            runs.append(
                {
                    "startIndex": chunk.utf16_start,
                    "format": clone_format(chunk.format),
                }
            )
            current_format = clone_format(chunk.format)
    return runs


def revision_hash(text: str, chunks: list[GraphemeChunk]) -> str:
    digest = hashlib.sha256()
    digest.update(text.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(len(chunks)).encode("ascii"))
    return digest.hexdigest()[:16]


def chunks_payload(chunks: list[GraphemeChunk]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": chunk.chunk_id,
            "index": chunk.index,
            "text": chunk.text,
            "utf16_start": chunk.utf16_start,
            "utf16_end": chunk.utf16_end,
            "format": chunk.format,
        }
        for chunk in chunks
    ]


def choose_inherited_format(
    chunks: list[GraphemeChunk],
    start_index: int,
    end_index: int,
) -> dict[str, Any]:
    if chunks and 0 <= start_index < len(chunks):
        return clone_format(chunks[start_index].format)
    if chunks and 0 < end_index <= len(chunks):
        return clone_format(chunks[end_index - 1].format)
    if chunks and start_index > 0:
        return clone_format(chunks[start_index - 1].format)
    if chunks and end_index < len(chunks):
        return clone_format(chunks[end_index].format)
    return {}


def apply_replace_span(
    text: str,
    text_format_runs: list[dict[str, Any]] | None,
    start_index_1_based: int,
    end_index_1_based: int,
    replacement_text: str,
    replacement_format: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]], list[GraphemeChunk]]:
    chunks = grapheme_chunks(text, text_format_runs)
    if start_index_1_based < 1:
        raise ValueError("start must be >= 1")
    if end_index_1_based < start_index_1_based:
        raise ValueError("end must be >= start")

    start_index = start_index_1_based - 1
    end_index = min(end_index_1_based, len(chunks))
    if start_index > len(chunks):
        raise ValueError("start is beyond the end of the cell text")

    inherited_format = replacement_format or choose_inherited_format(chunks, start_index, end_index)
    replacement_chunks = [
        GraphemeChunk(chunk_id="", index=0, text=value, utf16_start=0, utf16_end=0, format=clone_format(inherited_format))
        for value in regex.findall(r"\X", replacement_text)
    ]

    new_chunks = chunks[:start_index] + replacement_chunks + chunks[end_index:]
    utf16_offset = 0
    rebuilt_text_parts: list[str] = []
    for index, chunk in enumerate(new_chunks, start=1):
        rebuilt_text_parts.append(chunk.text)
        chunk.chunk_id = f"c{index}"
        chunk.index = index
        chunk.utf16_start = utf16_offset
        utf16_offset += utf16_length(chunk.text)
        chunk.utf16_end = utf16_offset

    rebuilt_text = "".join(rebuilt_text_parts)
    rebuilt_runs = compress_text_format_runs(new_chunks)
    return rebuilt_text, rebuilt_runs, new_chunks


def apply_replace_chunks(
    text: str,
    text_format_runs: list[dict[str, Any]] | None,
    chunk_ids: list[str],
    replacement_chunks: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], list[GraphemeChunk], list[str]]:
    if not chunk_ids:
        raise ValueError("chunk_ids must not be empty")

    chunks = grapheme_chunks(text, text_format_runs)
    chunk_lookup = {chunk.chunk_id: chunk for chunk in chunks}
    missing = [chunk_id for chunk_id in chunk_ids if chunk_id not in chunk_lookup]
    if missing:
        raise ValueError(f"Unknown chunk IDs: {', '.join(missing)}")

    selected_indices = sorted(chunk_lookup[chunk_id].index for chunk_id in chunk_ids)
    if selected_indices != list(range(selected_indices[0], selected_indices[-1] + 1)):
        raise ValueError("replace_chunks currently requires contiguous chunk IDs")

    start_index = selected_indices[0] - 1
    end_index = selected_indices[-1]
    inherited_format = choose_inherited_format(chunks, start_index, end_index)

    new_chunk_objects = []
    for replacement in replacement_chunks:
        replacement_text = replacement.get("text")
        if replacement_text is None:
            raise ValueError("Each replacement chunk requires text")
        replacement_format = clone_format(replacement.get("format", inherited_format))
        for value in regex.findall(r"\X", replacement_text):
            new_chunk_objects.append(
                GraphemeChunk(
                    chunk_id="",
                    index=0,
                    text=value,
                    utf16_start=0,
                    utf16_end=0,
                    format=clone_format(replacement_format),
                )
            )

    new_chunks = chunks[:start_index] + new_chunk_objects + chunks[end_index:]
    utf16_offset = 0
    rebuilt_text_parts: list[str] = []
    for index, chunk in enumerate(new_chunks, start=1):
        rebuilt_text_parts.append(chunk.text)
        chunk.chunk_id = f"c{index}"
        chunk.index = index
        chunk.utf16_start = utf16_offset
        utf16_offset += utf16_length(chunk.text)
        chunk.utf16_end = utf16_offset

    rebuilt_text = "".join(rebuilt_text_parts)
    rebuilt_runs = compress_text_format_runs(new_chunks)
    return rebuilt_text, rebuilt_runs, new_chunks, chunk_ids


def single_cell_a1(tab: str, cell: str) -> str:
    return f"{quoted_tab_name(tab)}!{cell}"


def parse_single_cell_grid_range(sheet_id: int, cell: str) -> dict[str, int]:
    row_index, column_index = parse_a1_cell(cell)
    return {
        "sheetId": sheet_id,
        "startRowIndex": row_index,
        "endRowIndex": row_index + 1,
        "startColumnIndex": column_index,
        "endColumnIndex": column_index + 1,
    }
