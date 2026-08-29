# 0B.6 真实跨天 Diff 验收报告（2026-08-28）

> 输入 = 真实日终快照 08-27(as-of) vs 08-28
> 数据来源 = `vip0_timeline_20260828.json`（15 天累积增量）→
> `reconstruct_prev_snapshot_p0b.py` 过滤 ≤08-27 重建 as-of 快照
> （采集是增量累积，08-27 记录不应被 08-28 改动 —— 本验收恰好验证这一点）

## 验收结果
```
before 851 条 section → after 1088 条
ADDED 237 | REMOVED 0 | UNCHANGED 752 | MODIFIED 99
modified_breakdown: { "ROLE:role": 99 }   ← 全部为角色翻转，无内容修改
role_only_changes: 99
```

## 三块信号
1. **增量完整性 ✓**：MODIFIED 内容（非 role）= 0 → 08-28 采集未重写任何旧记录
2. **真·新增 237**：08-28 最新持仓操作 207 + 08-28 新观点 30（全部为 08-28 当日新增内容）
3. **角色翻转 99**：08-27（97 条）+ 08-26 清北游资（2 条，该博主 08-27 无数据）
   从 position_summary → daily_action —— 同一逻辑记录仅展示角色变化

## 设计落地（2026-08-28 用户拍板 方案 B + 细化）
- `section_type` 移出 `logical_key`，降级为**可 revision 的 role 字段**
- 角色翻转 = **MODIFIED(severity=ROLE)**，不判 REMOVED+ADDED
- `record_id` 保留 `:action:{NNN}` ordinal + 日期/实体（不退化）
- 角色翻转同时 action/text 实质变化 → **MODIFIED + SEVERE**（内容变化信号不丢失）
- 角色翻转 ≠ 当日新操作：role 变化不产生 Parser 事件，持仓不自动算成当日操作（双轨模型语义隔离）

## 单测（合成快照）
- 仅 role 翻转 → MODIFIED(ROLE)，changed=['role'] ✓
- role + 内容变化 → MODIFIED(SEVERE)，changed 含 role+content ✓
- 无假 REMOVED / 新日记录 → ADDED ✓

## 语义护栏（写进 0B.7 成绩单）
角色翻转不得改变 Parser 的 action/status/temporal；持仓汇总不得自动生成当日操作事件。

## 文件
- `scripts/diff_analyst_snapshots_v2.py` — role 语义升级
- `scripts/reconstruct_prev_snapshot_p0b.py` — as-of 快照重建（增量前提）
- `reports/crossday_diff_0827_0828.json` — 验收输出
