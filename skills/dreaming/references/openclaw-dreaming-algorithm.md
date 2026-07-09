# OpenClaw Dreaming 算法详解（基于源码）

> 提取自 `openclaw@2026.5.2` 的编译 JS 文件

---

## 数据模型

### Short-Term Recall Store

文件路径：`memory/.dreams/short-term-recall.json`

| 字段 | 类型 | 说明 |
|------|------|------|
| `key` | string | 唯一标识 `path:startLine:endLine` |
| `path` | string | 来源文件路径 |
| `snippet` | string | 文本内容 |
| `recallCount` | int | 被 recall 查询命中的次数 |
| `dailyCount` | int | 被 daily ingestion 收录的次数 |
| `groundedCount` | int | backfill 次数 |
| `totalScore` | float | 所有信号分数的累加和 |
| `maxScore` | float | 最高单次分数 |
| `queryHashes` | string[] | 去重查询哈希列表（最多 32 个） |
| `recallDays` | string[] | 被召回的日期列表（最多 16 天） |
| `conceptTags` | string[] | 概念标签（最多 8 个） |
| `promotedAt` | ISO | 已晋升到 MEMORY.md 的时间 |

### Phase Signal Store

文件路径：`memory/.dreams/phase-signals.json`

记录 Light 和 REM 阶段对每个 entry 的命中情况，用于 Deep 阶段的 phase boost。

---

## Light Phase 算法

### Daily Memory Ingestion

```python
DAILY_INGESTION_SCORE = 0.62
```

1. 遍历最近 7 天内的 `dreams/daily/YYYY-MM-DD.md`
2. 每份文件拆分成 chunk
3. 每个 chunk 固定分数 0.62
4. key = `daily:{文件名}:{chunk序号}`（如 `daily:2026-07-08:1`）
5. query_hash = `daily:{文件日期}`（如 `daily:2026-07-08`）
6. 调用 `record_daily_signal()` → `record_signal()`

### Session Transcript Ingestion

```python
SESSION_INGESTION_SCORE = 0.58
```

1. 遍历最近 7 天内的 `dreams/corpus/YYYY-MM-DD.txt`
2. 每个 chunk 固定分数 0.58
3. key = `session:{文件名}:{chunk序号}`（如 `session:2026-07-08:3`）
4. query_hash = `session:{文件日期}`（如 `session:2026-07-08`）
5. 调用 `record_session_signal()` → `record_signal()`

### Corpus 提取过滤

corpus 提取时（`corpus_extractor.py`）在 `_sanitize_session_text()` 中过滤：
- **fenced code blocks**（` ``` ` 包裹的内容和标记本身）→ 移除
- **image markers**（`[Image]`、`[IMAGE:`、`MEDIA:`）→ 移除
- 未闭合的代码块（有开始 ` ``` ` 无结束）→ 从 ` ``` ` 开始的内容保留

### 去重规则

```python
dedupe_signal = (
    query_hash in entry.queryHashes
    and day in entry.recallDays
)
```

同一个 query_hash（同一日期批次）在同一天（day）内重复命中同一个 key → 只算一次信号。不同天的扫描各自 +1，不同来源（corpus vs daily）各自 +1。

### Key 设计

key 包含来源文件名和 chunk 序号，不同文件的同内容不坍缩到同一个条目。同一文件在 lookback 窗口内被反复扫描时 key 不变，recallCount 跨天累加。

---

## REM Phase 算法

### Candidate Truth Confidence

```javascript
function calculateCandidateTruthConfidence(entry) {
    const recallStrength = Math.min(1, Math.log1p(entry.recallCount) / Math.log1p(6));
    const averageScore   = entry.totalScore / signalCount;
    const consolidation  = Math.min(1, entry.recallDays.length / 3);
    const conceptual     = Math.min(1, entry.conceptTags.length / 6);
    
    return Math.max(0, Math.min(1, 
        averageScore   * 0.45 + 
        recallStrength * 0.25 + 
        consolidation  * 0.20 + 
        conceptual     * 0.10
    ));
}
```

### 筛选条件

```javascript
dedupeEntries(entries, threshold=0.88)
.filter(entry => !entry.promotedAt)
.filter(entry => entry.confidence >= 0.45)
.toSorted((a, b) => b.confidence - a.confidence)
.slice(0, limit)
```

---

## Deep Phase 算法

### 硬门槛

| 门槛 | 默认值 | 说明 |
|------|--------|------|
| `minScore` | 0.75 | 综合评分必须 >= 0.75 |
| `minRecallCount` | 3 | 总信号数必须 >= 3 |
| `minUniqueQueries` | 2 | 独立查询数或召回天数 >= 2 |

### 六大信号加权评分

```javascript
const DEFAULT_PROMOTION_WEIGHTS = {
    frequency:     0.24,
    relevance:     0.30,
    diversity:     0.15,
    recency:       0.15,
    consolidation: 0.10,
    conceptual:    0.06
};
```

**晋升排序：**
```javascript
candidates.toSorted((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    if (b.recallCount !== a.recallCount) return b.recallCount - a.recallCount;
    return a.snippet.localeCompare(b.snippet);
})
.slice(0, limit)
```

---

## 关键纠正（vs 之前的错误猜测）

| 我之前说的 | 源码真相 |
|-----------|---------|
| confidence 是 AI 主观评分 | ❌ 是确定性算法加权分 |
| 用了 MemOS 向量搜索 | ❌ 完全无关，是本地 JSON store + 简单路径匹配 |
| Light/REM/Deep 都是 AI 推理 | ❌ 只有 Dream Diary 是 AI 写的，其余全是确定性算法 |
| openclaw 依赖 memos | ❌ memory-core 插件内置功能，与 memos 插件独立 |

---

## 文件路径对照

| OpenClaw | Hermes 对应 |
|----------|------------|
| `memory/YYYY-MM-DD.md` | `~/.hermes/sessions/` 数据库 |
| `.dreams/session-corpus/` | `~/.hermes/dreams/corpus/` |
| `.dreams/short-term-recall.json` | 插件内部 store |
| `.dreams/phase-signals.json` | 插件内部 store |
| `MEMORY.md` | `~/.hermes/memories/MEMORY.md` |
| `DREAMS.md` | `~/.hermes/dreams/DREAMS.md` |
