"""
Hermes Dreaming Plugin
====================

A Hermes backend plugin that provides:
- 2 tools for the nightly memory consolidation pipeline
- 1 built-in skill (dreaming) for the cron agent workflow

Tools:
  dreaming_extract_corpus  — extract today's session corpus
  dreaming_run_phases      — run Light/REM/Deep scoring on a corpus file

Tools are deterministic (no LLM calls). The cron agent calls them
in sequence, then uses its own LLM for AI generation.

Skill:
  dreaming:dreaming  — full workflow guidance for the cron agent
"""

from pathlib import Path

from .scripts.corpus_extractor import extract_daily_corpus
from .scripts.run_phases import run_phases


EXTRACT_CORPUS_SCHEMA = {
    "name": "dreaming_extract_corpus",
    "description": "Extract today's conversation corpus from Hermes session files into ~/.hermes/dreams/corpus/YYYY-MM-DD.txt",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}


RUN_PHASES_SCHEMA = {
    "name": "dreaming_run_phases",
    "description": "Run Light/REM/Deep sleep phases on an already-extracted corpus file. Returns JSON report with candidates, themes, and promoted entries.",
    "parameters": {
        "type": "object",
        "properties": {
            "corpus_path": {
                "type": "string",
                "description": "Absolute path to the corpus file (e.g., ~/.hermes/dreams/corpus/2026-05-23.txt)",
            },
        },
        "required": ["corpus_path"],
    },
}


def _handle_extract_corpus(args=None, **kwargs) -> str:
    """Handler for dreaming_extract_corpus tool."""
    import json
    corpus_path = extract_daily_corpus()
    return json.dumps({"corpus_path": str(corpus_path)})


def _handle_run_phases(args=None, **kwargs) -> str:
    """Handler for dreaming_run_phases tool."""
    import json
    corpus_path = args.get("corpus_path") if isinstance(args, dict) else str(args)
    return json.dumps(run_phases(corpus_path))


def register(ctx) -> None:
    """Register dreaming tools and built-in skill. Called once by the plugin loader."""
    ctx.register_tool(
        name="dreaming_extract_corpus",
        toolset="dreaming",
        schema=EXTRACT_CORPUS_SCHEMA,
        handler=_handle_extract_corpus,
        emoji="📝",
    )
    ctx.register_tool(
        name="dreaming_run_phases",
        toolset="dreaming",
        schema=RUN_PHASES_SCHEMA,
        handler=_handle_run_phases,
        emoji="🧠",
    )

    # Register built-in dreaming skill
    skill_md = Path(__file__).parent / "skills" / "dreaming" / "SKILL.md"
    ctx.register_skill(
        "dreaming",
        skill_md,
        description="agent夜间做梦工作流 — 会话语料归档、三阶段记忆蒸馏、诗意梦境生成",
    )
