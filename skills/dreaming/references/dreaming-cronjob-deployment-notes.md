# 做梦 Cron Job 部署状态与已知问题

> 来源：2026-05-11 会话 — cron job 执行时报 "Skill(s) not found and were skipped: openclaw-imports/dreaming"

---

## 当前部署状态

| 项 | 状态 | 说明 |
|---|---|---|
| 插件代码 | ✅ 正常 | `~/.hermes/plugins/dreaming/` 存在且可运行 |
| 算法执行 | ✅ 正常 | Light/REM/Deep 三阶段运行无错误 |
| 语料提取 | ✅ 正常 | 每日自动提取 corpus 到 `~/.hermes/dreams/corpus/` |
| short-term store | ✅ 积累中 | 已有 1,700+ 条候选，等待多日沉淀后晋升 |
| 日常 Daily Memory | ✅ 正常 | agent 会话中 AI 生成并落地 |
| DREAMS.md | ✅ 正常 | 每日追加诗意梦境 |
| 备份机制 | ✅ 正常 | MEMORY.md 每次修改前自动备份 |
| 飞书汇报发送 | ✅ 正常 | cron job 交付地址已修正 |

## 部署注意事项

每次 curator 合并或删除 skill 后，执行：
```bash
# 1. 检查所有 cron job 的 skill 引用
hermes cron list

# 2. 确认被删除/合并的 skill 不再被任何 cron job 引用

# 3. 检查交付地址是否带 chat_id
# 正确格式：feishu:oc_xxx 或 feishu:ou_xxx
```

## 2026-05-15 调查："做梦后定时任务死了"现象

### 根本原因分析

**不是"做梦导致任务死亡"，而是 delivery 管道卡住。**

1. 天气任务执行时间过长（10-15 分钟），产生"死了"的错觉
2. 用户 workaround（`hermes cron update`）触发 scheduler 刷新，使卡住的 delivery 队列恢复
3. 与做梦的时间关联是偶然——做梦在 23:00 执行，次日早上的天气/早安任务从 7:10 开始

### 建议
- 如果 cron job 执行正常但用户未收到消息，检查 `hermes cron list` + `~/.hermes/cron/output/<job_id>/` 下的输出文件
- 可以手动执行 `hermes cron update <job_id>` 尝试触发 delivery 刷新

---

## 关联文件

- `references/hermes-dreaming-implementation.md` — 做梦机制落地详情
- `references/dreaming-skill.md` — 做梦 skill 执行流程
