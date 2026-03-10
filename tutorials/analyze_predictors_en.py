#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_predictors_en.py
------------------------
Analyze rocket-alert Telegram export (result_filtered.json) and generate
a predictor table showing which settlements precede a target settlement
within a configurable time window.

Usage (Windows PowerShell):
    py analyze_predictors_en.py --input result_filtered.json --target AUTO_BEIT_HAG --min-volume 20 > output_en.txt 2>&1
    type output_en.txt

Requirements:
    Python 3.8+, standard library only.

JSON format expected:
    { "name": "...", "type": "...", "id": ..., "messages": [ ... ] }
    Each message: { "id", "type", "date", "text": str | list, "text_entities": list, ... }
"""

import json
import re
import math
import argparse
import sys
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
    r"מבזק",
    r"הישמעו להנחיות",
    r"בדקות הקרובות צפויות להתקבל התרעות",
]


def normalize_text(s):
    if not isinstance(s, str):
        return ""
    s = s.replace("\u05f4", '"').replace("\u05f3", "'")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def norm_key(s):
    s = normalize_text(s)
    s = s.replace('"', "").replace("'", "").replace("\u05f3", "").replace("\u05f4", "")
    return s


def to_dt(s):
    return datetime.fromisoformat(s)


def minute_bucket(dt):
    return dt.replace(second=0, microsecond=0)


def contains_any_pattern(text, patterns):
    return any(re.search(p, text) for p in patterns)


def flatten_text_field(text_field):
    """Convert text field (str or list of str/dict) to a single string."""
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


def message_raw_text(msg):
    """Extract raw text of a message (preserving newlines), preferring text_entities."""
    if isinstance(msg.get("text_entities"), list):
        parts = []
        for e in msg["text_entities"]:
            t = e.get("text", "")
            if isinstance(t, str):
                parts.append(t)
        txt = "".join(parts)
        if txt.strip():
            return txt
    return flatten_text_field(msg.get("text", ""))


def message_full_text(msg):
    """Extract normalized full text (newlines collapsed) for keyword checks."""
    return normalize_text(message_raw_text(msg))


def is_rocket_alert(text):
    return ("\u05d9\u05e8\u05d9 \u05e8\u05e7\u05d8\u05d5\u05ea \u05d5\u05d8\u05d9\u05dc\u05d9\u05dd" in text) and (
        not contains_any_pattern(text, NON_ALERT_PATTERNS)
    )


def extract_settlements(text):
    settlements = set()
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    time_markers = [
        "\u05de\u05d9\u05d9\u05d3\u05d9",
        "15 \u05e9\u05e0\u05d9\u05d5\u05ea",
        "30 \u05e9\u05e0\u05d9\u05d5\u05ea",
        "45 \u05e9\u05e0\u05d9\u05d5\u05ea",
        "\u05d3\u05e7\u05d4",
        "\u05d3\u05e7\u05d4 \u05d5\u05d7\u05e6\u05d9",
        "2 \u05d3\u05e7\u05d5\u05ea",
        "3 \u05d3\u05e7\u05d5\u05ea",
    ]

    for ln in lines:
        if ln.startswith("\U0001f6a8"):
            continue
        if "\u05d9\u05e8\u05d9 \u05e8\u05e7\u05d8\u05d5\u05ea \u05d5\u05d8\u05d9\u05dc\u05d9\u05dd" in ln:
            continue
        if ln.startswith("\u05d0\u05d6\u05d5\u05e8 "):
            continue
        if "\u05d4\u05d9\u05db\u05e0\u05e1\u05d5 \u05dc\u05de\u05e8\u05d7\u05d1 \u05d4\u05de\u05d5\u05d2\u05df" in ln:
            continue

        candidates = re.split(r"\)\s*", ln)
        for c in candidates:
            if "(" not in c:
                continue
            parts = c.rsplit("(", 1)
            if len(parts) != 2:
                continue
            left, right = parts
            right = right.strip()
            if any(tm in right for tm in time_markers):
                for name in left.split(","):
                    n = normalize_text(name)
                    n = re.sub(r"^-+\s*", "", n)
                    n = re.sub(r"\s*-\s*$", "", n)
                    if not n:
                        continue
                    if n.startswith("\u05e2\u05dc \u05ea\u05d5\u05e9\u05d1\u05d9"):
                        continue
                    if n.startswith("\u05d1\u05de\u05e7\u05e8\u05d4 \u05e9\u05dc"):
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

        try:
            dt = to_dt(ds)
        except ValueError:
            continue

        if dt < start_dt or dt > end_dt:
            continue

        text = message_full_text(msg)
        if not text:
            continue
        if not is_rocket_alert(text):
            continue

        raw_text = message_raw_text(msg)
        settlements = extract_settlements(raw_text)
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
        raise ValueError('Target not found: "{}"'.format(target_key))

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
        sett_times = times
        for th in target_times:
            lo = th - timedelta(seconds=MAX_LEAD_SEC)
            hi = th - timedelta(seconds=MIN_LEAD_SEC)
            j = bisect_left(sett_times, lo)
            if j < len(sett_times) and sett_times[j] <= hi:
                hit_target_given_settlement += 1

        p_settlement_given_target = (
            hit_target_given_settlement / target_count if target_count else 0.0
        )
        avg_lead = (
            sum(lead_seconds_list) / len(lead_seconds_list)
            if lead_seconds_list
            else math.nan
        )
        med_lead = median(lead_seconds_list) if lead_seconds_list else math.nan

        results.append(
            {
                "settlement": settlement,
                "total_events": total,
                "success_count": success,
                "precision": precision,
                "avg_lead_sec": avg_lead,
                "med_lead_sec": med_lead,
                "p_settlement_given_target": p_settlement_given_target,
            }
        )

    results.sort(key=lambda x: (x["precision"], x["total_events"]), reverse=True)
    return results, target_count


def format_lead(sec):
    if sec is None or (isinstance(sec, float) and math.isnan(sec)):
        return "-"
    m = int(sec // 60)
    s = int(round(sec % 60))
    return "{}s".format(s) if m == 0 else "{}m {}s".format(m, s)


def pct(x):
    return "{:.1f}%".format(x * 100)


def pick_top_operational(rows, k=3):
    scored = []
    for r in rows:
        if math.isnan(r["avg_lead_sec"]):
            continue
        precision_score = r["precision"]
        # Volume saturates at ~200 events (reference point for max score)
        volume_score = min(1.0, math.log1p(r["total_events"]) / math.log1p(200))
        lead = r["avg_lead_sec"]
        # Gaussian centered at 150s (2.5 min optimal lead), sigma=90s
        lead_score = math.exp(-((lead - 150.0) ** 2) / (2 * (90.0 ** 2)))
        # Weights: precision 55%, lead quality 25%, volume 20%
        score = 0.55 * precision_score + 0.25 * lead_score + 0.20 * volume_score
        rr = dict(r)
        rr["operational_score"] = score
        scored.append(rr)
    scored.sort(key=lambda x: x["operational_score"], reverse=True)
    return scored[:k]


def auto_pick_target(events_by_settlement):
    cands = [
        k
        for k in events_by_settlement.keys()
        if ("\u05d1\u05d9\u05ea" in k and "\u05d7\u05d2" in k)
    ]
    if not cands:
        return None
    cands.sort(key=lambda k: len(events_by_settlement.get(k, [])), reverse=True)
    return cands[0]


def main():
    # Ensure stdout handles UTF-8 on Windows (PowerShell / cmd)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Generate predictor tables from result_filtered.json"
    )
    parser.add_argument("--input", required=True, help="Path to result_filtered.json")
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help="Target settlement name. Use AUTO_BEIT_HAG for auto-detect.",
    )
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=None)
    parser.add_argument(
        "--min-volume",
        type=int,
        default=DEFAULT_MIN_VOLUME,
        help="Minimum number of events for a predictor settlement (default: 20)",
    )
    args = parser.parse_args()

    start_dt = datetime.fromisoformat(args.start_date + "T00:00:00")
    end_dt = (
        datetime.fromisoformat(args.end_date + "T23:59:59")
        if args.end_date
        else datetime.now()
    )

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("ERROR: Input file not found: {}".format(args.input))
        sys.exit(1)
    except json.JSONDecodeError as e:
        print("ERROR: Failed to parse JSON: {}".format(e))
        sys.exit(1)

    # Support both top-level list and {"messages": [...]} dict
    if isinstance(data, list):
        messages = data
    elif isinstance(data, dict):
        messages = data.get("messages", [])
    else:
        print("ERROR: Unexpected JSON root type: {}".format(type(data).__name__))
        sys.exit(1)

    if not messages:
        print("ERROR: No messages found in input file.")
        sys.exit(1)

    events_by_settlement = build_events(messages, start_dt, end_dt)

    if not events_by_settlement:
        print("ERROR: No parsed settlement events found in date range.")
        print("  Date range: {} .. {}".format(start_dt, end_dt))
        print("  Messages checked: {}".format(len(messages)))
        print(
            "  Hint: try adjusting --start-date (default: {})".format(DEFAULT_START_DATE)
        )
        sys.exit(1)

    if args.target == "AUTO_BEIT_HAG":
        target_key = auto_pick_target(events_by_settlement)
        if not target_key:
            print(
                "ERROR: Could not auto-detect target containing "
                "\u05d1\u05d9\u05ea + \u05d7\u05d2."
            )
            sample = sorted(events_by_settlement.keys())[:80]
            print("Sample keys:")
            for k in sample:
                print(" -", k)
            sys.exit(1)
        print("AUTO target selected: {}".format(target_key))
    else:
        target_key = norm_key(args.target)

    if target_key not in events_by_settlement:
        print(
            'ERROR: target not found after normalization: "{}"'.format(target_key)
        )
        print("Candidates containing \u05d1\u05d9\u05ea+\u05d7\u05d2:")
        found = False
        for k in sorted(events_by_settlement.keys()):
            if "\u05d1\u05d9\u05ea" in k and "\u05d7\u05d2" in k:
                found = True
                print(" -", k)
        if not found:
            print(" - none -")
        sys.exit(1)

    rows, target_count = compute_predictor_stats(
        events_by_settlement, target_key, args.min_volume
    )
    top10 = rows[:10]
    recommendations = pick_top_operational(top10, 3)

    print("=== Predictor Analysis ===")
    print("Date range  : {} .. {}".format(start_dt, end_dt))
    print("Target key  : {}".format(target_key))
    print("Target count: {} (deduplicated per minute)".format(target_count))
    print("Min volume  : {}".format(args.min_volume))
    print("Lead window : {}s .. {}s".format(MIN_LEAD_SEC, MAX_LEAD_SEC))

    print("\n--- Top 10 Predictors (by precision) ---")
    header = "{:<40} {:>6} {:>22} {:>9} {:>12} {:>22} {:>14}".format(
        "Settlement",
        "Total",
        "P(target|settlement)",
        "Avg lead",
        "Median lead",
        "P(settlement|target)",
        "Hits/Total",
    )
    print(header)
    print("-" * len(header))
    for r in top10:
        print(
            "{:<40} {:>6} {:>22} {:>9} {:>12} {:>22} {:>14}".format(
                r["settlement"][:40],
                r["total_events"],
                pct(r["precision"]),
                format_lead(r["avg_lead_sec"]),
                format_lead(r["med_lead_sec"]),
                pct(r["p_settlement_given_target"]),
                "{}/{}".format(r["success_count"], r["total_events"]),
            )
        )

    print("\n--- Top 3 Operational Triggers ---")
    if not recommendations:
        print("No recommendations (insufficient lead-time data).")
    else:
        for i, r in enumerate(recommendations, 1):
            print(
                "{}) {} | precision={} | avg_lead={} | total={}".format(
                    i,
                    r["settlement"],
                    pct(r["precision"]),
                    format_lead(r["avg_lead_sec"]),
                    r["total_events"],
                )
            )

    print("\n--- Required-Check Table ---")
    req_header = "{:<5} {:<40} {:<22} {:<12}".format(
        "Rank", "Settlement", "P(target|settlement)", "Avg Lead"
    )
    print(req_header)
    print("-" * len(req_header))
    for i, r in enumerate(top10, 1):
        print(
            "{:<5} {:<40} {:<22} {:<12}".format(
                i,
                r["settlement"][:40],
                pct(r["precision"]),
                format_lead(r["avg_lead_sec"]),
            )
        )


if __name__ == "__main__":
    main()
