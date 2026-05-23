# Hermes 做梦机制落地实施

来源：2026-05-10 会话 — 用户让露娜学习 openclaw 记忆架构并在 Hermes 中落地。

---

## 目录结构

```
~/.hermes/
└── dreams/
    ├── DREAMS.md              # 诗意梦境日记（用户可读，诗意叙事）
    ├── daily/                 # AI 生成的每日结构记忆
    │   └── YYYY-MM-DD.md
    └── corpus/                # 从 sessions 提取的纯文本语料
        └── YYYY-MM-DD.txt
```

## 关键约束

- 不动 `~/.hermes/AGENTS.md`——升级会被覆盖
- 不创建 `SESSION-STATE.md`——Hermes 的 todo/状态追踪已覆盖
- 不创建 `working-buffer.md`——同上
- MEMORY.md 是自动注入的，不需手动读
- DREAMS.md 按需 read，不是自动注入

## 插件

插件位于 `~/.hermes/plugins/dreaming/`，核心文件：
- `corpus_extractor.py` — 从 `~/.hermes/sessions/` 提取当日对话语料，支持 JSON/JSONL
- `light_phase.py` / `rem_phase.py` / `deep_phase.py` — 三阶段算法
- `scripts/run_dreaming.py` — 总调度脚本，输出 JSON 报告供 agent 消化

备份路径格式：`MEMORY.md.YYYYMMDD_HHMMSS.bak`

## Cron 配置

Job ID: `7a01dc14395b`
- 时间：每晚 23:00
- 流程：备份 MEMORY.md → Light Sleep → REM Sleep → Deep Sleep → DREAMS → 飞书汇报
- Skills: `dreaming`
- Deliver: `feishu:<your-feishu-chat-id>`

**汇报内容：**
- 提取了多少条候选记忆
- 晋升了几条到 MEMORY.md（列出标题）
- 清理了几条过时记忆（列出标题）
- 备份文件路径
- 今日诗意梦境全文

## 安全规则（硬约束）

Deep Sleep 更新 MEMORY.md 时：
- ❌ 不准覆盖整个文件
- ✅ 每次做梦前必须先备份 MEMORY.md
- ✅ 只能用 `patch` 做精确增量修改
- ✅ 如果 patch 失败或文件被破坏，立即从备份恢复
- ✅ 每次 patch 后重新读取确认完整性

## 成本

每晚约 8K token（含 Light + REM + Deep + DREAMS），约 ¥0.04。
语料提取几乎零成本。
