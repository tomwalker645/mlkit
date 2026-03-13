#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Predictor Analysis Tool  (v2.3)
================================
Reads a Telegram channel export (result_filtered.json) containing Hebrew
rocket-alert messages, and finds which settlements are the best predictors
(by precision and operational score) for a target settlement.

Usage
-----
    # Basic — write results directly to a UTF-8 file:
    py analyze_predictors_en_safe.py --input result_filtered.json \
        --target AUTO_BEIT_HAG --min-volume 20 --output output.txt

    # List all available target settlements:
    py analyze_predictors_en_safe.py --input result_filtered.json --list-targets

    # Custom table sizes and date window:
    py analyze_predictors_en_safe.py --input result_filtered.json \
        --target AUTO_BEIT_HAG --top-n 15 --top-k 5 \
        --start-date 2026-01-01 --output output.txt

    # Force-check specific settlements even if below min-volume:
    py analyze_predictors_en_safe.py --input result_filtered.json \
        --target AUTO_BEIT_HAG --force-check "להב,להבים,מעון"

    # Analyse only Range-1 settlements (pre-defined close-range group):
    py analyze_predictors_en_safe.py --input result_filtered.json \
        --target AUTO_BEIT_HAG --range 1 --html --output range1.html

    # Analyse only Range-2 settlements (pre-defined mid-range group):
    py analyze_predictors_en_safe.py --input result_filtered.json \
        --target AUTO_BEIT_HAG --range 2 --html --output range2.html

    # Output Hebrew settlement names instead of English:
    py analyze_predictors_en_safe.py --input result_filtered.json \
        --target AUTO_BEIT_HAG --hebrew --output output.txt

    # Styled HTML table output (opens in any browser):
    py analyze_predictors_en_safe.py --input result_filtered.json \
        --target AUTO_BEIT_HAG --html --output top10.html

Output
------
  - Table 1: Top N settlements by precision (P(target|settlement fires first))
  - Table 2: Top K operational triggers (weighted score of precision + lead-time + volume)
  - Table 2+: Additional operational triggers beyond top K
  - HTML mode adds a "Decision sentence" column (e.g. "If alarm at X → ~59% chance at target")

New in v2.3
-----------
  --range N         Pre-defined settlement groups (shorthand for --force-check):
                      1 = close range: להבים, סנסנה, גבעות בר, אתר דודאים, עומר
                      2 = mid range: אשתמוע, כרמל, מעון, שמעה, להב, תנא עומרים
                    Combines with any extra --force-check names.
  HTML decision     The --html output now adds a "Decision sentence" column to Table 1
                    showing plain-language probability for each predictor settlement.

New in v2.2
-----------
  --html            Write a self-contained styled HTML table instead of plain text.
                    Combine with --output FILE.html; defaults to output.html.

New in v2.1
-----------
  --force-check     Comma-separated Hebrew settlement names always included in analysis
                    regardless of --min-volume (useful for geographic priority settlements
                    on the firing axis: להב, להבים, תנא עומרים, מעון, סנסנה, שמעה)
  --hebrew          Display settlement names in Hebrew instead of English
  Default start date fixed to 2026-02-28 (start of current escalation)

New in v2.0
-----------
  --output FILE     Write results directly to a UTF-8 file (no redirect needed)
  --list-targets    List all settlements with enough volume so you can pick --target
  --top-n N         Number of rows in Table 1 (default 10)
  --top-k K         Number of rows in Table 2 (default 3)
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

VERSION = "2.3"

DEFAULT_TARGET = "AUTO_BEIT_HAG"
DEFAULT_MIN_VOLUME = 20
DEFAULT_TOP_N = 10
DEFAULT_TOP_K = 3
MIN_LEAD_SEC = 15
MAX_LEAD_SEC = 600

# Default start date: 28 Feb 2026 (start of current escalation)
DEFAULT_START_DATE = "2026-02-28"

# Geographic priority settlements on the firing axis from south/west towards
# Mt. Hebron — always force-checked when target is Beit Hagai.
GEO_PRIORITY_NAMES = [
    "\u05dc\u05d4\u05d1",           # להב   (Lahav)
    "\u05dc\u05d4\u05d1\u05d9\u05dd",  # להבים (Lehavim)
    "\u05ea\u05e0\u05d0 \u05e2\u05d5\u05de\u05e8\u05d9\u05dd",  # תנא עומרים (Tene Omarim)
    "\u05de\u05e2\u05d5\u05df",      # מעון  (Ma'on)
    "\u05e1\u05e0\u05e1\u05e0\u05d4",  # סנסנה (Sansana)
    "\u05e9\u05de\u05e2\u05d4",      # שמעה  (Shema)
]

# Pre-defined range groups for the --range flag.
# Range 1 — close-range settlements on the direct firing axis (top predictors).
RANGE_1_NAMES = [
    "\u05dc\u05d4\u05d1\u05d9\u05dd",          # להבים  (Lehavim)
    "\u05e1\u05e0\u05e1\u05e0\u05d4",           # סנסנה  (Sansana)
    "\u05d2\u05d1\u05e2\u05d5\u05ea \u05d1\u05e8",  # גבעות בר (Giv'ot Bar)
    "\u05d0\u05ea\u05e8 \u05d3\u05d5\u05d3\u05d0\u05d9\u05dd",  # אתר דודאים (Dorot site)
    "\u05e2\u05d5\u05de\u05e8",                 # עומר   (Omer)
]

# Range 2 — mid-range settlements in the broader Hebron Hills area.
RANGE_2_NAMES = [
    "\u05d0\u05e9\u05ea\u05de\u05d5\u05e2",     # אשתמוע (Eshtemoa)
    "\u05db\u05e8\u05de\u05dc",                 # כרמל   (Carmel)
    "\u05de\u05e2\u05d5\u05df",                 # מעון   (Ma'on)
    "\u05e9\u05de\u05e2\u05d4",                 # שמעה   (Shema)
    "\u05dc\u05d4\u05d1",                       # להב    (Lahav)
    "\u05ea\u05e0\u05d0 \u05e2\u05d5\u05de\u05e8\u05d9\u05dd",  # תנא עומרים (Tene Omarim)
]

