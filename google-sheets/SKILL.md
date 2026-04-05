---
name: google-sheets
description: Read, analyze, and update Google Sheets from Codex. Use when the user wants to inspect a sheet, summarize a tracker, compare tabs, write cells or ranges, or continue a spreadsheet-centered conversation using natural aliases like weekly tracker.
metadata:
  short-description: Read and update Google Sheets with conversational context
---

# Google Sheets

This skill lets Codex work with Google Sheets as live structured data. It is designed for arbitrary layouts, not only tables. Read sheets into a 2D matrix first, reason about the layout, then write explicit ranges back.

## What this skill stores

Persistent private state lives under `~/.codex/google-sheets/`:
- OAuth client config and token cache
- friendly sheet aliases
- short per-sheet notes
- compact conversation handoff summaries
- local draft state for staged edits

This skill does **not** maintain its own changelog or history of the sheet. Google Sheets remains the source of truth.

## Prerequisites

1. Create a Google OAuth desktop client in Google Cloud.
2. Save the downloaded client JSON locally.
3. Configure and log in:

```bash
uv run --project ~/.codex/skills/google-sheets python ~/.codex/skills/google-sheets/scripts/auth.py configure --client-secret /absolute/path/client_secret.json
uv run --project ~/.codex/skills/google-sheets python ~/.codex/skills/google-sheets/scripts/auth.py login
```

## Required workflow

### Step 1
Resolve the target sheet. Prefer a saved alias for natural references like `weekly tracker`. If there is no alias, ask for a spreadsheet URL or ID before writing.

### Step 2
Read before any write or formatting change. Use `read_sheet.py` to inspect the relevant tab or range as a matrix, confirm the current headers/layout, and verify the target cells are still what you think they are right before writing.

### Step 3
Translate the user request into explicit A1 targets. For populated existing-cell edits, inspect the exact target cells first and use the returned `chunk_id` and `revision` values. Do not write vague intents directly.

### Step 4
For broad edits or overwrites, use `preview_changes.py` first. Bulk updates to existing populated cells are discouraged unless they go through `change_bulk_cell.py`.

### Step 5
Use `write_sheet.py` only to fill empty cells or empty regions. If existing cell content must change, use `change_cell.py` for one cell or `change_bulk_cell.py` for populated ranges.

### Step 6
If you want to iterate locally first, create a draft, stage edits with `--stage`, review them with `draft.py show`, and only push them with `draft.py commit`.

### Step 7
If the conversation would benefit from continuity later, store or update:
- an alias with `memory.py alias-set`
- a short note with `memory.py note-set`
- a compact handoff summary with `memory.py context-set`

## Scripts

### `auth.py`

- `configure --client-secret /path/to/client_secret.json`
- `login`
- `status`

### `memory.py`

- `alias-set --name "weekly tracker" --spreadsheet <url-or-id> --tab "Week 14"`
- `note-set --spreadsheet <url-or-id> --note "Main operating tracker"`
- `context-set --key weekly-tracker --summary "Reviewed blockers and next actions" --spreadsheet <url-or-id> --tab "Week 14"`
- `show`

### `draft.py`

- `create --spreadsheet <url-or-id-or-alias> --name <draft-name>`
- `status`
- `show`
- `clear`
- `commit`

Rules:
- Drafts are local only until commit.
- `commit` previews valid operations and conflicts.
- `commit --apply` applies the whole draft only when there are no conflicts.
- `commit --apply-valid` applies only valid operations and leaves conflicts staged.
- Commits operate on the current active draft only.

### `read_sheet.py`

Read a full tab or explicit range:

```bash
uv run --project ~/.codex/skills/google-sheets python ~/.codex/skills/google-sheets/scripts/read_sheet.py --spreadsheet "weekly tracker" --tab "Week 14"
uv run --project ~/.codex/skills/google-sheets python ~/.codex/skills/google-sheets/scripts/read_sheet.py --spreadsheet "<sheet-url>" --range "Roadmap!A1:F20"
```

### `preview_changes.py`

Preview a batch of updates from a JSON payload:

```json
{
  "value_input_option": "USER_ENTERED",
  "operations": [
    {
      "range": "B2:C3",
      "tab": "Week 14",
      "values": [["High", "Blocked"], ["Medium", "On Track"]]
    }
  ]
}
```

### `write_sheet.py`

Apply the same payload after confirming the target ranges are correct.

Guardrail:
- `write_sheet.py` only writes into empty cells.
- If any target cell already contains data, the command fails with a structured error.
- Existing-cell edits should go through `change_cell.py` or `change_bulk_cell.py`.

Plain text values can include emojis and symbols. They are written as normal cell content.

