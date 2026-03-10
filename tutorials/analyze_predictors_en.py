#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_predictors_en.py
------------------------
Reads a Telegram-export JSON file and produces a tabular predictor analysis
showing which settlements' rocket alerts best predict an alert for a target
settlement within a configurable time window.

Encoding-safe: all output uses only ASCII characters and Latin-1-safe symbols
so it renders correctly in Windows PowerShell (cp1252/cp850) as well as in
terminals configured for UTF-8.  The input file is always read as UTF-8.

Usage
-----
  python analyze_predictors_en.py --input result_filtered.json
  python analyze_predictors_en.py --input result_filtered.json --target AUTO_BEIT_HAG
  python analyze_predictors_en.py --input result_filtered.json --target "Beit Haggai" --min-volume 10
  python analyze_predictors_en.py --input result_filtered.json --start-date 2024-01-01 --end-date 2024-06-01

Arguments
---------
  --input        Path to the JSON export file (required).
  --target       Target settlement name or AUTO_BEIT_HAG for auto-detection
                 (default: AUTO_BEIT_HAG).
  --start-date   Earliest date to include, YYYY-MM-DD.
                 Adjust to match your data's date range (default: 2026-02-28).
  --end-date     Latest date to include, YYYY-MM-DD (default: today).
  --min-volume   Minimum alert count a settlement must have to be considered
                 (default: 20).
