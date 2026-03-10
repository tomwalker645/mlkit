#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Predictor Analysis Tool
=======================
Reads a Telegram channel export (result_filtered.json) containing Hebrew
rocket-alert messages, and finds which settlements are the best predictors
(by precision and operational score) for a target settlement.

Usage
-----
    py analyze_predictors_en_safe.py --input result_filtered.json \
        --target AUTO_BEIT_HAG --min-volume 20

Output
------
  - Top 10 settlements by precision (P(target|settlement fires first))
  - Top 3 operational triggers (weighted score of precision + lead-time + volume)
"""

import json
import os
import re
import sys
import math
import argparse
from collections import defaultdict
from datetime import datetime, timedelta
from bisect import bisect_left
from statistics import median

DEFAULT_START_DATE = "2026-02-28"
DEFAULT_TARGET = "AUTO_BEIT_HAG"
DEFAULT_MIN_VOLUME = 20
MIN_LEAD_SEC = 15
MAX_LEAD_SEC = 600

NON_ALERT_PATTERNS = [
    r"\u05de\u05d1\u05d6\u05e7",
    r"\u05d4\u05d9\u05e9\u05de\u05e2\u05d5 \u05dc\u05d4\u05e0\u05d7\u05d9\u05d5\u05ea",
    r"\u05d1\u05d3\u05e7\u05d5\u05ea \u05d4\u05e7\u05e8\u05d5\u05d1\u05d5\u05ea \u05e6\u05e4\u05d5\u05d9\u05d5\u05ea \u05dc\u05d4\u05ea\u05e7\u05d1\u05dc \u05d4\u05ea\u05e8\u05e2\u05d5\u05ea",
]

# Hebrew time-marker tokens used inside alert lines to identify settlement entries
TIME_MARKERS = [
    "\u05de\u05d9\u05d9\u05d3\u05d9",
    "15 \u05e9\u05e0\u05d9\u05d5\u05ea",
    "30 \u05e9\u05e0\u05d9\u05d5\u05ea",
    "45 \u05e9\u05e0\u05d9\u05d5\u05ea",
    "\u05d3\u05e7\u05d4",
    "\u05d3\u05e7\u05d4 \u05d5\u05d7\u05e6\u05d9",
    "2 \u05d3\u05e7\u05d5\u05ea",
    "3 \u05d3\u05e7\u05d5\u05ea",
]

# Phrase that marks a rocket/missile alert (Hebrew: "ירי רקטות וטילים")
ROCKET_PHRASE = "\u05d9\u05e8\u05d9 \u05e8\u05e7\u05d8\u05d5\u05ea \u05d5\u05d8\u05d9\u05dc\u05d9\u05dd"


def normalize_text(s: str) -> str:
    """Normalize a single settlement name: replace Hebrew quote chars, collapse spaces."""
    if not isinstance(s, str):
        return ""
    s = s.replace("\u05f4", '"').replace("\u05f3", "'")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_msg_text(s: str) -> str:
    """Normalize a full message body: replace Hebrew quote chars but preserve newlines."""
    if not isinstance(s, str):
        return ""
    s = s.replace("\u05f4", '"').replace("\u05f3", "'")
    # Collapse runs of spaces/tabs within each line, but keep newlines intact
    s = re.sub(r"[^\S\n]+", " ", s).strip()
    return s


def norm_key(s: str) -> str:
    s = normalize_text(s)
    s = s.replace('"', "").replace("'", "").replace("\u05f3", "").replace("\u05f4", "")
    return s


def to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def minute_bucket(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def contains_any_pattern(text: str, patterns) -> bool:
    return any(re.search(p, text) for p in patterns)


def flatten_text_field(text_field):
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


def message_full_text(msg):
    if isinstance(msg.get("text_entities"), list):
        parts = []
        for e in msg["text_entities"]:
            t = e.get("text", "")
            if isinstance(t, str):
                parts.append(t)
        txt = "".join(parts)
        if txt.strip():
            return normalize_msg_text(txt)
    return normalize_msg_text(flatten_text_field(msg.get("text", "")))


def is_rocket_alert(text: str) -> bool:
    return (ROCKET_PHRASE in text) and (not contains_any_pattern(text, NON_ALERT_PATTERNS))


def extract_settlements(text: str):
    settlements = set()
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    skip_prefixes = [
        "\u05d0\u05d6\u05d5\u05e8 ",          # "אזור "
        "\u05d4\u05d9\u05db\u05e0\u05e1\u05d5 \u05dc\u05de\u05e8\u05d7\u05d1 \u05d4\u05de\u05d5\u05d2\u05df",  # "היכנסו למרחב המוגן"
        "\u05d4\u05d0\u05d9\u05e8\u05d5\u05e2 \u05d4\u05e1\u05ea\u05d9\u05d9\u05dd",  # "האירוע הסתיים"
        "\u05d4\u05e9\u05d5\u05d4\u05d9\u05dd \u05d1\u05de\u05e8\u05d7\u05d1 \u05d4\u05de\u05d5\u05d2\u05df",  # "השוהים במרחב המוגן"
    ]
    skip_name_prefixes = [
        "\u05e2\u05dc \u05ea\u05d5\u05e9\u05d1\u05d9",   # "על תושבי"
        "\u05d1\u05de\u05e7\u05e8\u05d4 \u05e9\u05dc",   # "במקרה של"
        "\u05e2\u05d3\u05db\u05d5\u05df",                 # "עדכון"
    ]

    for ln in lines:
        if ROCKET_PHRASE in ln:
            continue
        if any(ln.startswith(p) for p in skip_prefixes):
            continue

        candidates = re.split(r"\)\s*", ln)
        for c in candidates:
            if "(" not in c:
                continue
            left, right = c.rsplit("(", 1)
            right = right.strip()
            if any(tm in right for tm in TIME_MARKERS):
                for name in left.split(","):
                    n = normalize_text(name)
                    n = re.sub(r"^-+\s*", "", n)
                    n = re.sub(r"\s*-\s*$", "", n)
                    if not n:
                        continue
                    if any(n.startswith(p) for p in skip_name_prefixes):
                        continue
                    settlements.add(n)
    return settlements


def build_events(messages, start_dt, end_dt):
    events_by_settlement = defaultdict(list)
    dedup = set()

    for msg in messages:
        if msg.get("type") != "message":
            continue
        ds = msg.get("date")
        if not ds:
            continue
        dt = to_dt(ds)
        if dt < start_dt or dt > end_dt:
            continue

        text = message_full_text(msg)
        if not text or not is_rocket_alert(text):
            continue

        settlements = extract_settlements(text)
        if not settlements:
            continue

        mb = minute_bucket(dt)
        for s in settlements:
            sk = norm_key(s)
            key = (sk, mb)
            if key in dedup:
                continue
            dedup.add(key)
            events_by_settlement[sk].append(dt)

    for s in events_by_settlement:
        events_by_settlement[s].sort()
    return events_by_settlement


def compute_predictor_stats(events_by_settlement, target_key, min_volume):
    if target_key not in events_by_settlement:
        raise ValueError(f'Target not found: "{target_key}"')

    target_times = sorted(events_by_settlement[target_key])
    target_count = len(target_times)
    results = []

    for settlement, times in events_by_settlement.items():
        if settlement == target_key:
            continue
        total = len(times)
        if total < min_volume:
            continue

        lead_seconds_list = []
        success = 0

        for t in times:
            lo = t + timedelta(seconds=MIN_LEAD_SEC)
            hi = t + timedelta(seconds=MAX_LEAD_SEC)
            i = bisect_left(target_times, lo)
            if i < len(target_times) and target_times[i] <= hi:
                success += 1
                lead_seconds_list.append((target_times[i] - t).total_seconds())

        precision = success / total if total else 0.0

        hit_target_given_settlement = 0
        for th in target_times:
            lo = th - timedelta(seconds=MAX_LEAD_SEC)
            hi = th - timedelta(seconds=MIN_LEAD_SEC)
            j = bisect_left(times, lo)
            if j < len(times) and times[j] <= hi:
                hit_target_given_settlement += 1

        p_settlement_given_target = hit_target_given_settlement / target_count if target_count else 0.0
        avg_lead = sum(lead_seconds_list) / len(lead_seconds_list) if lead_seconds_list else math.nan
        med_lead = median(lead_seconds_list) if lead_seconds_list else math.nan

        results.append({
            "settlement": settlement,
            "total_events": total,
            "success_count": success,
            "precision": precision,
            "avg_lead_sec": avg_lead,
            "med_lead_sec": med_lead,
            "p_settlement_given_target": p_settlement_given_target,
        })

    results.sort(key=lambda x: (x["precision"], x["total_events"]), reverse=True)
    return results, target_count


def format_lead(sec):
    if sec is None or (isinstance(sec, float) and math.isnan(sec)):
        return "-"
    m = int(sec // 60)
    s = int(round(sec % 60))
    return f"{s}s" if m == 0 else f"{m}m {s}s"


def pct(x):
    return f"{x * 100:.1f}%"


def pick_top_operational(rows, k=3):
    scored = []
    for r in rows:
        if math.isnan(r["avg_lead_sec"]):
            continue
        precision_score = r["precision"]
        volume_score = min(1.0, math.log1p(r["total_events"]) / math.log1p(200))
        lead = r["avg_lead_sec"]
        lead_score = math.exp(-((lead - 150.0) ** 2) / (2 * (90.0 ** 2)))
        score = 0.55 * precision_score + 0.25 * lead_score + 0.20 * volume_score
        rr = dict(r)
        rr["operational_score"] = score
        scored.append(rr)
    scored.sort(key=lambda x: x["operational_score"], reverse=True)
    return scored[:k]


def auto_pick_target(events_by_settlement):
    beit = "\u05d1\u05d9\u05ea"   # "בית"
    hag = "\u05d7\u05d2"           # "חג"
    cands = [k for k in events_by_settlement.keys() if (beit in k and hag in k)]
    if not cands:
        return None
    cands.sort(key=lambda k: len(events_by_settlement.get(k, [])), reverse=True)
    return cands[0]


def print_safe(text):
    """Print text, falling back to ASCII-safe output on narrow Windows consoles."""
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))


def main():
    parser = argparse.ArgumentParser(
        description="Analyze rocket alert Telegram export and find settlement predictors."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the Telegram export JSON file (e.g. result_filtered.json)",
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help="Target settlement name. Use AUTO_BEIT_HAG for auto-detect (default).",
    )
    parser.add_argument(
        "--start-date",
        default=DEFAULT_START_DATE,
        help=f"Start date in YYYY-MM-DD format (default: {DEFAULT_START_DATE})",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="End date in YYYY-MM-DD format (default: now)",
    )
    parser.add_argument(
        "--min-volume",
        type=int,
        default=DEFAULT_MIN_VOLUME,
        help=f"Minimum alert count per settlement to include in analysis (default: {DEFAULT_MIN_VOLUME})",
    )
    args = parser.parse_args()

    # Robust missing-file handling
    if not os.path.isfile(args.input):
        print(f"ERROR: Input file not found: {args.input}")
        print()
        print("Make sure your Telegram export file is in the current directory, then run:")
        print(f"  py analyze_predictors_en_safe.py --input result_filtered.json --min-volume {args.min_volume}")
        sys.exit(1)

    start_dt = datetime.fromisoformat(args.start_date + "T00:00:00")
    end_dt = datetime.fromisoformat(args.end_date + "T23:59:59") if args.end_date else datetime.now()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict) or "messages" not in data:
        print("ERROR: Unexpected JSON structure. Expected a dict with a 'messages' key.")
        if isinstance(data, dict):
            print("  Top-level keys found:", list(data.keys()))
        else:
            print("  Top-level type:", type(data).__name__)
        sys.exit(1)

    messages = data["messages"]
    print(f"Loaded {len(messages)} messages from {args.input}")

    events_by_settlement = build_events(messages, start_dt, end_dt)

    if not events_by_settlement:
        print("ERROR: No rocket-alert settlement events found in the given date range.")
        print(f"  Date range: {start_dt} .. {end_dt}")
        print("  Try widening --start-date or removing --end-date.")
        sys.exit(1)

    if args.target == "AUTO_BEIT_HAG":
        target_key = auto_pick_target(events_by_settlement)
        if not target_key:
            beit = "\u05d1\u05d9\u05ea"
            hag = "\u05d7\u05d2"
            print("ERROR: Could not auto-detect a target containing both relevant Hebrew words.")
            cands = [k for k in sorted(events_by_settlement.keys()) if beit in k or hag in k]
            if cands:
                print("Settlements with partial match (use --target <name>):")
                for k in cands[:20]:
                    print_safe(f"  - {k}")
            sys.exit(1)
        print_safe(f"AUTO target selected: {target_key}")
    else:
        target_key = norm_key(args.target)

    if target_key not in events_by_settlement:
        beit = "\u05d1\u05d9\u05ea"
        hag = "\u05d7\u05d2"
        print_safe(f'ERROR: target not found after normalization: "{target_key}"')
        cands = [k for k in sorted(events_by_settlement.keys()) if beit in k and hag in k]
        if cands:
            print("Candidates (use --target <name>):")
            for k in cands:
                print_safe(f"  - {k}")
        sys.exit(1)

    rows, target_count = compute_predictor_stats(events_by_settlement, target_key, args.min_volume)
    top10 = rows[:10]
    recs = pick_top_operational(top10, 3)

    print()
    print("=== Predictor Analysis ===")
    print_safe(f"Target         : {target_key}")
    print(f"Target events  : {target_count}")
    print(f"Date range     : {start_dt} .. {end_dt}")
    print(f"Min volume     : {args.min_volume}")
    print(f"Window         : {MIN_LEAD_SEC}s .. {MAX_LEAD_SEC}s")
    print()

    # Table 1 - Top 10 by precision
    print("--- Table 1: Top 10 Predictors by Precision ---")
    print(
        f"{'#':<3}  {'Settlement':<35}  {'Total':>5}  "
        f"{'Precision':>9}  {'Avg Lead':>8}  {'Med Lead':>8}  "
        f"{'P(sett|tgt)':>11}  {'Hits/Total':>10}"
    )
    print("-" * 100)
    for i, r in enumerate(top10, 1):
        print_safe(
            f"{i:<3}  {r['settlement']:<35}  {r['total_events']:>5}  "
            f"{pct(r['precision']):>9}  {format_lead(r['avg_lead_sec']):>8}  "
            f"{format_lead(r['med_lead_sec']):>8}  {pct(r['p_settlement_given_target']):>11}  "
            f"{r['success_count']}/{r['total_events']}"
        )

    print()
    # Table 2 - Top 3 operational triggers
    print("--- Table 2: Top 3 Operational Triggers ---")
    if not recs:
        print("No recommendations (insufficient lead-time data).")
    else:
        for i, r in enumerate(recs, 1):
            print_safe(
                f"{i}) {r['settlement']}  |  "
                f"precision={pct(r['precision'])}  |  "
                f"avg_lead={format_lead(r['avg_lead_sec'])}  |  "
                f"total={r['total_events']}  |  "
                f"score={r['operational_score']:.3f}"
            )


if __name__ == "__main__":
    main()
