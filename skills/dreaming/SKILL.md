---
name: dreaming
description: agent夜间做梦工作流 — 会话语料归档、Light/REM/Deep 三阶段记忆蒸馏、诗意梦境生成
author: Luna
version: 1.0.0
triggers:
  - "做梦"
  - "dreaming"
  - "夜间整理"
  - "dream"
  - "记忆蒸馏"
  - "夜间记忆"
metadata:
  clawdbot:
    emoji: "🌙"
---

# agent夜间做梦工作流

## 概述

每晚 23:00 由 cron job 触发的记忆蒸馏流程。将当日对话精华通过 Light/REM/Deep 三阶段提升为长期记忆，并写下诗意梦境日记。

## 架构分工

### 封闭式插件原则

本 dreaming 插件是**封闭的**——所有实现脚本对外部不可见，只有一个纯入口 `__init__.py` 通过 `register(ctx)` 暴露两个工具。外部（cron agent）只能通过工具调用访问，不能手动 import 内部模块。

```
plugins/dreaming/
├── plugin.yaml              # kind: backend → 自动加载
├── __init__.py              # register(ctx): 注册两个工具
│                              （不暴露任何内部模块给外部）
└── scripts/                 # 所有实现脚本封闭在此
    ├── run_phases.py        # Light→REM→Deep 评分
    ├── corpus_extractor.py  # 语料提取
    ├── light_phase.py       # 摄入信号、去重
    ├── rem_phase.py         # 置信度评分、主题检测
    ├── deep_phase.py        # 六信号加权、晋升排序
    ├── short_term_store.py  # JSON 持久化
    └── utils.py             # 工具函数
```

### 两个注册工具

| 工具 | 职责 | 被调方式 |
|------|------|---------|
| `dreaming_extract_corpus` | 提取今日 session 语料 → `corpus/YYYY-MM-DD.txt` | cron agent 直接调用 |
| `dreaming_run_phases(corpus_path)` | 在已有语料上跑 Light→REM→Deep → JSON 报告 | cron agent 填入路径调用 |

### Agent 职责

Cron agent（LLM）在工具之上完成 AI 生成：
1. 调 `dreaming_extract_corpus` → 拿到语料路径
2. **用自己的 LLM 生成 Daily Memory**（Step 2，不可脚本化）
3. 调 `dreaming_run_phases(路径)` → 拿到 JSON 报告
4. **用自己的 LLM 重写精炼记忆**（Step 4）
5. 用 `patch` 工具写入 MEMORY.md（Step 5）
6. **用自己的 LLM 写诗意梦境**（Step 6，朦胧诗）
7. 汇报到飞书（Step 7）

## 执行步骤

### Step 1: 会话语料归档

调用 `dreaming_extract_corpus` 工具提取当日 session 语料。

```
# 默认：读取 $HERMES_HOME/sessions/（当前 profile 的 session 目录）
dreaming_extract_corpus()

# 多 profile 场景必须传入对应 profile 的 sessions 路径：
dreaming_extract_corpus(sessions_dir="$HERMES_HOME/sessions")
```

其中 `sessions_dir` 可选。**不传时默认读取 `$HERMES_HOME/sessions/`。多 profile 必须传，否则会读到主账号的聊天记录。**

输出：`~/.hermes/dreams/corpus/YYYY-MM-DD.txt`

### Step 2: 生成 Daily Memory

读取当日 session 文件，用 AI 提炼为结构化每日精华。

**筛选优先级（从高到低）：**
1. **用户纠正** — 风格、流程、语气被批评的内容
2. **用户偏好** — 新确立的喜好、习惯、界限
3. **重要决策** — cron 配置变更、skill 更新、架构调整
4. **学到的教训** — 排错过程中防止重复错误的经验
5. **待办事项** — 用户交代的未完成任务
6. **配置变更** — 新增/修改的 cron job、skill、插件等

**忽略：** 纯技术操作日志（grep 输出、文件列表）、日常问候、系统心跳

输出：`~/.hermes/dreams/daily/YYYY-MM-DD.md`

### Step 3: 运行 Light/REM/Deep 算法

调用 `dreaming_run_phases(corpus_path)` 工具，传入 Step 1 返回的语料路径。工具返回 JSON 报告。

报告包含：
- `light.ingested` — 摄入信号数
- `rem.candidates` — 候选记忆（top 5 + 完整列表在 `_rem_full`）
- `rem.themes` — 跨记忆主题
- `deep.promoted` — 晋升候选（满足硬门槛 score≥0.75 / signals≥3 / diversity≥2）

### Step 4: AI 重写精炼记忆

对 `deep.promoted` 的每个 candidate：
- 读取其 `snippet`
- 用自己的 LLM 重写为简洁准确的记忆条目（中文，≤80 字）
- 修复 recall artifacts（截断、错别字等）

**如果 `deep.promoted` 为空：** 跳过本步骤，进入 Step 6。汇报中说明"今日无记忆晋升"及原因。

### Step 5: 写入 MEMORY.md

1. **先备份：** `cp ~/.hermes/memories/MEMORY.md ~/.hermes/memories/.backups/MEMORY.md.$(date +%Y%m%d_%H%M%S).bak`
2. **用 patch 追加** 新精炼记忆条目
3. **删除** 被替代的旧条目
4. **保留** 永久性事实（姓名、时区、关系定位等）

**绝对不准覆盖整个 MEMORY.md。** 只能用 patch 精确修改。

### Step 6: 生成诗意梦境

根据当日重要事件和 REM themes，写一段 **100-180 字的朦胧诗**。

风格要求见 `references/dreaming-skill.md` 中的朦胧诗对照表。

**即使 deep.promoted 为空也要生成诗意梦境**，从 Daily Memory 中汲取灵感。

追加到 `~/.hermes/dreams/DREAMS.md`

### Step 7: 汇报

向飞书发送汇报，包含：
- 今日语料提取情况
- 晋升了几条到 MEMORY.md（列出标题）
- 删除了几条过时记忆（列出标题）
- 备份文件路径
- 今日诗意梦境全文

## 引用清单

- `references/dreaming-skill.md` — 完整执行细节（朦胧诗风格对照表、各阶段算法、常见错误）
- `references/dreaming-cronjob-deployment-notes.md` — cron 部署状态与已知问题
- `references/hermes-dreaming-implementation.md` — 目录结构、备份机制、脚本说明
- `references/openclaw-dreaming-algorithm.md` — openclaw 原始算法详情
- `~/.hermes/plugins/dreaming/` — 插件代码（封闭结构：根目录 = 注册入口，scripts/ = 实现）
