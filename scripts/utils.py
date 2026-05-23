"""Shared utilities for the dreaming engine."""

import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants (mirroring openclaw defaults)
# ---------------------------------------------------------------------------
DAY_MS = 1440 * 60 * 1000
DEFAULT_RECENCY_HALF_LIFE_DAYS = 14
DEFAULT_PROMOTION_MIN_SCORE = 0.75
DEFAULT_PROMOTION_WEIGHTS = {
    "frequency": 0.24,
    "relevance": 0.30,
    "diversity": 0.15,
    "recency": 0.15,
    "consolidation": 0.10,
    "conceptual": 0.06,
}
PHASE_SIGNAL_LIGHT_BOOST_MAX = 0.06
PHASE_SIGNAL_REM_BOOST_MAX = 0.09
PHASE_SIGNAL_HALF_LIFE_DAYS = 14
DAILY_INGESTION_SCORE = 0.62
SESSION_INGESTION_SCORE = 0.58
MAX_RECALL_DAYS = 16


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def get_hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))


def dreams_dir() -> Path:
    return get_hermes_home() / "dreams"


def memories_dir() -> Path:
    return get_hermes_home() / "memories"


def sessions_dir() -> Path:
    return get_hermes_home() / "sessions"


def short_term_store_path() -> Path:
    return dreams_dir() / ".store" / "short-term-recall.json"


def phase_signals_path() -> Path:
    return dreams_dir() / ".store" / "phase-signals.json"


def daily_ingestion_state_path() -> Path:
    return dreams_dir() / ".store" / "daily-ingestion.json"


def backup_dir() -> Path:
    return memories_dir() / ".backups"


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def tz_sh() -> timezone:
    return timezone(timedelta(hours=8))


def today_iso() -> str:
    return datetime.now(tz_sh()).strftime("%Y-%m-%d")


def today_compact() -> str:
    return datetime.now(tz_sh()).strftime("%Y%m%d")


def iso_day(epoch_ms: int, tz: timezone = None) -> str:
    tz = tz or tz_sh()
    return datetime.fromtimestamp(epoch_ms / 1000, tz=tz).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Score helpers
# ---------------------------------------------------------------------------
def clamp_score(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def calculate_recency_component(age_days: float, half_life_days: float = DEFAULT_RECENCY_HALF_LIFE_DAYS) -> float:
    if not math.isfinite(age_days) or age_days < 0:
        return 1.0
    if not math.isfinite(half_life_days) or half_life_days <= 0:
        return 1.0
    lam = math.log(2) / half_life_days
    return math.exp(-lam * age_days)


def entry_average_score(entry: dict) -> float:
    signal_count = max(0, math.floor(entry.get("recallCount", 0) or 0)) + max(0, math.floor(entry.get("dailyCount", 0) or 0)) + max(0, math.floor(entry.get("groundedCount", 0) or 0))
    if signal_count <= 0:
        return 0.0
    return clamp_score(entry.get("totalScore", 0) / signal_count)


def total_signal_count(entry: dict) -> int:
    return max(0, math.floor(entry.get("recallCount", 0) or 0)) + max(0, math.floor(entry.get("dailyCount", 0) or 0)) + max(0, math.floor(entry.get("groundedCount", 0) or 0))


def calculate_consolidation_component(recall_days: list) -> float:
    if not recall_days:
        return 0.0
    if len(recall_days) == 1:
        return 0.2
    parsed = []
    for d in recall_days:
        try:
            ts = datetime.strptime(d, "%Y-%m-%d").timestamp()
            parsed.append(ts)
        except Exception:
            continue
    if len(parsed) <= 1:
        return 0.2
    parsed.sort()
    span_days = max(0, (parsed[-1] - parsed[0]) / 86400)
    spacing = clamp_score(math.log1p(len(parsed) - 1) / math.log1p(4))
    span = clamp_score(span_days / 7)
    return clamp_score(0.55 * spacing + 0.45 * span)


def calculate_conceptual_component(concept_tags: list) -> float:
    return clamp_score(len(concept_tags) / 6)


def calculate_phase_signal_boost(phase_entry: dict | None, now_ms: int) -> float:
    if not phase_entry:
        return 0.0
    light_hits = max(0, phase_entry.get("lightHits", 0))
    rem_hits = max(0, phase_entry.get("remHits", 0))
    light_strength = clamp_score(math.log1p(light_hits) / math.log1p(6))
    rem_strength = clamp_score(math.log1p(rem_hits) / math.log1p(6))

    light_age = _phase_signal_age_days(phase_entry.get("lastLightAt"), now_ms)
    rem_age = _phase_signal_age_days(phase_entry.get("lastRemAt"), now_ms)

    light_recency = 0.0 if light_age is None else clamp_score(calculate_recency_component(light_age, PHASE_SIGNAL_HALF_LIFE_DAYS))
    rem_recency = 0.0 if rem_age is None else clamp_score(calculate_recency_component(rem_age, PHASE_SIGNAL_HALF_LIFE_DAYS))

    return clamp_score(PHASE_SIGNAL_LIGHT_BOOST_MAX * light_strength * light_recency + PHASE_SIGNAL_REM_BOOST_MAX * rem_strength * rem_recency)


def _phase_signal_age_days(last_seen_at: str | None, now_ms: int) -> float | None:
    if not last_seen_at:
        return None
    try:
        parsed = datetime.fromisoformat(last_seen_at.replace("Z", "+00:00")).timestamp() * 1000
        if not math.isfinite(parsed):
            return None
        return max(0, (now_ms - parsed) / DAY_MS)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Concept tag extraction (simplified CJK + latin)
# ---------------------------------------------------------------------------
def tokenize_snippet(snippet: str) -> set:
    return set(re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", snippet.lower()))


def jaccard_similarity(left: str, right: str) -> float:
    left_tokens = tokenize_snippet(left)
    right_tokens = tokenize_snippet(right)
    if not left_tokens or not right_tokens:
        return 1.0 if left.strip().lower() == right.strip().lower() else 0.0
    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return intersection / union if union > 0 else 0.0


def derive_concept_tags(path: str, snippet: str, limit: int = 8) -> list:
    source = f"{Path(path).name} {snippet}"
    tags = []
    # Simple extraction: 3+ char tokens that look like meaningful words
    tokens = re.findall(r"[a-zA-Z]{3,}|[\u4e00-\u9fff]{2,}", source.lower())
    seen = set()
    for t in tokens:
        if t in seen:
            continue
        seen.add(t)
        tags.append(t)
        if len(tags) >= limit:
            break
    return tags


# ---------------------------------------------------------------------------
# JSON store helpers
# ---------------------------------------------------------------------------
def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