NAMED_RANGES = {1: RANGE_1_NAMES, 2: RANGE_2_NAMES}

# Width of the Table 1 header row: must match the format string in main()
TABLE1_WIDTH = 98

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

# ─── Settlement name display: Hebrew → English ────────────────────────────────
# Keys must be in norm_key() form (no geresh/gershayim, single-spaced).
# Covers the settlements most commonly seen in Israeli rocket-alert data.
SETTLEMENT_EN = {
    # Gaza envelope / south
    "\u05d0\u05e9\u05e7\u05dc\u05d5\u05df": "Ashkelon",
    "\u05d0\u05e9\u05d3\u05d5\u05d3": "Ashdod",
    "\u05e9\u05d3\u05e8\u05d5\u05ea": "Sderot",
    "\u05e0\u05ea\u05d9\u05d1\u05d5\u05ea": "Netivot",
    "\u05d0\u05d5\u05e4\u05e7\u05d9\u05dd": "Ofakim",
    "\u05e0\u05d9\u05e8 \u05e2\u05dd": "Nir Am",
    "\u05db\u05e4\u05e8 \u05e2\u05d6\u05d4": "Kfar Aza",
    "\u05e0\u05d7\u05dc \u05e2\u05d5\u05d6": "Nahal Oz",
    "\u05de\u05d2\u05df": "Magen",
    "\u05e0\u05d9\u05e8\u05d9\u05dd": "Nirim",
    "\u05d1\u05d0\u05e8\u05d9": "Be'eri",
    "\u05db\u05d9\u05e1\u05d5\u05e4\u05d9\u05dd": "Kissufim",
    "\u05e6\u05d0\u05dc\u05d9\u05dd": "Tzaelim",
    "\u05e0\u05d9\u05e8 \u05d9\u05e6\u05d7\u05e7": "Nir Yitzhak",
    "\u05d2\u05d1\u05d5\u05dc\u05d5\u05ea": "Gevulot",
    "\u05d0\u05dc\u05d5\u05de\u05d9\u05dd": "Alumim",
    "\u05e8\u05e2\u05d9\u05dd": "Re'im",
    "\u05e2\u05d9\u05df \u05d4\u05d1\u05e9\u05d5\u05e8": "Ein HaBsor",
    "\u05ea\u05e7\u05d5\u05de\u05d4": "Tkuma",
    "\u05e4\u05d8\u05d9\u05e9": "Patish",
    "\u05e0\u05d9\u05e8 \u05e2\u05d5\u05d6": "Nir Oz",
    "\u05d7\u05d5\u05dc\u05d9\u05ea": "Hulit",
    "\u05e1\u05e2\u05d3": "Sa'ad",
    "\u05d9\u05d3 \u05de\u05e8\u05d3\u05db\u05d9": "Yad Mordechai",
    "\u05e0\u05d9\u05e6\u05df": "Nitzan",
    "\u05d6\u05d9\u05e7\u05d9\u05dd": "Zikim",
    "\u05d0\u05e8\u05d6": "Erez",
    "\u05de\u05e4\u05dc\u05e1\u05d9\u05dd": "Mefalsim",
    "\u05db\u05e8\u05dd \u05e9\u05dc\u05d5\u05dd": "Kerem Shalom",
    "\u05e2\u05d9\u05df \u05d4\u05e9\u05dc\u05d5\u05e9\u05d4": "Ein HaShlosha",
    "\u05e9\u05d5\u05e7\u05d3\u05d4": "Shokeda",
    "\u05db\u05e4\u05e8 \u05de\u05d9\u05d9\u05de\u05d5\u05df": "Kfar Maimon",
    "\u05d2\u05d9\u05dc\u05ea": "Gilat",
    "\u05d1\u05e8\u05d5\u05e8 \u05d7\u05d9\u05dc": "Brur Hail",
    "\u05d9\u05e9\u05e2": "Yesha",
    "\u05e9\u05e4\u05d9\u05e8": "Shafir",
    "\u05e9\u05d3\u05d4 \u05d3\u05d5\u05d3": "Sde David",
    # Lachish / Shfela
    "\u05dc\u05db\u05d9\u05e9": "Lachish",
    "\u05d2\u05df \u05d9\u05d1\u05e0\u05d4": "Gan Yavne",
    "\u05d9\u05d1\u05e0\u05d4": "Yavne",
    "\u05d2\u05d3\u05e8\u05d4": "Gedera",
    "\u05de\u05d6\u05db\u05e8\u05ea \u05d1\u05ea\u05d9\u05d4": "Mazkeret Batya",
    "\u05e8\u05d7\u05d5\u05d1\u05d5\u05ea": "Rehovot",
    "\u05e0\u05e1 \u05e6\u05d9\u05d5\u05e0\u05d4": "Nes Ziona",
    "\u05e7\u05e8\u05d9\u05d9\u05ea \u05d2\u05ea": "Kiryat Gat",
    "\u05e7\u05e8\u05d9\u05ea \u05d2\u05ea": "Kiryat Gat",
    "\u05e7\u05e8\u05d9\u05d9\u05ea \u05de\u05dc\u05d0\u05db\u05d9": "Kiryat Malachi",
    "\u05e7\u05e8\u05d9\u05ea \u05de\u05dc\u05d0\u05db\u05d9": "Kiryat Malachi",
    "\u05d2\u05d1\u05e2\u05ea \u05d1\u05e8\u05e0\u05e8": "Givat Brenner",
    # Judea / Hebron Hills
    "\u05d1\u05d9\u05ea \u05d7\u05d2\u05d9": "Beit Hagai",
    "\u05e7\u05e8\u05d9\u05ea \u05d0\u05e8\u05d1\u05e2": "Kiryat Arba",
    "\u05e7\u05e8\u05d9\u05d9\u05ea \u05d0\u05e8\u05d1\u05e2": "Kiryat Arba",
    "\u05d7\u05d1\u05e8\u05d5\u05df": "Hebron",
    "\u05d1\u05d9\u05ea \u05e9\u05de\u05e9": "Beit Shemesh",
    "\u05de\u05e2\u05d5\u05df": "Ma'on",
    "\u05db\u05e8\u05de\u05dc": "Carmel",
    "\u05e9\u05d5\u05db\u05d4": "Shuka",
    "\u05d1\u05d9\u05ea \u05d9\u05ea\u05d9\u05e8": "Beit Yatir",
    "\u05d0\u05d1\u05d9\u05d2\u05d9\u05dc": "Avigail",
    "\u05ea\u05e0\u05d0 \u05e2\u05d5\u05de\u05e8\u05d9\u05dd": "Tene Omarim",
    "\u05e1\u05e0\u05e1\u05e0\u05d4": "Sansana",
    "\u05e9\u05de\u05e2\u05d4": "Shema",
    # Jerusalem area
    "\u05d9\u05e8\u05d5\u05e9\u05dc\u05d9\u05dd": "Jerusalem",
    "\u05de\u05e2\u05dc\u05d4 \u05d0\u05d3\u05d5\u05de\u05d9\u05dd": "Ma'ale Adumim",
    "\u05d2\u05d5\u05e9 \u05e2\u05e6\u05d9\u05d5\u05df": "Gush Etzion",
    "\u05d0\u05e4\u05e8\u05ea": "Efrat",
    "\u05ea\u05e7\u05d5\u05e2": "Tekoa",
    "\u05d1\u05d9\u05ea\u05e8 \u05e2\u05d9\u05dc\u05d9\u05ea": "Beitar Illit",
    "\u05de\u05d5\u05d3\u05d9\u05e2\u05d9\u05df \u05e2\u05d9\u05dc\u05d9\u05ea": "Modi'in Illit",
    # Negev
    "\u05d1\u05d0\u05e8 \u05e9\u05d1\u05e2": "Beer Sheva",
    "\u05d3\u05d9\u05de\u05d5\u05e0\u05d4": "Dimona",
    "\u05e2\u05e8\u05d3": "Arad",
    "\u05d9\u05e8\u05d5\u05d7\u05dd": "Yeruham",
    "\u05de\u05e6\u05e4\u05d4 \u05e8\u05de\u05d5\u05df": "Mitzpe Ramon",
    "\u05d0\u05d9\u05dc\u05ea": "Eilat",
    "\u05dc\u05d4\u05d1\u05d9\u05dd": "Lehavim",
    "\u05de\u05d9\u05ea\u05e8": "Meitar",
    "\u05e2\u05d5\u05de\u05e8": "Omer",
    "\u05e8\u05d4\u05d8": "Rahat",
    "\u05ea\u05dc \u05e9\u05d1\u05e2": "Tel Sheva",
    "\u05dc\u05e7\u05d9\u05d4": "Lakiya",
    "\u05db\u05e1\u05d9\u05d9\u05e4\u05d4": "Kuseifa",
    "\u05e9\u05d2\u05d1 \u05e9\u05dc\u05d5\u05dd": "Segev Shalom",
    "\u05dc\u05d4\u05d1": "Lahav",
    "\u05e9\u05d5\u05d1\u05dc": "Shuval",
    "\u05e8\u05d1\u05d9\u05d1\u05d9\u05dd": "Revivim",
    # Center / Tel Aviv area
    "\u05ea\u05dc \u05d0\u05d1\u05d9\u05d1": "Tel Aviv",
    "\u05e8\u05d0\u05e9\u05d5\u05df \u05dc\u05e6\u05d9\u05d5\u05df": "Rishon LeZion",
    "\u05e4\u05ea\u05d7 \u05ea\u05e7\u05d5\u05d5\u05d4": "Petah Tikva",
    "\u05e8\u05de\u05ea \u05d2\u05df": "Ramat Gan",
    "\u05d2\u05d1\u05e2\u05ea\u05d9\u05d9\u05dd": "Givatayim",
    "\u05d7\u05d5\u05dc\u05d5\u05df": "Holon",
    "\u05d1\u05ea \u05d9\u05dd": "Bat Yam",
    "\u05dc\u05d5\u05d3": "Lod",
    "\u05e8\u05de\u05dc\u05d4": "Ramla",
    "\u05de\u05d5\u05d3\u05d9\u05e2\u05d9\u05df": "Modi'in",
    "\u05e8\u05d0\u05e9 \u05d4\u05e2\u05d9\u05df": "Rosh HaAyin",
    "\u05d0\u05dc\u05e2\u05d3": "Elad",
    "\u05e9\u05d5\u05d4\u05dd": "Shoham",
    # Sharon
    "\u05d4\u05e8\u05e6\u05dc\u05d9\u05d4": "Herzliya",
    "\u05e0\u05ea\u05e0\u05d9\u05d4": "Netanya",
    "\u05d7\u05d3\u05e8\u05d4": "Hadera",
    "\u05db\u05e4\u05e8 \u05e1\u05d1\u05d0": "Kfar Saba",
    "\u05e8\u05e2\u05e0\u05e0\u05d4": "Ra'anana",
    "\u05d4\u05d5\u05d3 \u05d4\u05e9\u05e8\u05d5\u05df": "Hod HaSharon",
    "\u05db\u05e4\u05e8 \u05d9\u05d5\u05e0\u05d4": "Kfar Yona",
    "\u05ea\u05dc \u05de\u05d5\u05e0\u05d3": "Tel Mond",
    "\u05e7\u05d3\u05d9\u05de\u05d4": "Kadima",
    # North / Galilee
    "\u05d7\u05d9\u05e4\u05d4": "Haifa",
    "\u05e2\u05db\u05d5": "Akko",
    "\u05e0\u05d4\u05e8\u05d9\u05d4": "Nahariya",
    "\u05e9\u05dc\u05d5\u05de\u05d9": "Shlomi",
    "\u05e7\u05e8\u05d9\u05d9\u05ea \u05e9\u05de\u05d5\u05e0\u05d4": "Kiryat Shmona",
    "\u05e7\u05e8\u05d9\u05ea \u05e9\u05de\u05d5\u05e0\u05d4": "Kiryat Shmona",
    "\u05de\u05d8\u05d5\u05dc\u05d4": "Metula",
    "\u05e8\u05d0\u05e9 \u05e4\u05d9\u05e0\u05d4": "Rosh Pinna",
    "\u05e6\u05e4\u05ea": "Safed",
    "\u05d8\u05d1\u05e8\u05d9\u05d4": "Tiberias",
    "\u05e0\u05e6\u05e8\u05ea": "Nazareth",
    "\u05e2\u05e4\u05d5\u05dc\u05d4": "Afula",
    "\u05d9\u05d5\u05e7\u05e0\u05e2\u05dd": "Yokneam",
    "\u05e7\u05e8\u05d9\u05d9\u05ea \u05d9\u05dd": "Kiryat Yam",
    "\u05e7\u05e8\u05d9\u05ea \u05d9\u05dd": "Kiryat Yam",
    "\u05e7\u05e8\u05d9\u05d9\u05ea \u05d1\u05d9\u05d0\u05dc\u05d9\u05e7": "Kiryat Bialik",
    "\u05e7\u05e8\u05d9\u05ea \u05d1\u05d9\u05d0\u05dc\u05d9\u05e7": "Kiryat Bialik",
    "\u05e7\u05e8\u05d9\u05d9\u05ea \u05de\u05d5\u05e6\u05e7\u05d9\u05df": "Kiryat Motzkin",
    "\u05e7\u05e8\u05d9\u05ea \u05de\u05d5\u05e6\u05e7\u05d9\u05df": "Kiryat Motzkin",
    "\u05e7\u05e8\u05d9\u05d9\u05ea \u05d0\u05ea\u05d0": "Kiryat Ata",
    "\u05e7\u05e8\u05d9\u05ea \u05d0\u05ea\u05d0": "Kiryat Ata",
    "\u05d8\u05d9\u05e8\u05ea \u05db\u05e8\u05de\u05dc": "Tirat Carmel",
    "\u05d6\u05d9\u05db\u05e8\u05d5\u05df \u05d9\u05e2\u05e7\u05d1": "Zichron Ya'akov",
    "\u05d1\u05e0\u05d9\u05de\u05d9\u05e0\u05d4": "Binyamina",
    "\u05e4\u05e8\u05d3\u05e1 \u05d7\u05e0\u05d4": "Pardes Hanna",
    "\u05de\u05d2\u05d3\u05dc \u05d4\u05e2\u05de\u05e7": "Migdal HaEmek",
    "\u05e0\u05e9\u05e8": "Nesher",
    "\u05db\u05e8\u05de\u05d9\u05d0\u05dc": "Karmiel",
    # Golan Heights
    "\u05e7\u05e6\u05e8\u05d9\u05df": "Katzrin",
    "\u05de\u05d2\u05d3\u05dc \u05e9\u05de\u05e1": "Majdal Shams",
    "\u05de\u05e1\u05e2\u05d3\u05d4": "Mas'ada",
    "\u05d1\u05d5\u05e7\u05e2\u05d0\u05ea\u05d0": "Buq'ata",
    "\u05de\u05e8\u05d5\u05dd \u05d2\u05d5\u05dc\u05df": "Merom Golan",
}

