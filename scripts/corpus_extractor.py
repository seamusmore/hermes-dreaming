"""Extract daily conversation corpus from Hermes session files.

Ported from OpenClaw's engine-qmd session transcript logic:
- Skip non-message records
- Extract text from string or content-array blocks
- Strip system/cron/heartbeat wrapper messages
- Soft-wrap long lines at 280 chars
- Annotate each line with source file and line number

Primary source: SQLite state.db (Hermes 0.14+ canonical store).
Fallback: disk files in ~/.hermes/sessions/.
"""

import json
import glob
import re
import sqlite3
from pathlib import Path
from .utils import sessions_dir, dreams_dir, today_iso, today_compact, tz_sh, get_hermes_home

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


def _strip_code_blocks(text: str) -> str:
    """Remove fenced code blocks (```...```) from text.

    Code blocks are noise for memory consolidation — they are raw tool output,
    config snippets, or formatted data, not natural conversation.
    Both the fences and the content between them are removed.

    If a code block is not closed (opening ``` without matching close),
    the content from the opening ``` to the end is kept — we cannot assume
    it is a code block without a closing fence.
    """
    lines = text.splitlines()
    result = []
    in_code_block = False
    code_start_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_start_idx = i
            else:
                in_code_block = False
                code_start_idx = -1
            continue
        if in_code_block:
            continue
        result.append(line)

    # Unclosed code block: keep everything from the opening ``` onward
    if in_code_block and code_start_idx >= 0:
        result.extend(lines[code_start_idx:])

    return "\n".join(result)


def _strip_image_markers(text: str) -> str:
    """Remove image placeholder lines like [Image: ...] and [IMAGE: ...]."""
    lines = text.splitlines()
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[Image]") or stripped.startswith("[IMAGE:"):
            continue
        if stripped.startswith("MEDIA:"):
            continue
        result.append(line)
    return "\n".join(result)


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
    # Strip code blocks and image markers (noise for memory consolidation)
    text = _strip_code_blocks(text)
    text = _strip_image_markers(text)
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


def _extract_from_state_db() -> list[str]:
    """Extract today's conversations from SQLite state.db (primary source).

    Hermes 0.14+ stores sessions in state.db by default; disk snapshots
    are opt-in.  This function queries state.db when disk files are absent.
    """
    state_db_path = get_hermes_home() / "state.db"
    if not state_db_path.exists():
        return []

    today = today_iso()
    all_lines: list[str] = []
    conn = sqlite3.connect(str(state_db_path))

    sessions = conn.execute("""
        SELECT id, source, title
        FROM sessions
        WHERE date(started_at, 'unixepoch', 'localtime') = ?
          AND source IN ('feishu', 'cli')
        ORDER BY started_at
    """, (today,)).fetchall()

    for sid, source, title in sessions:
        session_scope = f"hermes/state.db/{sid}"
        all_lines.append(f"[{session_scope}]")

        messages = conn.execute("""
            SELECT role, content
            FROM messages
            WHERE session_id = ?
              AND role IN ('user', 'assistant')
            ORDER BY timestamp
        """, (sid,)).fetchall()

        for msg_idx, (role, content) in enumerate(messages, start=1):
            if not content or not content.strip():
                continue
            text = _sanitize_session_text(content, role)
            if not text:
                continue
            label = "User" if role == "user" else "Assistant"
            rendered = _render_session_lines(label, text)
            for snippet in rendered:
                all_lines.append(f"[{session_scope}#L{msg_idx}] {snippet}")

        all_lines.append("")

    conn.close()
    return all_lines


def _extract_from_disk_files() -> list[str]:
    """Extract today's sessions from disk files (fallback)."""
    date_prefixes = [today_compact(), today_iso()]
    session_files = []
    for prefix in date_prefixes:
        session_files.extend(glob.glob(str(sessions_dir() / f"*{prefix}*")))
    session_files = sorted(set(session_files))

    all_lines: list[str] = []

    for filepath in session_files:
        basename = Path(filepath).name
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                raw_content = f.read()
        except Exception:
            continue

        if not raw_content.strip():
            continue

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

        session_scope = f"hermes/sessions/{basename}"
        all_lines.append(f"[{session_scope}]")
        for idx, snippet in enumerate(collected):
            src_line = line_map[idx] if idx < len(line_map) else "?"
            all_lines.append(f"[{session_scope}#L{src_line}] {snippet}")
        all_lines.append("")

    return all_lines


def extract_daily_corpus() -> Path:
    """Extract today's sessions into a plain-text corpus file.

    Primary source: SQLite state.db (Hermes 0.14+ canonical store).
    Fallback: disk files in ~/.hermes/sessions/.
    """
    corpus_dir = dreams_dir() / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)

    all_lines: list[str] = []

    # Primary source: SQLite state.db
    state_lines = _extract_from_state_db()
    if state_lines:
        all_lines = state_lines
        source_label = f"(SQLite state.db: {len(state_lines)} lines)"
    else:
        # Fallback: disk files
        disk_lines = _extract_from_disk_files()
        if disk_lines:
            all_lines = disk_lines
            source_label = f"(disk files: {len(disk_lines)} lines)"
        else:
            source_label = "(no sessions found)"

    # Write output
    total_lines = len(all_lines)
    header = [
        f"# Session Corpus — {today_iso()}",
        f"# Extracted from {total_lines} lines {source_label}",
        f"# Format: [hermes/sessions/<file>#L<line>] <Speaker>: <text>",
        "",
    ]
    output_path = corpus_dir / f"{today_iso()}.txt"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(header + all_lines) + "\n")

    return output_path
