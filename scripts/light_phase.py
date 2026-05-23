"""Light Sleep phase: ingest daily-memory and session-transcript signals."""

import re
from pathlib import Path
from typing import List, Tuple

from scripts.utils import (
    today_iso,
    derive_concept_tags,
    load_json,
    short_term_store_path,
    dreams_dir,
)
from scripts.short_term_store import (
    get_store,
    save_store,
    get_daily_ingestion_state,
    save_daily_ingestion_state,
    record_daily_signal,
    record_session_signal,
)


def _chunk_corpus(corpus_text: str, max_chunk_length: int = 800) -> List[Tuple[str, str]]:
    """Split corpus into (summary, snippet) chunks."""
    lines = corpus_text.splitlines()
    chunks = []
    current_lines = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("---"):
            if current_lines:
                snippet = "\n".join(current_lines)
                summary = current_lines[0][:120]
                chunks.append((summary, snippet))
                current_lines = []
            continue
        current_lines.append(line)
        total_len = sum(len(l) for l in current_lines)
        if total_len >= max_chunk_length:
            snippet = "\n".join(current_lines)
            summary = current_lines[0][:120]
            chunks.append((summary, snippet))
            current_lines = []

    if current_lines:
        snippet = "\n".join(current_lines)
        summary = current_lines[0][:120]
        chunks.append((summary, snippet))

    return chunks


def _chunk_daily_memory(daily_text: str) -> List[Tuple[str, str]]:
    """Split daily memory markdown into (summary, snippet) chunks.
    Each non-empty, non-markdown line becomes its own chunk."""
    chunks = []
    for line in daily_text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip pure markdown/formatting lines
        if line.startswith("#") or line.startswith("---") or line.startswith("```"):
            continue
        # Skip image/media markers
        if line.startswith("!") or line.startswith("MEDIA:"):
            continue
        # Use first 120 chars as summary, full line as snippet
        summary = line[:120]
        chunks.append((summary, line))
    return chunks


def _make_key(snippet: str) -> str:
    """Derive a stable key from the first line of a snippet."""
    first = snippet.splitlines()[0] if snippet else ""
    cleaned = re.sub(r"[^\u4e00-\u9fff\w]", "", first[:80])
    return cleaned.strip() or "unknown"


def _ingest_corpus(store, corpus_path: Path, day: str, day_state: dict) -> int:
    """Ingest a single corpus file. Returns count ingested."""
    corpus_key = f"corpus:{corpus_path.name}"
    if day_state.get(corpus_key):
        return 0

    text = corpus_path.read_text(encoding="utf-8", errors="replace")
    chunks = _chunk_corpus(text)

    ingested = 0
    for summary, snippet in chunks:
        key = _make_key(snippet)
        if not key or len(key) < 3:
            continue
        concept_tags = derive_concept_tags(str(corpus_path), snippet)
        record_session_signal(store, key, summary, concept_tags, str(corpus_path), day)
        ingested += 1

    day_state[corpus_key] = True
    return ingested


def _ingest_daily_file(store, daily_path: Path, day: str, day_state: dict) -> int:
    """Ingest a single daily memory file. Returns count ingested."""
    daily_key = f"daily:{daily_path.name}"
    if day_state.get(daily_key):
        return 0

    text = daily_path.read_text(encoding="utf-8", errors="replace")
    chunks = _chunk_daily_memory(text)

    ingested = 0
    for summary, snippet in chunks:
        key = _make_key(snippet)
        if not key or len(key) < 3:
            continue
        concept_tags = derive_concept_tags(str(daily_path), snippet)
        record_daily_signal(store, key, summary, concept_tags, str(daily_path), day)
        ingested += 1

    day_state[daily_key] = True
    return ingested


def run_light_phase(corpus_path: Path) -> dict:
    """
    Ingest corpus and daily memory into short-term store.
    Returns: {"ingested": int, "skipped": int, "store_path": str}
    """
    store = get_store()
    ingestion_state = get_daily_ingestion_state()
    day = today_iso()

    day_state = ingestion_state.setdefault("days", {}).setdefault(day, {})

    total_ingested = 0

    # 1. Ingest session corpus
    if corpus_path.exists():
        total_ingested += _ingest_corpus(store, corpus_path, day, day_state)

    # 2. Ingest daily memory files for today
    daily_dir = dreams_dir() / "daily"
    if daily_dir.exists():
        for daily_file in daily_dir.iterdir():
            if daily_file.is_file() and daily_file.name.startswith(day):
                total_ingested += _ingest_daily_file(store, daily_file, day, day_state)

    save_store(store)
    save_daily_ingestion_state(ingestion_state)

    return {"ingested": total_ingested, "skipped": 0, "store_path": str(short_term_store_path())}