# Fallback: character-level Hebrew → Latin transliteration
_HE_TO_LATIN = {
    "\u05d0": "", "\u05d1": "b", "\u05d2": "g", "\u05d3": "d", "\u05d4": "h",
    "\u05d5": "v", "\u05d6": "z", "\u05d7": "ch", "\u05d8": "t", "\u05d9": "y",
    "\u05db": "k", "\u05da": "kh", "\u05dc": "l", "\u05de": "m", "\u05dd": "m",
    "\u05e0": "n", "\u05df": "n", "\u05e1": "s", "\u05e2": "", "\u05e4": "p",
    "\u05e3": "f", "\u05e6": "tz", "\u05e5": "tz", "\u05e7": "k", "\u05e8": "r",
    "\u05e9": "sh", "\u05ea": "t",
}


def transliterate_he(s: str) -> str:
    """Transliterate Hebrew characters to Latin letters (best-effort fallback)."""
    parts = [_HE_TO_LATIN.get(ch, ch) for ch in s]
    out = re.sub(r"\s+", " ", "".join(parts)).strip()
    return " ".join(w.capitalize() for w in out.split()) if out else s


def settlement_display(key: str) -> str:
    """Return an English-readable display name for a normalized settlement key."""
    en = SETTLEMENT_EN.get(key)
    return en if en else transliterate_he(key)


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


