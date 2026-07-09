"""Short-term recall store — in-memory JSON mirroring openclaw's structure."""

import math
from datetime import datetime
from pathlib import Path
from typing import Optional
from .utils import (
    load_json,
    save_json,
    short_term_store_path,
    phase_signals_path,
    daily_ingestion_state_path,
    today_iso,
    tz_sh,
    derive_concept_tags,
)
from .utils import get_hermes_home

def get_store() -> dict:
    """Load the short-term recall store; create if missing."""
    default = {"version": 1, "updatedAt": datetime.now(tz_sh()).isoformat(), "entries": {}}
    return load_json(short_term_store_path(), default)


def save_store(store: dict) -> None:
    store["updatedAt"] = datetime.now(tz_sh()).isoformat()
    save_json(short_term_store_path(), store)


def get_phase_signals() -> dict:
    default = {"version": 1, "updatedAt": datetime.now(tz_sh()).isoformat(), "entries": {}}
    return load_json(phase_signals_path(), default)


def save_phase_signals(signals: dict) -> None:
    signals["updatedAt"] = datetime.now(tz_sh()).isoformat()
    save_json(phase_signals_path(), signals)


def get_daily_ingestion_state() -> dict:
    default = {"version": 1, "days": {}}
    return load_json(daily_ingestion_state_path(), default)


def save_daily_ingestion_state(state: dict) -> None:
    save_json(daily_ingestion_state_path(), state)


def record_signal(
    store: dict,
    key: str,
    snippet: str,
    concept_tags: list,
    score: float,
    source_path: str,
    day: str,
    query_hash: Optional[str] = None,
) -> None:
    """Record or update a short-term signal entry.

    Dedup: if query_hash is already in queryHashes AND day is already in
    recallDays, this is a repeat within the same scan — skip the signal.
    Different days or different query_hashes always count as new signals.
    """
    entries = store.setdefault("entries", {})
    now_iso = datetime.now(tz_sh()).isoformat()

    if key not in entries:
        entries[key] = {
            "key": key,
            "snippet": snippet,
            "conceptTags": concept_tags,
            "recallCount": 0,
            "dailyCount": 0,
            "groundedCount": 0,
            "totalScore": 0.0,
            "maxScore": 0.0,
            "queryHashes": [],
            "recallDays": [],
            "promotedAt": None,
            "firstSeenAt": now_iso,
            "lastRecalledAt": now_iso,
        }

    entry = entries[key]

    # Dedup: same query_hash + same day → skip
    if query_hash and day:
        if query_hash in entry.get("queryHashes", []) and day in entry.get("recallDays", []):
            return

    entry["recallCount"] = entry.get("recallCount", 0) + 1
    entry["totalScore"] = entry.get("totalScore", 0.0) + score
    entry["maxScore"] = max(entry.get("maxScore", 0.0), score)
    entry["lastRecalledAt"] = now_iso

    # Daily source → dailyCount + 1
    if query_hash and query_hash.startswith("daily:"):
        entry["dailyCount"] = entry.get("dailyCount", 0) + 1

    if day and day not in entry.get("recallDays", []):
        entry["recallDays"].append(day)
        # keep at most MAX_RECALL_DAYS
        if len(entry["recallDays"]) > 16:
            entry["recallDays"] = entry["recallDays"][-16:]

    if query_hash and query_hash not in entry.get("queryHashes", []):
        entry["queryHashes"].append(query_hash)
        if len(entry["queryHashes"]) > 20:
            entry["queryHashes"] = entry["queryHashes"][-20:]


def _extract_date_from_filename(filename: str) -> str:
    """Extract YYYY-MM-DD date from a corpus or daily memory filename."""
    stem = Path(filename).stem
    # e.g. "2026-07-08" or "2026-07-08-something"
    parts = stem.split("-")
    if len(parts) >= 3:
        date = "-".join(parts[:3])
        try:
            datetime.strptime(date, "%Y-%m-%d")
            return date
        except ValueError:
            pass
    return stem


def record_daily_signal(
    store: dict,
    key: str,
    snippet: str,
    concept_tags: list,
    source_path: str,
    day: str,
) -> None:
    """Record a daily-ingestion signal with fixed score."""
    from .utils import DAILY_INGESTION_SCORE
    file_date = _extract_date_from_filename(source_path)
    query_hash = f"daily:{file_date}"
    record_signal(store, key, snippet, concept_tags,
                   DAILY_INGESTION_SCORE, source_path, day, query_hash=query_hash)


def record_session_signal(
    store: dict,
    key: str,
    snippet: str,
    concept_tags: list,
    source_path: str,
    day: str,
) -> None:
    """Record a session-transcript signal with fixed score."""
    from .utils import SESSION_INGESTION_SCORE
    file_date = _extract_date_from_filename(source_path)
    query_hash = f"session:{file_date}"
    record_signal(store, key, snippet, concept_tags,
                   SESSION_INGESTION_SCORE, source_path, day, query_hash=query_hash)