"""

import json
import re
import math
import sys
import argparse
import os
from collections import defaultdict
from datetime import datetime, timedelta
from bisect import bisect_left
from statistics import median

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_START_DATE = "2026-02-28"
DEFAULT_TARGET = "AUTO_BEIT_HAG"
DEFAULT_MIN_VOLUME = 20
MIN_LEAD_SEC = 15
MAX_LEAD_SEC = 600

NON_ALERT_PATTERNS = [
    r"\u05de\u05d1\u05d6\u05e7",                              # מבזק
    r"\u05d4\u05d9\u05e9\u05de\u05e2\u05d5 \u05dc\u05d4\u05e0\u05d7\u05d9\u05d5\u05ea",  # הישמעו להנחיות
    r"\u05d1\u05d3\u05e7\u05d5\u05ea \u05d4\u05e7\u05e8\u05d5\u05d1\u05d5\u05ea",        # בדקות הקרובות
]

# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def normalize_text(s):
    """Normalize whitespace and common Hebrew typographic quote characters."""
    if not isinstance(s, str):
        return ""
    s = s.replace("\u05f4", '"').replace("\u05f3", "'")  # ״ -> " , ׳ -> '
    s = re.sub(r"\s+", " ", s).strip()
    return s


def norm_key(s):
    """Return a comparison key that ignores quote-like characters."""
    s = normalize_text(s)
    return s.replace('"', "").replace("'", "").replace("\u05f3", "").replace("\u05f4", "")


def flatten_text_field(text_field):
    """Flatten Telegram text field (str or list of str/dict) to plain string."""
    if isinstance(text_field, str):
        return text_field
    if isinstance(text_field, list):
        parts = []
        for item in text_field:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                t = item.get("text", "")
                if isinstance(t, str):
                    parts.append(t)
        return "".join(parts)
    return ""


def normalize_quotes(s):
    """Normalize only typographic quote characters, preserving newlines."""
    if not isinstance(s, str):
        return ""
    return s.replace("\u05f4", '"').replace("\u05f3", "'")  # ״ -> " , ׳ -> '


def message_full_text(msg):
    """Extract the full plain text from a Telegram message dict.

    Newlines are preserved so that extract_settlements() can split by line.
    """
    if isinstance(msg.get("text_entities"), list):
        parts = [e.get("text", "") for e in msg["text_entities"] if isinstance(e.get("text", ""), str)]
        txt = "".join(parts)
        if txt.strip():
            return normalize_quotes(txt)
    return normalize_quotes(flatten_text_field(msg.get("text", "")))


def contains_any_pattern(text, patterns):
    return any(re.search(p, text) for p in patterns)


def is_rocket_alert(text):
    """Return True if the message is a rocket/missile alert."""
    # Hebrew: ירי רקטות וטילים
    return (
        "\u05d9\u05e8\u05d9 \u05e8\u05e7\u05d8\u05d5\u05ea \u05d5\u05d8\u05d9\u05dc\u05d9\u05dd" in text
        and not contains_any_pattern(text, NON_ALERT_PATTERNS)
    )


def extract_settlements(text):
    """Parse settlement names and their response-time windows from an alert message."""
    settlements = set()
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    # Hebrew time-marker suffixes that appear inside parentheses
    time_markers = [
        "\u05de\u05d9\u05d9\u05d3\u05d9",       # מיידי
        "15 \u05e9\u05e0\u05d9\u05d5\u05ea",    # 15 שניות
        "30 \u05e9\u05e0\u05d9\u05d5\u05ea",    # 30 שניות
        "45 \u05e9\u05e0\u05d9\u05d5\u05ea",    # 45 שניות
        "\u05d3\u05e7\u05d4",                    # דקה
        "\u05d3\u05e7\u05d4 \u05d5\u05d7\u05e6\u05d9",  # דקה וחצי
        "2 \u05d3\u05e7\u05d5\u05ea",           # 2 דקות
        "3 \u05d3\u05e7\u05d5\u05ea",           # 3 דקות
    ]

    skip_prefixes = [
        "\U0001f6a8",                            # 🚨
        "\u05d9\u05e8\u05d9 \u05e8\u05e7\u05d8\u05d5\u05ea",   # ירי רקטות
        "\u05d0\u05d6\u05d5\u05e8 ",            # אזור
        "\u05d4\u05d9\u05db\u05e0\u05e1\u05d5",  # היכנסו
    ]

    for ln in lines:
        if any(ln.startswith(p) for p in skip_prefixes):
            continue

        for chunk in re.split(r"\)\s*", ln):
            if "(" not in chunk:
                continue
            left, right = chunk.rsplit("(", 1)
            right = right.strip()
            if any(tm in right for tm in time_markers):
                for name in left.split(","):
                    n = normalize_text(name)
                    n = re.sub(r"^-+\s*", "", n).rstrip(" -")
                    if not n:
                        continue
                    # Skip boilerplate Hebrew phrases
                    if n.startswith("\u05e2\u05dc \u05ea\u05d5\u05e9\u05d1\u05d9"):  # על תושבי
                        continue
                    if n.startswith("\u05d1\u05de\u05e7\u05e8\u05d4 \u05e9\u05dc"):  # במקרה של
                        continue
                    settlements.add(n)
    return settlements


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def build_events(messages, start_dt, end_dt):
    """Return dict mapping normalised settlement key -> sorted list[datetime]."""
    events = defaultdict(list)
    dedup = set()

    for msg in messages:
        if msg.get("type") != "message":
            continue
        ds = msg.get("date")
        if not ds:
            continue
        try:
            dt = datetime.fromisoformat(ds)
        except ValueError:
            continue
        if dt < start_dt or dt > end_dt:
            continue

        text = message_full_text(msg)
        if not text or not is_rocket_alert(text):
            continue

        settlements = extract_settlements(text)
        if not settlements:
            continue

        mb = dt.replace(second=0, microsecond=0)  # minute bucket for dedup
        for s in settlements:
            sk = norm_key(s)
            token = (sk, mb)
            if token in dedup:
                continue
            dedup.add(token)
            events[sk].append(dt)

    for s in events:
        events[s].sort()
    return events


def compute_predictor_stats(events, target_key, min_volume):
    """
    For each settlement with >= min_volume events, compute:
      - precision  = P(target alert within window | settlement alert)
      - recall     = P(settlement appears before target alert)
      - avg/median lead time in seconds
    Returns (rows, target_count).
    """
    if target_key not in events:
        raise ValueError(f'Target key not found: "{target_key}"')

    target_times = events[target_key]
    target_count = len(target_times)
    rows = []

    for s, times in events.items():
        if s == target_key:
            continue
        total = len(times)
        if total < min_volume:
            continue

        leads = []
        success = 0
        for t in times:
            lo = t + timedelta(seconds=MIN_LEAD_SEC)
            hi = t + timedelta(seconds=MAX_LEAD_SEC)
            i = bisect_left(target_times, lo)
            if i < len(target_times) and target_times[i] <= hi:
                success += 1
                leads.append((target_times[i] - t).total_seconds())

        precision = success / total if total else 0.0

        # How often does this settlement appear before any target event?
        recall_hits = 0
        for th in target_times:
            lo = th - timedelta(seconds=MAX_LEAD_SEC)
            hi = th - timedelta(seconds=MIN_LEAD_SEC)
            j = bisect_left(times, lo)
            if j < len(times) and times[j] <= hi:
                recall_hits += 1

        recall = recall_hits / target_count if target_count else 0.0
        avg_lead = sum(leads) / len(leads) if leads else math.nan
        med_lead = median(leads) if leads else math.nan

        rows.append({
            "settlement": s,
            "total": total,
            "success": success,
            "precision": precision,
            "avg_lead": avg_lead,
            "med_lead": med_lead,
            "recall": recall,
        })

    rows.sort(key=lambda r: (r["precision"], r["total"]), reverse=True)
    return rows, target_count


def pick_top_operational(rows, k=3):
    """Score rows by a weighted combination of precision, lead-time, and volume."""
    scored = []
    for r in rows:
        if math.isnan(r["avg_lead"]):
            continue
        p_score = r["precision"]
        v_score = min(1.0, math.log1p(r["total"]) / math.log1p(200))
        lead = r["avg_lead"]
        l_score = math.exp(-((lead - 150.0) ** 2) / (2 * (90.0 ** 2)))
        score = 0.55 * p_score + 0.25 * l_score + 0.20 * v_score
        rr = dict(r)
        rr["op_score"] = score
        scored.append(rr)
    scored.sort(key=lambda r: r["op_score"], reverse=True)
    return scored[:k]


def auto_pick_target(events):
    """Return the key matching settlements that contain both *beit* and *hag*."""
    # Hebrew roots: בית (beit) and חג (hag)
    cands = [k for k in events if "\u05d1\u05d9\u05ea" in k and "\u05d7\u05d2" in k]
    if not cands:
        return None
    cands.sort(key=lambda k: len(events[k]), reverse=True)
    return cands[0]


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_lead(sec):
    if sec is None or (isinstance(sec, float) and math.isnan(sec)):
        return "    -   "
    m, s = divmod(int(round(sec)), 60)
    return f"{s}s" if m == 0 else f"{m}m {s:02d}s"


def pct(x):
    return f"{x * 100:5.1f}%"


def print_table(rows, target_key, target_count, start_dt, end_dt, min_volume):
    """Print a clean ASCII table to stdout (encoding-safe)."""
    # Column widths (between the | pipes, including 1-space padding each side):
    # Settlement(32), Total(8), Precision(11), Avg lead(10), Med lead(10), Recall(9), Success/Total(15)
    sep = (
        "+" + "-" * 32 + "+" + "-" * 8 + "+" + "-" * 11 + "+"
        + "-" * 10 + "+" + "-" * 10 + "+" + "-" * 9 + "+" + "-" * 15 + "+"
    )
    hdr = (
        f"| {'Settlement key':<30} | {'Total':>6} | {'Precision':>9} "
        f"| {'Avg lead':>8} | {'Med lead':>8} | {'Recall':>7} | {'Success/Total':>13} |"
    )

    print("=" * 80)
    print(" Predictor Analysis")
    print("=" * 80)
    print(f" Date range : {start_dt.date()} .. {end_dt.date()}")
    print(f" Target key : {target_key}")
    print(f" Target cnt : {target_count} events (deduplicated to minute)")
    print(f" Window     : {MIN_LEAD_SEC}s .. {MAX_LEAD_SEC}s lead time")
    print(f" Min volume : {min_volume}")
    print()

    print("Top 10 settlements by precision:")
    print(sep)
    print(hdr)
    print(sep)
    for r in rows[:10]:
        s = r["settlement"]
        if len(s) > 30:
            s = s[:27] + "..."
        print(
            f"| {s:<30} | {r['total']:>6} | {pct(r['precision']):>9} "
            f"| {fmt_lead(r['avg_lead']):>8} | {fmt_lead(r['med_lead']):>8} "
            f"| {pct(r['recall']):>7} | {r['success']:>6}/{r['total']:<6} |"
        )
    print(sep)

    top3 = pick_top_operational(rows[:10], 3)
    print()
    print("Top 3 operational triggers (weighted score):")
    if not top3:
        print("  No recommendations (insufficient lead-time data).")
    else:
        for i, r in enumerate(top3, 1):
            print(
                f"  {i}) {r['settlement']}"
                f"  |  precision={pct(r['precision'])}"
                f"  |  avg_lead={fmt_lead(r['avg_lead'])}"
                f"  |  total={r['total']}"
                f"  |  score={r['op_score']:.3f}"
            )
    print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Analyse a Telegram JSON export to find which settlements best "
            "predict rocket alerts for a target settlement."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        metavar="FILE",
        help="Path to the JSON export file (e.g. result_filtered.json). Required.",
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        metavar="NAME",
        help=(
            "Target settlement name or AUTO_BEIT_HAG to auto-detect. "
            f"Default: {DEFAULT_TARGET}"
        ),
    )
    parser.add_argument(
        "--start-date",
        default=DEFAULT_START_DATE,
        metavar="YYYY-MM-DD",
        help=f"Earliest date to include. Default: {DEFAULT_START_DATE}",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Latest date to include. Default: today.",
    )
    parser.add_argument(
        "--min-volume",
        type=int,
        default=DEFAULT_MIN_VOLUME,
        metavar="N",
        help=f"Minimum alert count per settlement. Default: {DEFAULT_MIN_VOLUME}",
    )
    args = parser.parse_args()

    # ---- Validate input file -----------------------------------------------
    if not os.path.isfile(args.input):
        print(f"ERROR: Input file not found: {args.input}", file=sys.stderr)
        print(
            "Please provide the correct path with --input, e.g.:\n"
            "  python analyze_predictors_en.py --input C:\\Users\\User\\Downloads\\result_filtered.json",
            file=sys.stderr,
        )
        sys.exit(1)

    # ---- Parse dates --------------------------------------------------------
    try:
        start_dt = datetime.fromisoformat(args.start_date + "T00:00:00")
    except ValueError:
        print(f"ERROR: Invalid --start-date: {args.start_date} (expected YYYY-MM-DD)", file=sys.stderr)
        sys.exit(1)

    if args.end_date:
        try:
            end_dt = datetime.fromisoformat(args.end_date + "T23:59:59")
        except ValueError:
            print(f"ERROR: Invalid --end-date: {args.end_date} (expected YYYY-MM-DD)", file=sys.stderr)
            sys.exit(1)
    else:
        end_dt = datetime.now()

    # ---- Load JSON ----------------------------------------------------------
    try:
        with open(args.input, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Failed to parse JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    messages = data.get("messages", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    if not messages:
        print("ERROR: No messages found in the JSON file.", file=sys.stderr)
        print(
            "Expected a Telegram export with a top-level 'messages' list, "
            "or a bare JSON array of message objects.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ---- Build event index --------------------------------------------------
    events = build_events(messages, start_dt, end_dt)

    if not events:
        print("ERROR: No parsed rocket-alert events found in the specified date range.", file=sys.stderr)
        print(f"  Date range : {start_dt.date()} .. {end_dt.date()}", file=sys.stderr)
        print(
            "Try widening --start-date / --end-date, or check that the file "
            "contains Hebrew rocket-alert messages.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ---- Resolve target -----------------------------------------------------
    if args.target == "AUTO_BEIT_HAG":
        target_key = auto_pick_target(events)
        if not target_key:
            print("ERROR: Auto-detection failed — no settlement key contains both beit (בית) and hag (חג).", file=sys.stderr)
            print("Sample settlement keys:", file=sys.stderr)
            for k in sorted(events.keys())[:40]:
                print(f"  - {k}", file=sys.stderr)
            sys.exit(1)
        print(f"[Auto-detected target: {target_key}]")
    else:
        target_key = norm_key(args.target)

    if target_key not in events:
        print(f'ERROR: Target not found after normalisation: "{target_key}"', file=sys.stderr)
        # Show helpful candidates
        beit_hag_cands = [k for k in sorted(events.keys()) if "\u05d1\u05d9\u05ea" in k and "\u05d7\u05d2" in k]
        if beit_hag_cands:
            print("Candidate keys containing beit+hag:", file=sys.stderr)
            for k in beit_hag_cands:
                print(f"  - {k}", file=sys.stderr)
        else:
            print("No candidate keys found. Sample keys:", file=sys.stderr)
            for k in sorted(events.keys())[:40]:
                print(f"  - {k}", file=sys.stderr)
        sys.exit(1)

    # ---- Compute & display --------------------------------------------------
    rows, target_count = compute_predictor_stats(events, target_key, args.min_volume)
    print_table(rows, target_key, target_count, start_dt, end_dt, args.min_volume)


if __name__ == "__main__":
    main()
