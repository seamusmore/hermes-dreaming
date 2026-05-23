"""Extract daily conversation corpus from Hermes session files.

Ported from OpenClaw's engine-qmd session transcript logic:
- Skip non-message records
- Extract text from string or content-array blocks
- Strip system/cron/heartbeat wrapper messages
- Soft-wrap long lines at 280 chars
- Annotate each line with source file and line number
"""

import json
import glob
import re
from pathlib import Path
from scripts.utils import sessions_dir, dreams_dir, today_iso, today_compact, tz_sh

SESSION_EXPORT_CONTENT_WRAP_CHARS = 280

# Patterns matching OpenClaw's filter logic
GENERATED_SYSTEM_MESSAGE_RE = re.compile(r"^System(?: \(untrusted\))?: \[[^\]]+\]\s*")
DIRECT_CRON_PROMPT_RE = re.compile(r"^\[Cron\]|^Scheduled task:|^Cron job:", re.I)
HEARTBEAT_MARKER = "HEARTBEAT_OK"

# Hermes-specific cron preamble (injected into user messages by cron runtime)
HERMES_CRON_PREAMBLE_RE = re.compile(r"^\[IMPORTANT: You are running as a scheduled cron job", re.I)
HERMES_SILENT_MARKER_RE = re.compile(r"^\[SILENT\]|^SILENT:", re.I)


