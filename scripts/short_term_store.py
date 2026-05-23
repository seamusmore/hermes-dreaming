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
    """Record or update a short-term signal entry."""
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
    entry["recallCount"] = entry.get("recallCount", 0) + 1
    entry["totalScore"] = entry.get("totalScore", 0.0) + score
    entry["maxScore"] = max(entry.get("maxScore", 0.0), score)
    entry["lastRecalledAt"] = now_iso

    if day and day not in entry.get("recallDays", []):
        entry["recallDays"].append(day)
        # keep at most MAX_RECALL_DAYS
        if len(entry["recallDays"]) > 16:
            entry["recallDays"] = entry["recallDays"][-16:]

    if query_hash and query_hash not in entry.get("queryHashes", []):
        entry["queryHashes"].append(query_hash)
        if len(entry["queryHashes"]) > 20:
            entry["queryHashes"] = entry["queryHashes"][-20:]


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
    record_signal(store, key, snippet, concept_tags, DAILY_INGESTION_SCORE, source_path, day)

    entries = store.setdefault("entries", {})
    if key in entries:
        entries[key]["dailyCount"] = entries[key].get("dailyCount", 0) + 1


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
    record_signal(store, key, snippet, concept_tags, SESSION_INGESTION_SCORE, source_path, day)
