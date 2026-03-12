# Predictor Analysis — Rocket Alert Settlement Data  (v2.0)

This tool reads a Telegram channel export (`result_filtered.json`) containing
Hebrew rocket-alert messages and produces two tables:

1. **Top N predictors by precision** — settlements whose alert most reliably
   precedes an alert for the target settlement within a 15–600 second window.
2. **Top K operational triggers** — a weighted score combining precision,
   lead-time quality, and volume.

---

## Requirements

- Python 3.8 or newer (no extra packages needed — standard library only)
- A Telegram export JSON file from the rocket-alert channel

---

## Quick Start (Windows PowerShell)

**Recommended — write directly to a UTF-8 file with `--output`:**

```powershell
cd "C:\Users\User\Downloads"
py analyze_predictors_en_safe.py --input result_filtered.json --target AUTO_BEIT_HAG --min-volume 20 --output output.txt
notepad output.txt
```

> Using `--output output.txt` writes a proper UTF-8 file directly,
> so Hebrew characters are always preserved correctly.
> No need to redirect with `>` at all.

**List all available settlements (to pick a custom `--target`):**

```powershell
py analyze_predictors_en_safe.py --input result_filtered.json --list-targets
```

---

## Command-line Arguments

| Argument | Default | Description |
|---|---|---|
| `--input` | *(required)* | Path to the Telegram export JSON file |
| `--target` | `AUTO_BEIT_HAG` | Target settlement. `AUTO_BEIT_HAG` auto-detects the Beit Hag settlement |
| `--start-date` | `2026-02-28` | Start date `YYYY-MM-DD` (default = start of current escalation) |
| `--end-date` | *(now)* | End date `YYYY-MM-DD` |
| `--min-volume` | `20` | Minimum alert count for a settlement to be considered |
| `--top-n` | `10` | Number of rows in Table 1 (precision table) |
| `--top-k` | `3` | Number of rows in Table 2 (operational triggers) |
| `--output FILE` | *(console)* | Write results to FILE in UTF-8 (recommended on Windows) |
| `--list-targets` | — | List all qualifying settlements and exit |
| `--force-check NAMES` | *(geo-priority)* | Comma-separated Hebrew names always included, even below `--min-volume`. Rows marked `*`. When target is `AUTO_BEIT_HAG`, the six geographic-priority settlements (להב, להבים, תנא עומרים, מעון, סנסנה, שמעה) are added automatically |
| `--hebrew` | — | Display settlement names in Hebrew instead of English |

---

## Expected JSON Format

The tool expects a standard Telegram channel export file:

```json
{
  "name": "...",
  "type": "public_channel",
  "id": 12345,
  "messages": [
    {
      "id": 1,
      "type": "message",
      "date": "2026-02-28T08:13:43",
      "text": ["...", {"type": "...", "text": "..."}],
      "text_entities": [{"type": "plain", "text": "..."}]
    }
  ]
}
```

---

## Error Handling

| Error message | Cause | Fix |
|---|---|---|
| `ERROR: Input file not found` | The JSON file path is wrong | Check spelling and directory |
| `ERROR: No rocket-alert settlement events found` | Date range too narrow, or messages don't match the expected format | Widen `--start-date` |
| `ERROR: Could not auto-detect a target` | No settlement containing the target keywords was found | Run with `--list-targets` to see options, then use `--target <name>` |

---

## Execution Environment Note

This script runs **entirely on your local machine**. The repository only stores
the script source code. The data file (`result_filtered.json`) is **never
uploaded** to the repository — it stays on your computer.

Copilot and GitHub Actions cannot execute this script against your local file
because the file only exists on your machine. Copy the script to the same
folder as `result_filtered.json` and run it with Python as shown above.