def _collect_raw_session_text(content) -> str | None:
    """Mirror OpenClaw collectRawSessionText()."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts = []
    for block in content:
        if not block or not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts) if parts else None


def _is_generated_system_wrapper(text: str, role: str) -> bool:
    return role == "user" and bool(GENERATED_SYSTEM_MESSAGE_RE.match(text))


def _is_generated_cron_prompt(text: str, role: str) -> bool:
    return role == "user" and bool(DIRECT_CRON_PROMPT_RE.search(text))


def _is_hermes_cron_preamble(text: str, role: str) -> bool:
    return role == "user" and bool(HERMES_CRON_PREAMBLE_RE.search(text))


def _is_hermes_silent_marker(text: str, role: str) -> bool:
    return role == "user" and bool(HERMES_SILENT_MARKER_RE.search(text))


def _is_heartbeat_message(text: str, role: str) -> bool:
    return role == "user" and HEARTBEAT_MARKER in text


def _strip_internal_runtime_context(text: str) -> str:
    """Remove compacted-context markers like [CONTEXT COMPACTION]."""
    lines = text.splitlines()
    filtered = []
    skip = False
    for line in lines:
        if "[CONTEXT COMPACTION" in line or "[HISTORY SNAPSHOT" in line:
            skip = True
            continue
        if skip and line.strip() == "":
            skip = False
            continue
        if not skip:
            filtered.append(line)
    return "\n".join(filtered)


def _sanitize_session_text(text: str, role: str) -> str | None:
    """Mirror OpenClaw sanitizeSessionText() pipeline + Hermes-specific filters."""
    text = text.strip()
    if not text:
        return None
    if _is_generated_system_wrapper(text, role):
        return None
    if _is_generated_cron_prompt(text, role):
        return None
    if _is_hermes_cron_preamble(text, role):
        return None
    if _is_hermes_silent_marker(text, role):
        return None
    if _is_heartbeat_message(text, role):
        return None
    # Strip internal runtime context (Hermes-specific)
    text = _strip_internal_runtime_context(text)
    if not text.strip():
        return None
    # Compact whitespace (mirror normalizeSessionText)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text if text else None


def _split_long_line(text: str, max_chars: int = SESSION_EXPORT_CONTENT_WRAP_CHARS) -> list[str]:
    """Mirror OpenClaw splitLongSessionLine()."""
    normalized = text.strip()
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]
    segments = []
    cursor = 0
    while cursor < len(normalized):
        if len(normalized) - cursor <= max_chars:
            segments.append(normalized[cursor:].strip())
            break
        limit = cursor + max_chars
        split_at = limit
        for idx in range(limit, cursor, -1):
            if normalized[idx] == " ":
                split_at = idx
                break
        if split_at > cursor:
            segments.append(normalized[cursor:split_at].strip())
            cursor = split_at
            while cursor < len(normalized) and normalized[cursor] == " ":
                cursor += 1
        else:
            # No space found — hard split
            segments.append(normalized[cursor:limit].strip())
            cursor = limit
    return [s for s in segments if s]


def _render_session_lines(label: str, text: str) -> list[str]:
    """Mirror OpenClaw renderSessionExportLines()."""
    return [f"{label}: {segment}" for segment in _split_long_line(text)]


def _parse_session_timestamp_ms(record: dict, message: dict) -> int | None:
    """Extract timestamp from record or message."""
    ts = record.get("timestamp") or record.get("created_at") or message.get("timestamp")
    if isinstance(ts, (int, float)):
        return int(ts)
    return None


def extract_daily_corpus() -> Path:
    """Extract today's sessions into a plain-text corpus file.

    Mirrors OpenClaw buildSessionEntry() + buildSessionRenderedLine() logic.
    """
    corpus_dir = dreams_dir() / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)

    date_prefixes = [today_compact(), today_iso()]
    session_files = []
    for prefix in date_prefixes:
        session_files.extend(glob.glob(str(sessions_dir() / f"*{prefix}*")))
    session_files = sorted(set(session_files))

    all_lines: list[str] = []

    for filepath in session_files:
        basename = Path(filepath).name
        # Read raw content
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                raw_content = f.read()
        except Exception:
            continue

        if not raw_content.strip():
            continue

        # Determine format: JSONL vs JSON array/object
        lines = raw_content.splitlines()
        collected: list[str] = []
        line_map: list[int] = []
        message_timestamps: list[int | None] = []

        if filepath.endswith(".jsonl"):
            for jsonl_idx, line in enumerate(lines, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # OpenClaw: record.type === "message"
                if not isinstance(record, dict) or record.get("type") != "message":
                    continue

                message = record.get("message", record)
                if not isinstance(message, dict):
                    continue

                role = message.get("role", "")
                if role not in ("user", "assistant"):
                    continue

                raw_text = _collect_raw_session_text(message.get("content"))
                if raw_text is None:
                    continue

                text = _sanitize_session_text(raw_text, role)
                if not text:
                    continue

                label = "User" if role == "user" else "Assistant"
                rendered = _render_session_lines(label, text)
                collected.extend(rendered)
                line_map.extend([jsonl_idx] * len(rendered))
                ts = _parse_session_timestamp_ms(record, message)
                message_timestamps.extend([ts] * len(rendered))

        elif filepath.endswith(".json"):
            try:
                data = json.loads(raw_content)
            except json.JSONDecodeError:
                continue

            messages = data.get("messages", [])
            if not isinstance(messages, list):
                continue

            for msg_idx, message in enumerate(messages, start=1):
                if not isinstance(message, dict):
                    continue

                role = message.get("role", "")
                if role not in ("user", "assistant"):
                    continue

                raw_text = _collect_raw_session_text(message.get("content"))
                if raw_text is None:
                    continue

                text = _sanitize_session_text(raw_text, role)
                if not text:
                    continue

                label = "User" if role == "user" else "Assistant"
                rendered = _render_session_lines(label, text)
                collected.extend(rendered)
                line_map.extend([msg_idx] * len(rendered))
                ts = message.get("timestamp")
                message_timestamps.extend([int(ts) if isinstance(ts, (int, float)) else None] * len(rendered))

        if not collected:
            continue

        # Build OpenClaw-style header + annotated lines
        session_scope = f"hermes/sessions/{basename}"
        all_lines.append(f"[{session_scope}]")
        for idx, snippet in enumerate(collected):
            src_line = line_map[idx] if idx < len(line_map) else "?"
            all_lines.append(f"[{session_scope}#L{src_line}] {snippet}")
        all_lines.append("")

    # Write output
    header = [
        f"# Session Corpus — {today_iso()}",
        f"# Extracted from {len(session_files)} session files",
        f"# Format: [hermes/sessions/<file>#L<line>] <Speaker>: <text>",
        "",
    ]
    output_path = corpus_dir / f"{today_iso()}.txt"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(header + all_lines) + "\n")

    return output_path
