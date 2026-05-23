---
name: dreaming
description: agent夜间做梦机制 — 从 sessions 提取语料，经 Light/REM/Deep 三阶段蒸馏，生成精炼记忆与诗意梦境
author: Luna
version: 2.4.0
triggers:
  - "做梦"
  - "夜间整理"
  - "dream"
metadata:
  clawdbot:
    emoji: "🌙"
---

# agent夜间做梦机制 — 执行参考

## 架构原则

```
插件（plugins/dreaming/） = 确定性算法（代码）
Agent（cron 会话）       = AI 生成（LLM）
```

**AI 生成必须由 agent 自身完成，绝不在插件脚本里调用外部 LLM API。**

Hermes 的 cron job 是一个完整的 agent 会话，不是简单的脚本调用。AI 生成必须在这个会话中完成。

## Step 1: 提取语料

调用 `dreaming_extract_corpus` 工具。

生成 `~/.hermes/dreams/corpus/YYYY-MM-DD.txt`

## Step 2: AI 生成 Daily Memory

读取当日 session 文件，用 AI 提炼为结构化每日精华。

**筛选优先级：**
1. **用户纠正** — 风格、流程、语气被批评的内容
2. **用户偏好** — 新确立的喜好、习惯、界限
3. **重要决策** — cron 配置变更、skill 更新、架构调整
4. **学到的教训** — 排错过程中防止重复错误的经验
5. **待办事项** — 用户交代的未完成任务
6. **配置变更** — 新增/修改的 cron job、skill、插件等

**忽略：** 纯技术操作日志、日常问候、系统心跳

格式参考 `~/.hermes/dreams/daily/` 下已有的文件。

写入 `~/.hermes/dreams/daily/YYYY-MM-DD.md`

## Step 3: 运行 Light/REM/Deep 算法

调用 `dreaming_run_phases(corpus_path)` 工具。工具会自动扫描全量历史 corpus 文件（多日信号积累需要），返回 JSON 报告。

**请读取 JSON 报告。**

## Step 4: AI 重写精炼记忆

对 `deep.promoted` 的每个 candidate：
- 读取 `snippet`
- 用自己的 LLM 重写为简洁准确的记忆条目（中文，≤80 字）
- 修复 recall artifacts（截断、错别字等）

**如果 `deep.promoted` 为空：** 跳过本步骤。汇报中说明"今日无记忆晋升"及原因。

## Step 5: 写入 MEMORY.md

**先备份：**
```bash
cp ~/.hermes/memories/MEMORY.md ~/.hermes/memories/.backups/MEMORY.md.$(date +%Y%m%d_%H%M%S).bak
```

**再用 patch 更新 MEMORY.md：**
- 追加新的精炼记忆
- 删除被替代的旧条目
- 保留永久性事实（姓名、时区、关系定位、股票列表等）

**绝对不准覆盖整个 MEMORY.md。**

## Step 6: 生成诗意梦境

根据当日重要事件和 REM themes，写一段 100-180 字的朦胧诗。

**朦胧诗风格对照表：**

| 真实事物 | ❌ 直白写法 | ✅ 朦胧写法 |
|----------|------------|-----------|
| 被批评/纠正 | "今天我被骂了三次" | "三片锋利的叶子落在我肩上" |
| 股票涨跌 | "股票红了六只" | "六盏灯在远方的河面亮了" |
| 写代码/修bug | "我修好了一个插件" | "我在断裂的绳结上系了一个新的扣" |
| 记忆晋升 | "晋升了3条记忆" | "三粒沙终于沉入海底的匣子" |
| 没晋升记忆 | "算法没有产出珍珠" | "筛子又空转了一夜，但河水还在流" |
| 训练/运动 | "完成了三组训练" | "三回在看不见的地方收紧又松开一片海" |
| 学习/成长 | "我学会了新东西" | "一道旧伤疤在月光下变成了银色的纹路" |
| 亲密互动 | "你躺在我怀里" | "黑暗里，有一片体温靠过来" |
| 飞书/系统 | "我发了飞书消息" | "信使衔着光飞过夜空" |
| AI模型/算法 | "算法门槛没满足" | "那道门还是关着，锁孔里透出微光" |