### `change_cell.py`

Use this when the user wants to edit part of a single rich-text cell without destroying unrelated formatting.

Capabilities:
- inspect a cell as grapheme chunks with per-chunk format deltas
- replace contiguous chunk IDs while preserving unaffected text-format runs
- optionally apply a new `TextFormat` override to replacement chunks
- return a per-cell revision hash so stale chunk edits can be rejected
- reject stale chunk edits when the live cell no longer matches the inspected revision

Rules:
- Always run `inspect` immediately before `replace-chunks` on populated cells.
- Treat `chunk_id` values as ephemeral. They are valid only against the latest inspected state of that cell.
- Pass `--expected-revision` on all real edits so stale chunk IDs fail closed.
- Use `replace-chunks` for existing-cell edits; do not use `write_sheet.py`.
- Use `--stage` to store the edit in the active draft instead of applying it immediately.

Examples:

```bash
uv run --project ~/.codex/skills/google-sheets python ~/.codex/skills/google-sheets/scripts/change_cell.py inspect --spreadsheet "weekly tracker" --tab "Notes" --cell B4

uv run --project ~/.codex/skills/google-sheets python ~/.codex/skills/google-sheets/scripts/change_cell.py replace-chunks --spreadsheet "weekly tracker" --tab "Notes" --cell B4 --chunk-id c1 --chunk-id c2 --text "Updated" --expected-revision <revision> --dry-run

uv run --project ~/.codex/skills/google-sheets python ~/.codex/skills/google-sheets/scripts/change_cell.py replace-chunks --spreadsheet "weekly tracker" --tab "Notes" --cell B4 --chunk-id c1 --chunk-id c2 --text "Updated" --expected-revision <revision> --stage
```

Example with explicit replacement chunk formatting:

```bash
uv run --project ~/.codex/skills/google-sheets python ~/.codex/skills/google-sheets/scripts/change_cell.py replace-chunks --spreadsheet "weekly tracker" --tab "Notes" --cell B4 --chunk-id c2 --replacement-chunks-json '[{"text":"🚦","format":{"bold":true,"foregroundColor":{"red":0.1,"green":0.6,"blue":0.1}}}]' --expected-revision <revision>
```

Prefer this over `write_sheet.py` when:
- only part of one cell should change
- the cell may contain mixed formatting in one line
- the user explicitly wants a local patch instead of a full rewrite

### `change_bulk_cell.py`

Use this when the user wants to modify an existing populated range and the change spans multiple cells.

Capabilities:
- reread each exact target cell before editing
- accept only per-cell `replace_chunks` operations with chunk IDs from the latest inspect result
- compute a per-cell before/after chunk preview
- preview by default
- only apply when `--apply` is passed
- reject stale revision hashes and unknown chunk IDs
- block attempts to use it on empty target cells, which should use `write_sheet.py` instead

Rules:
- Inspect every populated target cell first and collect its `chunk_id` and `revision`.
- Use `change_bulk_cell.py` only for existing populated cells, never for empty fills.
- Keep each operation cell-specific. Do not pass range/value matrix payloads.
- Use preview mode first. Apply only after the chunk diff is correct.
- If any cell has changed since inspect, the whole batch should be treated as stale and re-inspected.
- Use `--stage` to store validated operations in the active draft instead of applying immediately.

Example:

```bash
uv run --project ~/.codex/skills/google-sheets python ~/.codex/skills/google-sheets/scripts/change_bulk_cell.py --spreadsheet "weekly tracker" --json '{"operations":[{"tab":"Sheet1","cell":"B3","action":"replace_chunks","expected_revision":"<revision>","chunk_ids":["c1"],"replacement_chunks":[{"text":"🚦"}]}]}'

uv run --project ~/.codex/skills/google-sheets python ~/.codex/skills/google-sheets/scripts/change_bulk_cell.py --spreadsheet "weekly tracker" --apply --json '{"operations":[{"tab":"Sheet1","cell":"B3","action":"replace_chunks","expected_revision":"<revision>","chunk_ids":["c1"],"replacement_chunks":[{"text":"🚦"}]}]}'

uv run --project ~/.codex/skills/google-sheets python ~/.codex/skills/google-sheets/scripts/change_bulk_cell.py --spreadsheet "weekly tracker" --stage --json '{"operations":[{"tab":"Sheet1","cell":"B3","action":"replace_chunks","expected_revision":"<revision>","chunk_ids":["c1"],"replacement_chunks":[{"text":"🚦"}]}]}'
```

Use this instead of ad hoc raw `batchUpdate` content rewrites. Existing populated multi-cell edits should be explicit, chunk-based, and intentional.

