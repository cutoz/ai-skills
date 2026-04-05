# AI Skills

Open-source Codex skills published under the repository's Apache license.

## Available skills

### `google-sheets`

Google Sheets read/write automation for Codex with:
- OAuth-based access to live Google Sheets
- alias and lightweight context memory
- empty-cell fills through `write_sheet.py`
- chunk-ID-based rich-text editing for existing populated cells
- draft and commit workflow for staging multiple changes locally before pushing to Google

The skill lives in [google-sheets/SKILL.md](google-sheets/SKILL.md).

## Install

Use the Codex skill installer against this repo:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo cutoz/ai-skills \
  --path google-sheets
```

Then restart Codex and configure Google OAuth:

```bash
uv run --project ~/.codex/skills/google-sheets python ~/.codex/skills/google-sheets/scripts/auth.py configure --client-secret /absolute/path/client_secret.json
uv run --project ~/.codex/skills/google-sheets python ~/.codex/skills/google-sheets/scripts/auth.py login
```

## Usage model

Use the skill commands according to the data state:

- `write_sheet.py`: fill empty cells only
- `change_cell.py`: edit one populated cell with chunk IDs
- `change_bulk_cell.py`: edit multiple populated cells with chunk IDs
- `format_sheet.py`: formatting and layout changes
- `draft.py`: stage and commit local drafts

For populated existing-cell content edits:
- direct `values.batchUpdate` rewrites are prohibited
- direct ad hoc `spreadsheets.batchUpdate` content rewrites are prohibited
- use `change_cell.py` or `change_bulk_cell.py` only

## Tests

Run the lightweight unit tests with:

```bash
cd google-sheets
uv run python -m unittest discover -s tests -p 'test_*.py'
```
