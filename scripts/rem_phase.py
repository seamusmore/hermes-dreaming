"""REM Sleep phase: pattern recognition and candidate-truth generation."""

import math
from datetime import datetime
from typing import List, Tuple

from .utils import (
    today_iso,
    tz_sh,
    jaccard_similarity,
    entry_average_score,
    calculate_consolidation_component,
    calculate_conceptual_component,
    clamp_score,
    derive_concept_tags,
)
from .short_term_store import get_store, get_phase_signals, save_phase_signals


def _dedupe_entries(entries: List[dict], threshold: float = 0.88) -> List[dict]:
    """Deduplicate entries by Jaccard similarity of their snippets."""
    result = []
    for entry in entries:
        dup = False
        for kept in result:
            if jaccard_similarity(entry.get("snippet", ""), kept.get("snippet", "")) >= threshold:
                dup = True
                break
        if not dup:
            result.append(entry)
    return result


def _calculate_candidate_confidence(entry: dict) -> float:
    """Confidence = openclaw's lightweight REM formula."""
    recall_count = max(0, math.floor(entry.get("recallCount", 0) or 0))
    recall_strength = clamp_score(math.log1p(recall_count) / math.log1p(6))
    avg_score = entry_average_score(entry)
    consolidation = min(1.0, len(entry.get("recallDays", [])) / 3)
    conceptual = min(1.0, len(entry.get("conceptTags", [])) / 6)

    return avg_score * 0.45 + recall_strength * 0.25 + consolidation * 0.20 + conceptual * 0.10


def run_rem_phase(min_confidence: float = 0.45, limit: int = 20) -> dict:
    """
    Scan short-term store for candidate truths and recurring themes.
    Returns:
        {
            "candidates": [...],
            "themes": [...],
            "total_entries": int,
        }
    """
    store = get_store()
    entries_map = store.get("entries", {})
    entries = list(entries_map.values())

    # Filter out already promoted
    candidates = [e for e in entries if not e.get("promotedAt")]

    # Deduplicate
    candidates = _dedupe_entries(candidates)

    # Calculate confidence
    for entry in candidates:
        entry["confidence"] = _calculate_candidate_confidence(entry)

    # Filter by min confidence
    candidates = [e for e in candidates if e.get("confidence", 0) >= min_confidence]

    # Sort by confidence desc
    candidates.sort(key=lambda e: e.get("confidence", 0), reverse=True)
    candidates = candidates[:limit]

    # ---- Theme detection (concept tag frequency) ----
    tag_counts = {}
    for entry in entries:
        for tag in entry.get("conceptTags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    total_entries = len(entries)
    themes = []
    for tag, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True):
        if total_entries > 0:
            strength = min(1.0, count / max(1, total_entries) * 2)
        else:
            strength = 0.0
        if strength >= 0.15:  # minPatternStrength
            themes.append({"tag": tag, "count": count, "strength": strength})
        if len(themes) >= 10:
            break

    # Record REM phase signals
    phase_signals = get_phase_signals()
    phase_entries = phase_signals.setdefault("entries", {})
    now_iso = datetime.now(tz_sh()).isoformat()
    for entry in candidates:
        key = entry["key"]
        if key not in phase_entries:
            phase_entries[key] = {"key": key, "lightHits": 0, "remHits": 0, "lastLightAt": None, "lastRemAt": None}
        phase_entries[key]["remHits"] = phase_entries[key].get("remHits", 0) + 1
        phase_entries[key]["lastRemAt"] = now_iso
    save_phase_signals(phase_signals)

    return {
        "candidates": candidates,
        "themes": themes,
        "total_entries": total_entries,
    }