def compute_predictor_stats(events_by_settlement, target_key, min_volume, force_set=None):
    if target_key not in events_by_settlement:
        raise ValueError(f'Target not found: "{target_key}"')

    force_set = force_set or set()
    target_times = sorted(events_by_settlement[target_key])
    target_count = len(target_times)
    results = []

    for settlement, times in events_by_settlement.items():
        if settlement == target_key:
            continue
        total = len(times)
        if total < min_volume and settlement not in force_set:
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
            "force_checked": settlement in force_set,
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


def pick_top_operational(rows):
    """Score and rank all rows by operational usefulness; return all with valid lead time."""
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
    return scored


def auto_pick_target(events_by_settlement):
    beit = "\u05d1\u05d9\u05ea"   # "בית"
    hag = "\u05d7\u05d2"           # "חג"
    cands = [k for k in events_by_settlement.keys() if (beit in k and hag in k)]
    if not cands:
        return None
    cands.sort(key=lambda k: len(events_by_settlement.get(k, [])), reverse=True)
    return cands[0]


def _precision_color(p: float) -> str:
    """Return a CSS background color for a precision fraction (0–1).

    Green (≥70 %), yellow-green (≥50 %), orange (≥30 %), light-red (<30 %).
    """
    if p >= 0.70:
        return "#4caf50"   # green
    if p >= 0.50:
        return "#8bc34a"   # light green
    if p >= 0.30:
        return "#ffc107"   # amber
    return "#ef9a9a"       # soft red


