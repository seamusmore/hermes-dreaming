# dreaming — Hermes's Nightly Memory Consolidation Plugin

A Hermes agent plugin that performs nightly memory consolidation using the
openclaw-inspired Light/REM/Deep dreaming algorithm.

## What It Does

Every night at 23:00, this plugin runs a memory consolidation pipeline:

1. **Extract** — Pulls today's conversation transcripts into a structured corpus
2. **Light Sleep** — Ingests corpus signals into a short-term recall store
3. **REM Sleep** — Pattern recognition: scores candidates, detects recurring themes
4. **Deep Sleep** — Weighted scoring with six signals, promotes worthy entries
   to long-term memory

The cron agent then uses its own LLM to:
- Generate a structured daily memory summary
- Rewrite promoted candidates into concise memory entries
- Write a poetic dream diary entry (朦胧诗 style)
- Send a consolidation report

## Architecture

```
plugins/dreaming/
├── plugin.yaml        ← Plugin manifest (kind: backend)
├── __init__.py        ← Registers 2 tools + 1 built-in skill
├── scripts/
│   ├── corpus_extractor.py    ← Extract session transcripts
│   ├── light_phase.py         ← Light Sleep: signal ingestion
│   ├── rem_phase.py           ← REM Sleep: pattern recognition
│   ├── deep_phase.py          ← Deep Sleep: weighted scoring + promotion
│   ├── run_phases.py          ← Orchestrator: light → rem → deep
│   ├── short_term_store.py    ← JSON-backed recall store
│   └── utils.py               ← Shared utilities
└── skills/dreaming/
    ├── SKILL.md               ← Workflow guidance for the cron agent
    └── references/            ← Algorithm details, deployment notes
```

### Principle

```
Plugin scripts = deterministic algorithms
Cron agent     = AI generation (LLM)
```

The plugin handles all math, scoring, and data persistence. The cron agent
handles all LLM-dependent work: rewriting memories, generating poetic dreams,
and sending reports.

## Registered Tools

| Tool | Purpose |
|------|---------|
| `dreaming_extract_corpus` | Extract today's session corpus |
| `dreaming_run_phases` | Run Light → REM → Deep, return JSON report |

## Prerequisites

- Hermes Agent (tested with 0.14+)
- Python 3.11+

## Installation

### Option 1: Install via Hermes CLI (recommended)

If the plugin is published on GitHub:

```bash
hermes plugins install https://github.com/seamusmore/hermes-dreaming.git
```

### Option 2: Manual installation (local)

Download from https://github.com/seamusmore/hermes-dreaming.git, copy it manually:

```bash
cp -r /path/to/dreaming ~/.hermes/plugins/dreaming
```

Restart the gateway to pick up the plugin:

```bash
hermes gateway restart
```

## Usage

### Prerequisites

The plugin requires a cron job to run nightly. This is **not** created
automatically by the plugin installer.

### Setting up the cron job

> **⚠️ 关键：** `--skills` **必须指定为** `dreaming:dreaming`（插件名:技能名），**不能只写** `dreaming`。这是插件提供的内建技能引用格式，写错了 cron agent 将无法加载工作流。

After the plugin is loaded and the gateway is running, create the cron job:

```bash
hermes cron create \
  --name "Agent夜间做梦 - 每天23:00" \
  --schedule "0 23 * * *" \
  --skills dreaming:dreaming \
  --deliver "feishu:<your-feishu-chat-id>" \
  --prompt '加载 `dreaming:dreaming` skill，执行其中的夜间记忆蒸馏（做梦）工作流。按 skill 步骤执行后，生成汇报发到飞书。'
```

Replace `<your-feishu-chat-id>` with the actual chat ID where reports
should be delivered (e.g. `oc_b84xxxxxxxxxx`).

You can verify the job is scheduled:

```bash
hermes cron list
```

### Data Dependencies

The plugin reads and writes data under `~/.hermes/dreams/`:

```
.dreams/
├── DREAMS.md              ← Poetic dream diary
├── daily/                 ← AI-generated daily memory summaries
├── corpus/                ← Session transcript archives
└── .store/                ← Algorithm state (short-term recall, phase signals)
```

## Cron Job

The nightly consolidation is triggered by a Hermes cron job:

- **Schedule:** `0 23 * * *` (every night at 23:00)
- **Skill:** `dreaming:dreaming`
- **Prompt:** "加载 `dreaming:dreaming` skill，执行其中的夜间记忆蒸馏工作流"

## Algorithm Overview

### Light Sleep
- Scans corpus (score: 0.58) and daily memory (score: 0.62)
- De-duplicates by Jaccard similarity
- Records signals to short-term recall store

### REM Sleep
- Scores candidates using: `avgScore×0.45 + recallStrength×0.25 + consolidation×0.20 + conceptual×0.10`
- Detects concept themes (strength ≥ 0.15)

### Deep Sleep
- Six weighted signals:

| Signal | Weight | Formula |
|--------|--------|---------|
| Frequency | 0.24 | log1p(signals) / log1p(10) |
| Relevance | 0.30 | totalScore / signalCount |
| Diversity | 0.15 | max(uniqueQueries, recallDays) / 5 |
| Recency | 0.15 | Exponential decay, half-life 14 days |
| Consolidation | 0.10 | Cross-day span + coverage |
| Conceptual | 0.06 | conceptTags / 6 |

- Promotion threshold: score ≥ 0.75, signals ≥ 3, diversity ≥ 2

## License

Copyright (c) 2026 Seamus. All rights reserved.