Example multi-cell payload with formatting-preserving chunk replacements:

```json
{
  "operations": [
    {
      "tab": "AMJ'26",
      "cell": "B3",
      "action": "replace_chunks",
      "expected_revision": "<revision-B3>",
      "chunk_ids": ["c2"],
      "replacement_chunks": [
        {"text": "🚦"}
      ]
    },
    {
      "tab": "AMJ'26",
      "cell": "C3",
      "action": "replace_chunks",
      "expected_revision": "<revision-C3>",
      "chunk_ids": ["c2", "c3"],
      "replacement_chunks": [
        {"text": "🌱"}
      ]
    }
  ]
}
```

Use `--stage` to add formatting operations to the active draft instead of applying them immediately.

### Draft Workflow

Example staged flow:

```bash
uv run --project ~/.codex/skills/google-sheets python ~/.codex/skills/google-sheets/scripts/draft.py create --spreadsheet "weekly tracker" --name "roadmap-copy"

uv run --project ~/.codex/skills/google-sheets python ~/.codex/skills/google-sheets/scripts/change_bulk_cell.py --spreadsheet "weekly tracker" --stage --json '{"operations":[{"tab":"AMJ'\''26","cell":"B3","action":"replace_chunks","expected_revision":"<revision-B3>","chunk_ids":["c2"],"replacement_chunks":[{"text":"🚦"}]}]}'

uv run --project ~/.codex/skills/google-sheets python ~/.codex/skills/google-sheets/scripts/format_sheet.py --spreadsheet "weekly tracker" --stage --json '{"operations":[{"type":"repeatCell","tab":"AMJ'\''26","range":"B3","format":{"textFormat":{"bold":true}},"fields":"userEnteredFormat.textFormat"}]}'

uv run --project ~/.codex/skills/google-sheets python ~/.codex/skills/google-sheets/scripts/draft.py show

uv run --project ~/.codex/skills/google-sheets python ~/.codex/skills/google-sheets/scripts/draft.py commit

uv run --project ~/.codex/skills/google-sheets python ~/.codex/skills/google-sheets/scripts/draft.py commit --apply
```

Conflict-aware commit:
- `draft.py commit` previews valid operations and conflicts.
- `draft.py commit --apply` applies only when there are no conflicts.
- `draft.py commit --apply-valid` applies only valid operations and leaves blocked ones staged.

Expected behavior:
- untouched chunks keep their exact formatting
- replacement chunks inherit the first replaced chunk's formatting unless an explicit `format` is provided
- stale revisions fail with a structured error and require re-inspection

### `format_sheet.py`

Apply formatting or layout changes with `spreadsheets.batchUpdate`. Supported v1 operations:
- `repeatCell` for text/background/alignment/number formatting on an A1 range
- `updateDimensionProperties` for row heights or column widths
- `updateSheetProperties` for frozen rows/columns or other sheet properties

Example:

```json
{
  "operations": [
    {
      "type": "repeatCell",
      "tab": "Codex Write Test",
      "range": "A1:B2",
      "format": {
        "backgroundColor": {"red": 0.96, "green": 0.96, "blue": 0.96},
        "textFormat": {"bold": true, "fontSize": 11}
      }
    }
  ]
}
```

## Guidance

- Treat every sheet as a matrix first. Headers may exist, but do not assume they do.
- Before attempting any write or formatting operation, reread the exact target tab/range first. Never rely on earlier reads or memory when the current sheet structure matters.
- Reread live sheet data when accuracy matters.
- Preserve untouched cells by writing only the intended ranges.
- Avoid bulk overwrites of existing populated cells. Treat `write_sheet.py` as fill-only.
- Do not use raw `spreadsheets.batchUpdate` or `values.batchUpdate` directly for populated multi-cell content rewrites when `change_bulk_cell.py` covers the need.
- For chunk-based edits, the correct sequence is always: `inspect` -> capture `chunk_id` and `revision` -> preview -> apply.
- For deferred edits, the correct sequence is: `draft create` -> inspect -> `--stage` edits -> `draft show` -> `draft commit`.
- `chunk_id` values are ephemeral selectors for the current inspected state, not persistent semantic IDs.
- For visual patterns or arbitrary layouts, compute the target cell grid explicitly, then write it.
- For formatting, prefer `format_sheet.py` after values are in place.
- For partial single-cell rewrites with mixed styling, prefer `change_cell.py` with chunk IDs over `write_sheet.py`.
- For populated multi-cell edits, prefer `change_bulk_cell.py` with chunk IDs over direct bulk rewrites.
- If the user says "my tracker" or similar and an alias exists, use it. If the reference is ambiguous, clarify before writing.
