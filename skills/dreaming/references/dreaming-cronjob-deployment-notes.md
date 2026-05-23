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

---

## 关联文件

- `references/hermes-dreaming-implementation.md` — 做梦机制落地详情
- `references/dreaming-skill.md` — 做梦 skill 执行流程