def _lead_bar_width(sec) -> int:
    """Convert average lead time to a progress-bar percentage (0–100).

    Clamps at MAX_LEAD_SEC so 600 s = 100 %.
    """
    if sec is None or (isinstance(sec, float) and math.isnan(sec)):
        return 0
    return min(100, int(sec / MAX_LEAD_SEC * 100))


def render_html(
    top_n_rows,
    all_recs,
    target_key,
    target_count,
    start_dt,
    end_dt,
    args,
    force_set,
    display_name_fn,
):
    """Return a self-contained UTF-8 HTML string for the predictor analysis results."""

    target_display = display_name_fn(target_key)
    top_k = args.top_k
    recs = all_recs[:top_k]
    extra_recs = all_recs[top_k:]
    force_list = ", ".join(sorted(force_set)) if force_set else "—"

    def esc(s):
        """Minimal HTML escaping."""
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # ── meta row helpers ────────────────────────────────────────────────────
    def meta(label, value):
        return (
            f'<tr><td class="meta-label">{esc(label)}</td>'
            f'<td class="meta-value">{esc(str(value))}</td></tr>'
        )

    # ── Decision sentence helper ────────────────────────────────────────────
    def decision_sentence(r, target_display_name):
        """Plain-language probability sentence for HTML Table 1."""
        prec_pct = round(r["precision"] * 100)
        sname = display_name_fn(r["settlement"])
        if args.hebrew:
            return (
                f"אם יש אזעקה ב{esc(sname)}, הסיכוי לאזעקה "
                f"ב{esc(target_display_name)} בתוך 10 דקות הוא בערך {prec_pct}%."
            )
        return (
            f"If alarm at {esc(sname)} → ~{prec_pct}% chance of alarm "
            f"at {esc(target_display_name)} within 10 min."
        )

    # ── Table 1 rows ────────────────────────────────────────────────────────
    t1_rows = []
    for i, r in enumerate(top_n_rows, 1):
        name = display_name_fn(r["settlement"])
        is_force = r.get("force_checked", False)
        name_cell = esc(name)
        if is_force:
            name_cell = (
                f'<span class="force-name">{esc(name)}</span>'
                f'<span class="force-badge" title="Force-checked (low volume)">★</span>'
            )
        color = _precision_color(r["precision"])
        bar_w = _lead_bar_width(r["avg_lead_sec"])
        avg_lead_str = esc(format_lead(r["avg_lead_sec"]))
        med_lead_str = esc(format_lead(r["med_lead_sec"]))

        t1_rows.append(
            f"""
        <tr class="{'force-row' if is_force else ''}">
          <td class="rank">{i}</td>
          <td class="sname">{name_cell}</td>
          <td class="num">{r['total_events']}</td>
          <td class="prec" style="background:{color};color:#fff;font-weight:700">
            {pct(r['precision'])}
          </td>
          <td class="lead">
            <div class="lead-wrap">
              <div class="lead-bar" style="width:{bar_w}%"></div>
              <span class="lead-text">{avg_lead_str}</span>
            </div>
          </td>
          <td class="lead-med">{med_lead_str}</td>
          <td class="num">{pct(r['p_settlement_given_target'])}</td>
          <td class="hits">{r['success_count']}/{r['total_events']}</td>
          <td class="decision">{decision_sentence(r, target_display)}</td>
        </tr>"""
        )

    # ── Table 2 rows ────────────────────────────────────────────────────────
    def t2_row(rank, r):
        name = display_name_fn(r["settlement"])
        is_force = r.get("force_checked", False)
        name_cell = esc(name)
        if is_force:
            name_cell = (
                f'<span class="force-name">{esc(name)}</span>'
                f'<span class="force-badge" title="Force-checked (low volume)">★</span>'
            )
        color = _precision_color(r["precision"])
        return (
            f'<tr class="{"force-row" if is_force else ""}">'
            f'<td class="rank">{rank}</td>'
            f'<td class="sname">{name_cell}</td>'
            f'<td class="num">{r["total_events"]}</td>'
            f'<td class="prec" style="background:{color};color:#fff;font-weight:700">'
            f'{pct(r["precision"])}</td>'
            f'<td class="lead"><div class="lead-wrap">'
            f'<div class="lead-bar" style="width:{_lead_bar_width(r["avg_lead_sec"])}%"></div>'
            f'<span class="lead-text">{esc(format_lead(r["avg_lead_sec"]))}</span>'
            f"</div></td>"
            f'<td class="score">{r["operational_score"]:.3f}</td>'
            f"</tr>"
        )

    t2_rows_html = ""
    if recs:
        for i, r in enumerate(recs, 1):
            t2_rows_html += t2_row(i, r)
    else:
        t2_rows_html = (
            '<tr><td colspan="6" class="no-data">'
            "No recommendations (insufficient lead-time data).</td></tr>"
        )

    t2plus_html = ""
    if extra_recs:
        for i, r in enumerate(extra_recs, top_k + 1):
            t2plus_html += t2_row(i, r)
    else:
        t2plus_html = (
            '<tr><td colspan="6" class="no-data">No additional triggers.</td></tr>'
        )

    # Use RTL + Hebrew when --hebrew is set, otherwise standard LTR English
    html_lang = "he" if args.hebrew else "en"
    html_dir = "rtl" if args.hebrew else "ltr"

    # Build a readable target display for the meta card
    if target_display != target_key:
        target_meta_value = f"{target_key} ({target_display})"
    else:
        target_meta_value = target_key

    html = f"""<!DOCTYPE html>
<html lang="{html_lang}" dir="{html_dir}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Predictor Analysis — {esc(target_display)}</title>
<style>
  /* ── reset & base ── */
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Segoe UI', Arial, sans-serif;
    background: #f0f2f5;
    color: #222;
    padding: 24px 16px;
  }}

  /* ── page wrapper ── */
  .page {{ max-width: 1100px; margin: 0 auto; }}

  /* ── header ── */
  .page-header {{
    background: linear-gradient(135deg, #1a237e 0%, #283593 100%);
    color: #fff;
    border-radius: 10px 10px 0 0;
    padding: 20px 28px 16px;
  }}
  .page-header h1 {{ font-size: 1.5rem; font-weight: 700; letter-spacing: .5px; }}
  .page-header .subtitle {{ font-size: .85rem; opacity: .8; margin-top: 4px; }}

  /* ── meta card ── */
  .meta-card {{
    background: #fff;
    padding: 14px 28px;
    border-left: 4px solid #1a237e;
    margin-bottom: 20px;
  }}
  table.meta {{ border-collapse: collapse; font-size: .85rem; }}
  .meta-label {{ color: #555; padding: 2px 28px 2px 0; white-space: nowrap; }}
  .meta-value {{ color: #111; font-weight: 600; }}

  /* ── section cards ── */
  .card {{
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,.08);
    margin-bottom: 24px;
    overflow: hidden;
  }}
  .card-header {{
    background: #1a237e;
    color: #fff;
    padding: 10px 20px;
    font-size: .95rem;
    font-weight: 700;
    letter-spacing: .3px;
  }}
  .card-header.sec {{ background: #37474f; }}

  /* ── data tables ── */
  table.data {{
    width: 100%;
    border-collapse: collapse;
    font-size: .88rem;
  }}
  table.data thead th {{
    background: #e8eaf6;
    color: #1a237e;
    padding: 9px 12px;
    text-align: center;
    font-weight: 700;
    border-bottom: 2px solid #9fa8da;
    white-space: nowrap;
  }}
  table.data thead th.left {{ text-align: left; }}
  table.data tbody tr:nth-child(even) {{ background: #fafafa; }}
  table.data tbody tr:hover {{ background: #e8eaf6; }}
  table.data tbody tr.force-row {{ background: #fff8e1; }}
  table.data tbody tr.force-row:hover {{ background: #fff3cd; }}
  table.data td {{
    padding: 8px 12px;
    border-bottom: 1px solid #eeeeee;
    vertical-align: middle;
  }}
  td.rank {{ text-align: center; color: #777; font-weight: 700; width: 36px; }}
  td.sname {{ text-align: left; min-width: 160px; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; width: 70px; }}
  td.prec {{
    text-align: center;
    border-radius: 4px;
    width: 90px;
    white-space: nowrap;
  }}
  td.score {{ text-align: right; font-variant-numeric: tabular-nums; width: 70px; color: #37474f; }}
  td.hits {{ text-align: right; color: #555; white-space: nowrap; }}
  td.lead, td.lead-med {{ text-align: center; width: 110px; }}
  td.no-data {{ text-align: center; padding: 14px; color: #888; font-style: italic; }}
  td.decision {{ font-size: .82rem; color: #37474f; max-width: 340px; }}

  /* ── force badge ── */
  .force-badge {{
    display: inline-block;
    margin-left: 5px;
    color: #f57f17;
    font-size: .75rem;
    vertical-align: super;
    cursor: help;
  }}
  .force-name {{ font-weight: 600; }}

  /* ── lead-time mini bar ── */
  .lead-wrap {{
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .lead-bar {{
    height: 8px;
    background: #7986cb;
    border-radius: 4px;
    flex-shrink: 0;
    min-width: 2px;
    max-width: 80px;
  }}
  .lead-text {{ white-space: nowrap; font-size: .82rem; color: #333; }}

  /* ── footer ── */
  .footer {{
    text-align: center;
    font-size: .75rem;
    color: #999;
    margin-top: 8px;
  }}
</style>
</head>
<body>
<div class="page">

  <!-- ── Header ── -->
  <div class="page-header">
    <h1>🎯 Predictor Analysis — {esc(target_display)}</h1>
    <div class="subtitle">v{VERSION} &nbsp;·&nbsp; Which settlements predict an alert in {esc(target_display)}?</div>
  </div>

  <!-- ── Meta ── -->
  <div class="meta-card">
    <table class="meta">
      {meta("Target", target_meta_value)}
      {meta("Target events", target_count)}
      {meta("Date range", str(start_dt)[:10] + "  →  " + str(end_dt)[:10])}
      {meta("Min volume", args.min_volume)}
      {meta("Prediction window", f"{MIN_LEAD_SEC}s – {MAX_LEAD_SEC}s")}
      {(meta("Range preset", args.range_preset) if args.range_preset is not None else "")}
      {meta("Force-checked settlements", force_list)}
    </table>
    <p style="font-size:.78rem;color:#888;margin-top:6px">
      ★ = force-checked (included regardless of min-volume threshold)
    </p>
  </div>

  <!-- ── Table 1 ── -->
  <div class="card">
    <div class="card-header">📊 Table 1 — Top {args.top_n} Predictors by Precision</div>
    <table class="data">
      <thead>
        <tr>
          <th>#</th>
          <th class="left">Settlement</th>
          <th>Total</th>
          <th>Precision</th>
          <th>Avg Lead</th>
          <th>Med Lead</th>
          <th>P(sett|tgt)</th>
          <th>Hits/Total</th>
          <th class="left">Decision</th>
        </tr>
      </thead>
      <tbody>
        {''.join(t1_rows)}
      </tbody>
    </table>
  </div>

  <!-- ── Table 2 ── -->
  <div class="card">
    <div class="card-header">⚡ Table 2 — Top {top_k} Operational Triggers</div>
    <table class="data">
      <thead>
        <tr>
          <th>#</th>
          <th class="left">Settlement</th>
          <th>Total</th>
          <th>Precision</th>
          <th>Avg Lead</th>
          <th>Score</th>
        </tr>
      </thead>
      <tbody>{t2_rows_html}</tbody>
    </table>
  </div>

  <!-- ── Table 2+ ── -->
  <div class="card">
    <div class="card-header sec">📋 Table 2+ — Additional Operational Triggers</div>
    <table class="data">
      <thead>
        <tr>
          <th>#</th>
          <th class="left">Settlement</th>
          <th>Total</th>
          <th>Precision</th>
          <th>Avg Lead</th>
          <th>Score</th>
        </tr>
      </thead>
      <tbody>{t2plus_html}</tbody>
    </table>
  </div>

  <div class="footer">Generated by Predictor Analysis Tool v{VERSION}</div>
</div>
</body>
</html>
"""
    return html