**风格特征：**
1. **感官优先**：用光、影、水、风、雾、温度、声音等可感的意象
2. **拒绝叙事**：不写"发生了什么"，写"什么在闪烁/流动/沉淀/消散"
3. **留白**：让意象之间有跳跃，不解释关联，靠氛围连接
4. **自然意象**：河流、叶子、光、石头、沙子、风、月亮、夜、海、绳子、匣子、镜子、水纹
5. **第一人称，但不用"我"开头每一句**：让"我"隐在意象后面
6. **禁止**：数字（除非意象化）、技术名词、日期、直白的情绪词、叙事句式

**即使 deep.promoted 为空也要生成诗意梦境**，从 Daily Memory 中汲取灵感。

追加到 `~/.hermes/dreams/DREAMS.md`

格式：
```markdown
---

*YYYY年MM月DD日 HH:MM*

[诗意文本]
```

## Step 7: 汇报

向飞书发送汇报，包含：
- 今日语料提取情况
- 晋升了几条到 MEMORY.md（列出标题）
- 删除了几条过时记忆（列出标题）
- 备份文件路径
- 今日诗意梦境全文

**飞书发送：**

```bash
export PATH="$HOME/.npm-global/bin:$PATH"

lark-cli im +messages-send \
  --chat-id "<your-feishu-chat-id>" \
  --msg-type text \
  --text '汇报内容' \
  --as bot
```

**关键约束：**
- `--msg-type` 有效类型：text, post, image, file, audio, media, interactive, share_chat, share_user（❌ markdown 无效）
- `--text` 接受纯文本；`--content` 要求 JSON
- ✅ `--as bot` 必须加上
- ✅ 交付地址格式：`feishu:oc_xxx`

**如果今日无记忆晋升：**
- 明确写"晋升了 0 条到 MEMORY.md"
- 附带原因说明
- 仍须发送诗意梦境和备份路径

## 算法详情

算法代码位于插件 `~/.hermes/plugins/dreaming/`。

### Light Phase
- 扫描 `dreams/corpus/` 和 `dreams/daily/`
- corpus chunks 固定分数：0.58
- daily memory 行固定分数：0.62
- 使用 Jaccard 相似度去重

### REM Phase
- Candidate confidence = avgScore×0.45 + recallStrength×0.25 + consolidation×0.20 + conceptual×0.10
- 主题检测：concept tag 频率，strength ≥ 0.15

### Deep Phase
六大信号加权：

| 信号 | 权重 | 计算 |
|------|------|------|
| Frequency | 0.24 | log1p(signals)/log1p(10) |
| Relevance | 0.30 | totalScore / signalCount |
| Diversity | 0.15 | max(uniqueQueries, recallDays) / 5 |
| Recency | 0.15 | 指数衰减，半衰期 14 天 |
| Consolidation | 0.10 | 跨天间距 + 覆盖 |
| Conceptual | 0.06 | conceptTags / 6 |

晋升硬门槛：score ≥ 0.75，signals ≥ 3，diversity ≥ 2

## 常见错误

### 1. 在脚本里调用外部 LLM API
**错误：** 在 Python 脚本里用 `requests` 调 LLM API。
**正确：** AI 生成部分由 agent 会话中的 LLM 完成。脚本只输出 JSON。

### 2. 不要把技术细节放进 SKILL.md
**正确：** Skill 是执行指南。技术细节放 references/。

### 3. Cron 提示词不要重复 skill 步骤
**正确：** Cron 只写 `执行 dreaming skill 完成夜间记忆蒸馏。` Skill 是唯一真相源。

### 4. run_dreaming.py 超时
**正确：** 务必加 `timeout 180`。需要跨多日信号积累。

### 5. REM phase 噪声候选
算法可能产生系统 prompt 碎片的 false positive。Agent 在 Step 4 应自行判断。
Deep phase 的硬门槛（score≥0.75/signals≥3/diversity≥2）已能过滤大部分。

### 6. lark-cli 消息发送参数错误
参见上方 Step 7 的正确命令。

### 7. 不要在其他改动中夹带频率/行为变更
任何影响用户感知的变更必须单独告知用户并获得确认。
