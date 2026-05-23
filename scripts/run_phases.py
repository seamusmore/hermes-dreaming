#!/usr/bin/env python3
"""
Light/REM/Deep sleep phases runner.
Called by the dreaming_run_phases tool (cron agent).

Usage (via tool):
    dreaming_run_phases(corpus_path="/path/to/corpus/YYYY-MM-DD.txt")

Output: returns JSON dict with phase results.
"""

import json
from datetime import datetime
from pathlib import Path

from .utils import tz_sh, today_iso
from .light_phase import run_light_phase
from .rem_phase import run_rem_phase
from .deep_phase import run_deep_phase


def run_phases(corpus_path: str) -> dict:
    """
    Run Light → REM → Deep phase on an already-extracted corpus file.

    Args:
        corpus_path: Absolute path to the corpus file (YYYY-MM-DD.txt)

    Returns:
        dict with phase results (light, rem, deep, errors).
    """
    report = {
        "date": today_iso(),
        "corpus": corpus_path,
        "phases": {},
        "errors": [],
    }

    corpus_path_obj = Path(corpus_path)
    if not corpus_path_obj.exists():
        report["errors"].append(f"corpus file not found: {corpus_path}")
        return report

    # ------------------------------------------------------------------
    # Light Sleep
    # ------------------------------------------------------------------
    try:
        light_result = run_light_phase(corpus_path_obj)
        report["phases"]["light"] = light_result
    except Exception as e:
        report["errors"].append(f"light phase failed: {e}")

    # ------------------------------------------------------------------
    # REM Sleep
    # ------------------------------------------------------------------
    try:
        rem_result = run_rem_phase()
        report["phases"]["rem"] = {
            "candidates_count": len(rem_result["candidates"]),
            "themes_count": len(rem_result["themes"]),
            "total_entries": rem_result["total_entries"],
            "top_candidates": [
                {
                    "key": c.get("key", "")[:40],
                    "confidence": round(c.get("confidence", 0), 2),
                    "recallDays": len(c.get("recallDays", [])),
                }
                for c in rem_result["candidates"][:5]
            ],
            "themes": [t["tag"] for t in rem_result["themes"][:5]],
        }
        # Keep full data for agent AI generation
        report["_rem_full"] = {
            "candidates": [
                {"snippet": c.get("snippet", ""), "confidence": c.get("confidence", 0)}
                for c in rem_result["candidates"]
            ],
            "themes": rem_result["themes"],
        }
    except Exception as e:
        report["errors"].append(f"rem phase failed: {e}")
        report["_rem_full"] = {"candidates": [], "themes": []}

    # ------------------------------------------------------------------
    # Deep Sleep (algorithmic scoring only)
    # ------------------------------------------------------------------
    try:
        deep_result = run_deep_phase(dry_run=True)
        report["phases"]["deep"] = {
            "promoted_count": len(deep_result["promoted"]),
            "promoted": deep_result["promoted"],
            "total_candidates": deep_result["total_candidates"],
        }
    except Exception as e:
        report["errors"].append(f"deep phase failed: {e}")

    return report