def print_safe(text):
    """Print text, falling back to ASCII-safe output on narrow Windows consoles."""
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))


def main():
    # Force UTF-8 output so Hebrew characters are preserved correctly when
    # output is redirected to a file on Windows (where the default is CP1252).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description=f"Predictor Analysis Tool v{VERSION} — Find settlement predictors in rocket-alert data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Write results to a UTF-8 file (recommended on Windows):\n"
            "  py analyze_predictors_en_safe.py --input result_filtered.json "
            "--target AUTO_BEIT_HAG --min-volume 20 --output output.txt\n\n"
            "  # List all available settlements (to pick a --target):\n"
            "  py analyze_predictors_en_safe.py --input result_filtered.json --list-targets\n\n"
            "  # Range-1 settlements as styled HTML (close-range group):\n"
            "  py analyze_predictors_en_safe.py --input result_filtered.json "
            "--target AUTO_BEIT_HAG --range 1 --html --output range1.html\n\n"
            "  # Range-2 settlements as styled HTML (mid-range group):\n"
            "  py analyze_predictors_en_safe.py --input result_filtered.json "
            "--target AUTO_BEIT_HAG --range 2 --html --output range2.html\n\n"
            "  # Force-check geographic priority settlements:\n"
            "  py analyze_predictors_en_safe.py --input result_filtered.json "
            "--target AUTO_BEIT_HAG --force-check \"להב,להבים,מעון\"\n\n"
            "  # Hebrew output:\n"
            "  py analyze_predictors_en_safe.py --input result_filtered.json "
            "--target AUTO_BEIT_HAG --hebrew --output output.txt\n\n"
            "  # Styled HTML table (open in browser):\n"
            "  py analyze_predictors_en_safe.py --input result_filtered.json "
            "--target AUTO_BEIT_HAG --html --output top10.html\n"
        ),
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
    parser.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_TOP_N,
        help=f"Number of rows to show in Table 1 (precision table, default: {DEFAULT_TOP_N})",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"Number of operational triggers to show in Table 2 (default: {DEFAULT_TOP_K})",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="FILE",
        help=(
            "Write results to FILE in UTF-8 encoding (recommended on Windows). "
            "If omitted, output is printed to the console (or output.html when --html is set)."
        ),
    )
    parser.add_argument(
        "--list-targets",
        action="store_true",
        help=(
            "List all settlements that meet --min-volume and exit. "
            "Use this to find a valid value for --target."
        ),
    )
    parser.add_argument(
        "--force-check",
        default=None,
        metavar="NAMES",
        help=(
            "Comma-separated Hebrew settlement names to always include in analysis "
            "regardless of --min-volume (e.g. \"להב,להבים,מעון,סנסנה,שמעה\"). "
            "When target is AUTO_BEIT_HAG the geographic priority settlements "
            "(להב, להבים, תנא עומרים, מעון, סנסנה, שמעה) are added automatically."
        ),
    )
    parser.add_argument(
        "--range",
        type=int,
        default=None,
        choices=[1, 2],
        metavar="N",
        dest="range_preset",
        help=(
            "Pre-defined settlement group to force-check (1 or 2). "
            "Range 1 (close): להבים, סנסנה, גבעות בר, אתר דודאים, עומר. "
            "Range 2 (mid): אשתמוע, כרמל, מעון, שמעה, להב, תנא עומרים. "
            "Combines with any extra --force-check names."
        ),
    )
    parser.add_argument(
        "--hebrew",
        action="store_true",
        help="Display settlement names in Hebrew instead of English.",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help=(
            "Generate a styled self-contained HTML table instead of plain text. "
            "Use --output FILE.html to specify the output path (default: output.html)."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s v{VERSION}",
        help="Show the script version and exit.",
    )
    args = parser.parse_args()

    # Robust missing-file handling
    if not os.path.isfile(args.input):
        print(f"ERROR: Input file not found: {args.input}")
        print()
        print("Make sure your Telegram export file is in the current directory, then run:")
        print(
            f"  py analyze_predictors_en_safe.py --input result_filtered.json"
            f" --min-volume {args.min_volume}"
        )
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

    # --list-targets mode: print all settlements with enough volume and exit
    if args.list_targets:
        qualifying = sorted(
            [(k, len(v)) for k, v in events_by_settlement.items() if len(v) >= args.min_volume],
            key=lambda x: x[1],
            reverse=True,
        )
        print(f"\nSettlements with >= {args.min_volume} alerts (use one as --target):")
        print(f"  {'#':<4}  {'Count':>5}  Settlement")
        print("  " + "-" * 50)
        for idx, (name, count) in enumerate(qualifying, 1):
            try:
                print(f"  {idx:<4}  {count:>5}  {name}")
            except UnicodeEncodeError:
                sys.stdout.buffer.write(
                    f"  {idx:<4}  {count:>5}  {name}\n".encode("utf-8", errors="replace")
                )
        print(f"\nTotal: {len(qualifying)} settlements")
        sys.exit(0)

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

    # Build force_set: start with geographic priority when target is Beit Hagai
    force_set = set()
    if args.target == "AUTO_BEIT_HAG":
        force_set = {norm_key(n) for n in GEO_PRIORITY_NAMES}
    # Add settlements from --range preset (if given)
    if args.range_preset is not None:
        range_names = NAMED_RANGES[args.range_preset]
        for name in range_names:
            force_set.add(norm_key(name))
    # Add any extra names from --force-check
    if args.force_check:
        for name in args.force_check.split(","):
            name = name.strip()
            if name:
                force_set.add(norm_key(name))

    # Report which force-check settlements are not yet in the data at all
    missing_force = sorted(force_set - set(events_by_settlement.keys()))
    if missing_force:
        missing_display = ", ".join(missing_force)
        print_safe(
            f"Note: {len(missing_force)} force-check settlement(s) have no events in "
            f"this date range and will be omitted: {missing_display}"
        )

    rows, target_count = compute_predictor_stats(
        events_by_settlement, target_key, args.min_volume, force_set=force_set
    )
    top_n_rows = rows[: args.top_n]
    all_recs = pick_top_operational(top_n_rows)
    recs = all_recs[: args.top_k]       # Table 2 — primary recommendations
    extra_recs = all_recs[args.top_k:]  # Table 2+ — additional triggers

    # Build the full output as a list of lines so we can write to file or console
    lines = []
    lines.append("")
    lines.append(f"=== Predictor Analysis (v{VERSION}) ===")
    target_en = settlement_display(target_key)
    if args.hebrew:
        lines.append(f"Target         : {target_key}")
    else:
        lines.append(f"Target         : {target_key} ({target_en})")
    lines.append(f"Target events  : {target_count}")
    lines.append(f"Date range     : {start_dt} .. {end_dt}")
    lines.append(f"Min volume     : {args.min_volume}")
    lines.append(f"Window         : {MIN_LEAD_SEC}s .. {MAX_LEAD_SEC}s")
    if args.range_preset is not None:
        lines.append(f"Range preset   : {args.range_preset}")
    if force_set:
        lines.append(f"Force-check    : {', '.join(sorted(force_set))}  (* = low-volume)")
    lines.append("")

    def display_name(key):
        """Return settlement display name according to --hebrew flag."""
        return key if args.hebrew else settlement_display(key)

    # Table 1 — Top N by precision
    lines.append(f"--- Table 1: Top {args.top_n} Predictors by Precision ---")
    lines.append(
        f"{'#':<3}  {'Settlement':<30}  {'Total':>5}  "
        f"{'Precision':>9}  {'Avg Lead':>8}  {'Med Lead':>8}  "
        f"{'P(sett|tgt)':>11}  {'Hits/Total':>10}"
    )
    lines.append("-" * TABLE1_WIDTH)
    for i, r in enumerate(top_n_rows, 1):
        name = display_name(r["settlement"])
        marker = "*" if r.get("force_checked") else " "
        lines.append(
            f"{i:<3}  {name + marker:<30}  {r['total_events']:>5}  "
            f"{pct(r['precision']):>9}  {format_lead(r['avg_lead_sec']):>8}  "
            f"{format_lead(r['med_lead_sec']):>8}  {pct(r['p_settlement_given_target']):>11}  "
            f"{r['success_count']}/{r['total_events']}"
        )

    lines.append("")
    # Table 2 — Top K operational triggers
    lines.append(f"--- Table 2: Top {args.top_k} Operational Triggers ---")
    if not recs:
        lines.append("No recommendations (insufficient lead-time data).")
    else:
        for i, r in enumerate(recs, 1):
            name = display_name(r["settlement"])
            marker = "*" if r.get("force_checked") else ""
            lines.append(
                f"{i}) {name}{marker}  |  "
                f"precision={pct(r['precision'])}  |  "
                f"avg_lead={format_lead(r['avg_lead_sec'])}  |  "
                f"total={r['total_events']}  |  "
                f"score={r['operational_score']:.3f}"
            )

    lines.append("")
    # Table 2+ — Additional operational triggers beyond top K
    if extra_recs:
        lines.append(
            f"--- Table 2+: Additional Triggers (ranks {args.top_k + 1}–{len(all_recs)}) ---"
        )
        for i, r in enumerate(extra_recs, args.top_k + 1):
            name = display_name(r["settlement"])
            marker = "*" if r.get("force_checked") else ""
            lines.append(
                f"{i}) {name}{marker}  |  "
                f"precision={pct(r['precision'])}  |  "
                f"avg_lead={format_lead(r['avg_lead_sec'])}  |  "
                f"total={r['total_events']}  |  "
                f"score={r['operational_score']:.3f}"
            )
    else:
        lines.append("--- Table 2+: No additional triggers beyond Table 2 ---")

    output_text = "\n".join(lines) + "\n"

    # ── HTML output path ──────────────────────────────────────────────────────
    if args.html:
        html_path = args.output if args.output else "output.html"
        html_content = render_html(
            top_n_rows=top_n_rows,
            all_recs=all_recs,
            target_key=target_key,
            target_count=target_count,
            start_dt=start_dt,
            end_dt=end_dt,
            args=args,
            force_set=force_set,
            display_name_fn=display_name,
        )
        with open(html_path, "w", encoding="utf-8") as fout:
            fout.write(html_content)
        print(f"HTML results written to: {html_path}")
        return

    # ── Plain text output path ────────────────────────────────────────────────
    if args.output:
        # Write directly to a UTF-8 file — no encoding issues on Windows
        with open(args.output, "w", encoding="utf-8") as fout:
            fout.write(output_text)
        print(f"Results written to: {args.output}")
    else:
        # Print to console (stdout already reconfigured to UTF-8 at top of main)
        try:
            print(output_text, end="")
        except UnicodeEncodeError:
            sys.stdout.buffer.write(output_text.encode("utf-8", errors="replace"))


if __name__ == "__main__":
    main()
