"""Deep Sleep phase: weighted scoring + promotion to MEMORY.md."""

import math
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from scripts.utils import (
    today_iso,
    tz_sh,
    memories_dir,
    backup_dir,
    clamp_score,
    entry_average_score,
    total_signal_count,
    calculate_consolidation_component,
    calculate_conceptual_component,
    calculate_recency_component,
    calculate_phase_signal_boost,
    DEFAULT_PROMOTION_MIN_SCORE,
    DEFAULT_PROMOTION_WEIGHTS,
)
from scripts.short_term_store import get_store, get_phase_signals, save_store


def _backup_memory_md() -> Optional[Path]:
    """Backup MEMORY.md before any modification."""
    memory_path = memories_dir() / "MEMORY.md"
    if not memory_path.exists():
        return None
    backup_dir().mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz_sh()).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir() / f"MEMORY.md.{ts}.bak"
    shutil.copy2(str(memory_path), str(backup_path))
    return backup_path


def _calculate_deep_score(entry: dict, phase_signals_map: dict, now_ms: int) -> float:
    """Six-signal weighted score mirroring openclaw's deep phase."""
    signal_count = total_signal_count(entry)
    total_score = entry.get("totalScore", 0.0)

    # 1. Frequency
    freq = clamp_score(math.log1p(signal_count) / math.log1p(10))

    # 2. Relevance
    avg_score = clamp_score(total_score / max(1, signal_count))

    # 3. Query Diversity
    unique_queries = len(entry.get("queryHashes", []))
    recall_days = len(entry.get("recallDays", []))
    context_diversity = max(unique_queries, recall_days)
    diversity = clamp_score(context_diversity / 5)

    # 4. Recency
    last_recalled = entry.get("lastRecalledAt")
    age_days = 999
    if last_recalled:
        try:
            parsed = datetime.fromisoformat(last_recalled.replace("Z", "+00:00")).timestamp() * 1000
            age_days = max(0, (now_ms - parsed) / (1440 * 60 * 1000))
        except Exception:
            pass
    recency = calculate_recency_component(age_days)

    # 5. Consolidation
    raw_consolidation = calculate_consolidation_component(entry.get("recallDays", []))
    grounded = entry.get("groundedCount", 0) or 0
    consolidation = max(raw_consolidation, grounded / 3)

    # 6. Conceptual
    conceptual = calculate_conceptual_component(entry.get("conceptTags", []))

    # 7. Phase boost
    phase_entry = phase_signals_map.get(entry.get("key"))
    phase_boost = calculate_phase_signal_boost(phase_entry, now_ms)

    w = DEFAULT_PROMOTION_WEIGHTS
    score = (
        w["frequency"] * freq +
        w["relevance"] * avg_score +
        w["diversity"] * diversity +
        w["recency"] * recency +
        w["consolidation"] * consolidation +
        w["conceptual"] * conceptual +
        phase_boost
    )
    return clamp_score(score)


def _parse_memory_md(path: Path) -> Tuple[str, List[dict]]:
    """Parse MEMORY.md into header + entries."""
    if not path.exists():
        return "", []
    text = path.read_text(encoding="utf-8", errors="replace")

    # Split by section markers (§)
    parts = text.split("\n\xA7\n")
    header = parts[0].strip() if parts else ""
    entries = []
    for i, part in enumerate(parts[1:], start=1):
        part = part.strip()
        if not part:
            continue
        # Try to extract a title from first line
        lines = part.splitlines()
        title = lines[0].strip() if lines else f"entry_{i}"
        entries.append({"title": title, "content": part, "index": i})
    return header, entries


def _write_memory_md(path: Path, header: str, entries: List[dict]) -> None:
    """Write MEMORY.md from header + entries."""
    lines = []
    if header:
        lines.append(header)
    for entry in entries:
        lines.append("\n\xA7\n")
        lines.append(entry["content"])
    path.write_text("".join(lines).strip() + "\n", encoding="utf-8")


def _cleanup_outdated(entries: List[dict], new_titles: set) -> Tuple[List[dict], List[str]]:
    """Remove outdated entries whose titles are superseded by new ones."""
    cleaned = []
    removed = []
    for entry in entries:
        title = entry["title"].lower().strip()
        # Heuristic: if title is very similar to a new one, it's outdated
        outdated = False
        for new_title in new_titles:
            if title == new_title.lower().strip():
                outdated = True
                break
            # If title contains old preference indicators while new one updates it
            if any(marker in title for marker in ["旧", "old", "previous", "deprecated", "已废弃"]):
                if len(title) > len(new_title) * 0.6:
                    outdated = True
                    break
        if outdated:
            removed.append(entry["title"])
        else:
            cleaned.append(entry)
    return cleaned, removed


def run_deep_phase(min_score: float = DEFAULT_PROMOTION_MIN_SCORE,
                   min_recall_count: int = 3,
                   min_unique_queries: int = 2,
                   max_age_days: int = -1,
                   max_age_for_single_recall: int = 5,
                   limit: int = 5,
                   dry_run: bool = False) -> dict:
    """
    Evaluate candidates and promote worthy ones to MEMORY.md.
    Returns:
        {
            "promoted": [{"title": str, "score": float}],
            "removed": [str],
            "backup": str,
            "total_candidates": int,
        }
    """
    store = get_store()
    phase_signals = get_phase_signals()
    phase_map = phase_signals.get("entries", {})

    entries_map = store.get("entries", {})
    candidates = [e for e in entries_map.values() if not e.get("promotedAt")]

    now_ms = datetime.now(tz_sh()).timestamp() * 1000

    # Score each candidate
    scored = []
    for entry in candidates:
        score = _calculate_deep_score(entry, phase_map, now_ms)
        entry["deepScore"] = score
        scored.append(entry)

    # Hard thresholds
    filtered = []
    for entry in scored:
        signal_count = total_signal_count(entry)
        if signal_count < min_recall_count:
            continue
        unique_queries = len(entry.get("queryHashes", []))
        recall_days = len(entry.get("recallDays", []))
        if max(unique_queries, recall_days) < min_unique_queries:
            continue
        if max_age_days > 0:
            last_recalled = entry.get("lastRecalledAt")
            if last_recalled:
                try:
                    parsed = datetime.fromisoformat(last_recalled.replace("Z", "+00:00")).timestamp() * 1000
                    age = (now_ms - parsed) / (1440 * 60 * 1000)
                    if age > max_age_days:
                        continue
                except Exception:
                    pass
            else:
                continue
        if score < min_score:
            continue
        filtered.append(entry)

    # Sort by deepScore desc
    filtered.sort(key=lambda e: e.get("deepScore", 0), reverse=True)
    filtered = filtered[:limit]

    promoted = []
    for entry in filtered:
        promoted.append({
            "title": entry.get("snippet", "")[:60].strip(),
            "score": entry.get("deepScore", 0),
            "snippet": entry.get("snippet", ""),
            "key": entry.get("key", ""),
        })
        entry["promotedAt"] = datetime.now(tz_sh()).isoformat()

    save_store(store)

    return {
        "promoted": promoted,
        "removed": [],
        "backup": None,
        "total_candidates": len(scored),
    }
