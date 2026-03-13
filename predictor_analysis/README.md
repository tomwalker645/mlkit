# Predictor Analysis — Rocket Alert Settlement Data  (v2.3)

This tool reads a Telegram channel export (`result_filtered.json`) containing
Hebrew rocket-alert messages and finds which settlements are the best predictors
for a target settlement.

---

## ⭐ Single-File Option: Download ONE file and you're done

**`predictor_browser_standalone.html`** — the data is already embedded inside the HTML.
No separate JSON file needed. Just download, open, and click Analyze.

1. Download `predictor_browser_standalone.html` from this folder (click **Raw**, then **Ctrl+S**)
2. Double-click it to open in your browser
3. Click **"🔍 נתח עכשיו"** — results appear immediately, no file loading needed

> To regenerate this file after updating `result_filtered.json`, run:
> ```
> python build_standalone.py
> ```

---

## 🌐 Two-File Option: Browser Tool with separate data file

**`predictor_browser.html`** — use this if you have a fresh `result_filtered.json`
that is newer than what is embedded in the standalone file above.

1. Download `predictor_browser.html` to the **same directory** as your `result_filtered.json`
2. Double-click `predictor_browser.html` to open it in your browser
3. Drag your `result_filtered.json` onto the drop zone (or click "בחר קובץ")
4. Click **"🔍 נתח עכשיו"** — results appear as color-coded cards with plain-Hebrew decision sentences

---

## 🐍 Python CLI Tool (advanced)

For plain-text, CSV-style output, or scripted/automated use, the Python script
`analyze_predictors_en_safe.py` provides full control via command-line flags.

## ⚠️ Make Sure You Have the Latest Version

> If you see `unrecognized arguments: --range`, `unrecognized arguments: --html`,
> `unrecognized arguments: --output`, or `unrecognized arguments: --hebrew`,
> **you are running an old copy of the script**.
> Download the latest `analyze_predictors_en_safe.py` from this repository and replace
> your local copy before running any commands.

**To check which version you have:**

```powershell
py analyze_predictors_en_safe.py --version
# Should print: analyze_predictors_en_safe.py v2.3 (or newer)
```

If the `--version` flag itself is not recognized, your copy is older than v2.0 — download the latest file from the repository.

---

## Requirements

- Python 3.8 or newer (no extra packages needed — standard library only)
- A Telegram export JSON file from the rocket-alert channel

---

## Quick Start (Windows PowerShell)

**Plain text — write directly to a UTF-8 file with `--output`:**

```powershell
cd "C:\Users\User\Downloads"
py analyze_predictors_en_safe.py --input result_filtered.json --target AUTO_BEIT_HAG --min-volume 20 --output output.txt
notepad output.txt
```

**Styled HTML table (opens in any browser):**

```powershell
py analyze_predictors_en_safe.py --input result_filtered.json --target AUTO_BEIT_HAG --html --output top10.html
start top10.html
```

**Range-1 settlements (close-range group) as styled HTML:**

```powershell
py analyze_predictors_en_safe.py --input result_filtered.json --target AUTO_BEIT_HAG --range 1 --html --output range1.html
start range1.html
```

**Range-2 settlements (mid-range group) as styled HTML:**

```powershell
py analyze_predictors_en_safe.py --input result_filtered.json --target AUTO_BEIT_HAG --range 2 --html --output range2.html
start range2.html
```

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
| `--output FILE` | *(console / output.html)* | Write results to FILE in UTF-8 (recommended on Windows) |
| `--list-targets` | — | List all qualifying settlements and exit |
| `--range N` | — | Pre-defined settlement group to force-check: **1** = close range (להבים, סנסנה, גבעות בר, אתר דודאים, עומר), **2** = mid range (אשתמוע, כרמל, מעון, שמעה, להב, תנא עומרים). Can be combined with `--force-check` |
| `--force-check NAMES` | *(geo-priority)* | Comma-separated Hebrew names always included, even below `--min-volume`. Rows marked `★`. When target is `AUTO_BEIT_HAG`, the six geographic-priority settlements (להב, להבים, תנא עומרים, מעון, סנסנה, שמעה) are added automatically |
| `--hebrew` | — | Display settlement names in Hebrew instead of English |
| `--html` | — | Generate a self-contained styled HTML table instead of plain text. Defaults to `output.html` if `--output` is not given. Includes a **Decision sentence** column |

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
| `unrecognized arguments: --range` | You are running an old copy of the script | Download the latest `analyze_predictors_en_safe.py` from this repository and replace your local copy |
| `unrecognized arguments: --html` | Same as above — old version | Download the latest version (v2.3+) |
| `unrecognized arguments: --output` | Same as above — old version | Download the latest version (v2.3+) |
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
