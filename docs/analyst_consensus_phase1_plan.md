# Analyst Consensus — Phase 1 Consensus Data Layer 计划（v1，2026-08-28）

- 前置：Phase 0 已冻结（0B.1–0B.7 全 PASS，Overall=GO，见 `analyst_consensus_phase0b_plan.md`）
- 目标：**可信持久化** —— 把 Phase 0 验证过的解析能力（Security Resolver + Parser v1.1 + Diff/Revision）固化为可追溯、幂等、可重放的数据层
- 边界：**本阶段不计算 Consensus Score**，不做市场方向/主题热度/个股共识/操作资金流聚合
- 顺序（用户定）：`Phase 0 可信解析 → Phase 1 可信持久化 → Phase 2 市场方向/Theme Heat → Phase 3 Stock Consensus/Action Flow`
  —— 一旦 Phase 2/3 评分公式调整，底层事实事件不需重新抓取/解析，只需重新聚合

## 1. 要解决的三件事（用户 2026-08-28）

| # | 事项 | 落点 |
|---|---|---|
| 1 | **事件持久化** | `analyst_stock_events`（当日正文解析出的全部操作事件） |
| 2 | **状态快照** | `analyst_position_snapshots`（每日持仓视图，position_state=HOLDING） |
| 3 | **revision 落库** | `record_revisions`（历史不可物理覆盖） |

配套可追溯层：`source_snapshots`（输入留痕）、`ingest_runs`（批次幂等）、`analyst_profiles` / `analyst_daily_views` / `analyst_theme_mentions`（分析师/观点/主题）。

## 2. 数据流总览

```text
vip0_timeline.json（每日 22:40 归档）
  │  source_snapshots 登记（sha256 / 日期 / 原始文件）
  ▼
Security Resolver（读 security_master.db，只读）
  │  股票 → stock_code，保留 resolve_method / match_confidence
  ▼
Parser v1.1（确定性，无 LLM）
  │  ops → events[{action, action_status, temporal_type}] + position_state + buy_suppressed
  ▼
落库（幂等）
  ├─ analyst_stock_events     当日正文操作事件（含 WATCH/HOLD/SELL… 全 11 类）
  ├─ analyst_position_snapshots  position_summary 视图（HOLDING，不生成 BUY）
  ├─ analyst_daily_views       analysis-item（core_theme/trend/logic）
  ├─ analyst_theme_mentions    主题词原始提及（标准化留 Phase 2）
  ▼
Diff/Revision（vs 上一 source_snapshot）
  └─ record_revisions         ADDED/REMOVED/MODIFIED(ROLE|TEXT|SEVERE)
```

## 3. 数据库 Schema（SQLite，`data/analyst_consensus.db`）

> stock_master 仍在 `data/security_master.db`（Phase 0B.3），ingest 时只读引用，不复制。
> 所有表带 `created_at` / `updated_at`（**统一规则**：事件/快照等可审计表两者都要；
> append-only 表至少 `created_at`；DDL 统一给所有表两者，简化审计）；
> 所有"事实"行带 `first_seen_at` / `last_seen_at` / `revision_no`。
> **schema_version 用 `PRAGMA user_version = 1` 管理**（用户 2026-08-28，不单独建第 9 张表；
> 后续迁移只升 user_version，不靠猜结构）。所有枚举列加 CHECK 约束。

### 3.1 analyst_profiles —— 分析师档案
| 字段 | 类型 | 说明 |
|---|---|---|
| analyst_id | TEXT **PK** | 规范化 id（如 `laofan`） |
| analyst_name | TEXT UNIQUE | 展示名（老樊） |
| style | TEXT | LONG_TERM / SWING / SHORT / ULTRA_SHORT（Phase 0B.4 归一化） |
| time_horizon | TEXT | 时间框架描述（可空） |
| source | TEXT | 'vip0' |
| topic_id | INTEGER | 源话题 id（vip0_timeline.blogger.topic_id） |
| enabled | INTEGER | 1/0 |
| created_at / updated_at | TEXT | |

- 唯一键：`analyst_name`

### 3.2 source_snapshots —— 源快照（输入留痕）
| 字段 | 类型 | 说明 |
|---|---|---|
| snapshot_id | INTEGER **PK** | 自增 |
| source | TEXT | 'vip0' |
| snapshot_date | TEXT | '2026-08-28' |
| captured_at | TEXT | 归档时刻（UTC+8） |
| page_generated_at | TEXT | vip0_timeline.json 的 generated |
| page_sha256 | TEXT | 文件哈希 |
| raw_json_path | TEXT | 原始文件路径（analyst_snapshots/…json） |
| record_count | INTEGER | 该快照 section 数（851/1088 口径同 0B.6） |

- 唯一键：`(source, snapshot_date)`

### 3.3 analyst_daily_views —— 每日观点（analysis-item）
| 字段 | 类型 | 说明 |
|---|---|---|
| view_id | INTEGER **PK** | |
| analyst_id | TEXT FK→analyst_profiles | |
| view_date | TEXT | 分析日期 |
| view_type | TEXT | core_theme / trend / logic |
| content | TEXT | 观点原文 |
| source_snapshot_id | INTEGER FK→source_snapshots | |
| record_hash | TEXT | 内容指纹（fingerprint） |
| first_seen_at / last_seen_at | TEXT | |
| revision_no | INTEGER | 默认 1 |

- 唯一键：`(analyst_id, view_date, view_type)`

### 3.4 analyst_stock_events —— 操作事件（双轨第一轨）
> 只来源于**当日正文**的动作表达；`position_summary` 视图绝不在此生成 BUY（门禁 HOLDING→BUY=0）。
> **存全部 11 类动作**（用户 2026-08-28 拍板）——`analyst_stock_events` 是完整事件事实层，
> 不是只存成交动作的交易表。Phase 1 不提前删信息，Phase 3 再按 `event_category`/`action_type` 选择性聚合。
>
> **event_category 分层（用户 2026-08-28）**：
> - TRADE：BUY / ADD / LOW_BUY / TRIAL / REDUCE / SELL / CLEAR / STOP_LOSS
> - OBSERVATION：WATCH（**stance 必须一并持久化**：FOLLOW/AVOID/WAIT/POSITIVE/NEGATIVE）
> - STATE：HOLD（HOLD 事件 ≠ 今日买入；与 position_snapshot 的 ADD+HOLDING 并存合法）
> - COMPOSITE_TACTICAL：DO_T（避免直接产生净买卖方向）
> - UNKNOWN：action=UNKNOWN
| 字段 | 类型 | 说明 |
|---|---|---|
| event_id | INTEGER **PK** | |
| source_record_id | TEXT | 源记录身份 `vip0:{analyst}:{date}:{entity}:action:{NNN}`（0B.6 口径，role 不在身份内） |
| logical_record_id | TEXT | 逻辑记录组 `vip0:{analyst}:{date}:{entity}`（=0B.6 的 logical_key，索引见下） |
| role | TEXT | daily_action / position_summary（可 revision 字段） |
| event_index | INTEGER | 同 source_record_id 下第几个事件（多事件行） |
| analyst_id | TEXT FK | |
| event_date | TEXT | 解析后的时间（temporal 归一，TODAY→当日；PAST→事件发生日；其余→analysis_date） |
| temporal_type | TEXT | TODAY/PAST/CURRENT_STATE/FUTURE_PLAN/CONDITIONAL/UNKNOWN |
| stock_code | TEXT | 解析出的 A 股代码（UNRESOLVED 时 NULL） |
| stock_name | TEXT | 标准证券名 |
| raw_target | TEXT | 原文标的（可含歧义/非A股） |
| action_type | TEXT | 11 类动作（parser 的 action 字段映射） |
| **event_category** | TEXT | TRADE / OBSERVATION / STATE / COMPOSITE_TACTICAL / UNKNOWN（上表映射） |
| action_status | TEXT | EXECUTED/INTENDED/CONDITIONAL/POSITION_STATE/UNKNOWN |
| stance | TEXT | FOLLOW/AVOID/WAIT/POSITIVE/NEGATIVE（**WATCH 必填**，其余可空） |
| direction | TEXT | 原文方向 |
| raw_action | TEXT | 原文动作 |
| raw_logic | TEXT | 原文逻辑 |
| resolve_method | TEXT | EXACT/ALIAS/CONTEXT/FUZZY/UNRESOLVED/OUT_OF_SCOPE |
| match_confidence | REAL | 可空 |
| source_snapshot_id | INTEGER FK | |
| record_hash | TEXT | 内容指纹 |
| first_seen_at / last_seen_at | TEXT | |
| revision_no | INTEGER | |

- 唯一键（幂等锚点）：`(source_record_id, event_index)` —— 同源同序事件只落一次
- 普通索引（用户 2026-08-28，Phase 2/3 聚合频繁用）：
  - `(analyst_id, event_date)`
  - `(stock_code, event_date)`
  - `(action_type, event_date)`
  - `(logical_record_id)`
- CHECK 约束：`action` ∈ 11+UNKNOWN；`event_category` ∈ TRADE/OBSERVATION/STATE/COMPOSITE_TACTICAL/UNKNOWN；
  `action_status` ∈ 5；`temporal_type` ∈ 6；`stance` ∈ FOLLOW/AVOID/WAIT/POSITIVE/NEGATIVE；
  `resolve_method` ∈ 6；`role` ∈ daily_action/position_summary

### 3.5 analyst_position_snapshots —— 持仓快照（双轨第二轨）
> 每个分析师"最新一天 ops"即当日持仓视图（role=position_summary）。**position_state 恒为 HOLDING**，
> 不生成任何当日操作事件；同一股票可与 `analyst_stock_events` 的 TODAY+EXECUTED+LOW_BUY 同时存在（双轨合法）。
| 字段 | 类型 | 说明 |
|---|---|---|
| snapshot_id | INTEGER **PK** | |
| analyst_id | TEXT FK | |
| snapshot_date | TEXT | 该持仓视图对应的最新日 |
| stock_code | TEXT | 解析代码 |
| stock_name | TEXT | |
| raw_target | TEXT | |
| position_state | TEXT | 恒 'HOLDING' |
| raw_action | TEXT | 原文 |
| raw_logic | TEXT | 原文逻辑 |
| source_record_id | TEXT | |
| logical_record_id | TEXT | 逻辑记录组（=0B.6 logical_key） |
| resolve_method | TEXT | |
| source_snapshot_id | INTEGER FK | |
| record_hash | TEXT | |
| first_seen_at / last_seen_at | TEXT | |
| revision_no | INTEGER | |

- 唯一键：`(analyst_id, snapshot_date, source_record_id)`
- 索引：`(analyst_id, snapshot_date)`、`(stock_code, snapshot_date)`

### 3.6 analyst_theme_mentions —— 主题提及（只落原始，不计算热度）
| 字段 | 类型 | 说明 |
|---|---|---|
| mention_id | INTEGER **PK** | |
| analyst_id | TEXT FK | |
| mention_date | TEXT | |
| theme_name | TEXT | 原始主题词（如 液冷/折叠屏/CPO） |
| theme_id | TEXT | 归一化主题 id（**Phase 2 填**，本阶段 NULL） |
| mention_type | TEXT | core_theme / logic 内嵌 / ops 相关 |
| source_record_id | TEXT | |
| raw_context | TEXT | 上下文原文 |
| source_snapshot_id | INTEGER FK | |

- 唯一键：`(analyst_id, mention_date, theme_name, source_record_id)`

### 3.7 record_revisions —— Revision 落库（历史不可物理覆盖）
| 字段 | 类型 | 说明 |
|---|---|---|
| revision_id | INTEGER **PK** | |
| source_record_id | TEXT | 细粒度锚点（=analyst_stock_events.source_record_id，ADDED/REMOVED/MODIFIED 作用对象） |
| logical_record_id | TEXT | 粗粒度逻辑组（=0B.6 logical_key，跨表共用锚点） |
| table_name | TEXT | 受影响的表 |
| snapshot_date | TEXT | 检测到变化的快照日 |
| detected_at | TEXT | |
| revision_no | INTEGER | 同 logical_record_id 递增 |
| change_type | TEXT | ADDED / REMOVED / UNCHANGED / MODIFIED |
| severity | TEXT | ROLE / TEXT / SEVERE（0B.6 分级） |
| old_hash / new_hash | TEXT | |
| old_value / new_value | TEXT | JSON 快照（旧值永不删除） |
| changed_fields_json | TEXT | JSON 数组（用户 2026-08-28 命名） |
| source_snapshot_id | INTEGER FK | |
| created_at | TEXT | |

- 唯一键：`(source_record_id, snapshot_date)`
- CHECK：`change_type` ∈ 4；`severity` ∈ ROLE/TEXT/SEVERE
- 规则：事实行的 UPDATE 一律**禁止物理覆盖**——新状态作为新 revision 落 `record_revisions`，
  业务表保留最新值 + `revision_no` 指向最新 revision。

### 3.8 ingest_runs —— 摄入批次（幂等 + 可重放）
| 字段 | 类型 | 说明 |
|---|---|---|
| run_id | INTEGER **PK** | |
| source_snapshot_id | INTEGER FK | |
| parser_version | TEXT | 'v1.1' |
| resolver_version | TEXT | 'b3.3' |
| schema_version | TEXT | 'p1.1' |
| started_at / finished_at | TEXT | |
| status | TEXT | running / success / failed |
| input_records | INTEGER | 输入 section 数 |
| events_created | INTEGER | 新落事件数 |
| events_dup_skipped | INTEGER | 幂等跳过数 |
| errors | TEXT | 失败明细（JSON） |

- 唯一键：`(source_snapshot_id, parser_version, resolver_version)` —— 同版本同快照只跑一次

## 4. 事件生命周期

```text
raw op（day.ops 一行）
  → [Resolver]  resolve_method 判定（EXACT/ALIAS/…/UNRESOLVED/OOS）
  → [Parser v1.1] 事件拆分：1 行 → 1..n events，各自 action/action_status/temporal_type
  → [落库]      每事件一行 analyst_stock_events（source_record_id + event_index 锚定）
  → [双轨分流]  role=position_summary 的同一批行 → analyst_position_snapshots（HOLDING，不产 BUY）
  → [Diff]      跨 source_snapshot 对比 → record_revisions
```

- **UNRESOLVED / OUT_OF_SCOPE**：照常落库（resolve_method 标记），不进 A股可解析统计，
  但 source lineage 100% 保留（可追溯"为什么没解析"）。
- **多事件行**：`低吸持有` → [LOW_BUY, HOLD] 两个 event_index；`event_index` 保序。
- **buy_suppressed**：parser 返回的抑制标记落 `record_revisions.changed_fields` 或 event 扩展字段，
  用于审计"为何未把持仓升级成 BUY"。

## 5. 幂等规则

1. **批次级**：ingest 前查 `ingest_runs` —— 同 `(source_snapshot_id, parser_version, resolver_version)`
   已 success → 直接跳过（重放安全）。
2. **行级**：`analyst_stock_events` 唯一键 `(source_record_id, event_index)` +
   `analyst_daily_views` `(analyst_id, view_date, view_type)` + `analyst_position_snapshots`
   `(analyst_id, snapshot_date, source_record_id)` —— `INSERT … ON CONFLICT DO NOTHING`。
3. **确定性**：Parser v1.1 无随机/无 LLM；Resolver 规则确定性 → 同一输入重复运行结果字节级一致。
4. **重复 ingest 验收**：同快照连续跑 2 次 → `events_created` 第二次 = 0，`events_dup_skipped` = 全量，
   duplicate events = 0。

## 6. Revision 规则

- 来源：每日 ingest 后，以 0B.6 `diff_analyst_snapshots_v2.py` 对比上一 source_snapshot。
- 映射：
  - record 只在 before → REMOVED（理论增量数据不应出现；出现即告警）
  - 只在 after → ADDED（=当日真·新增，0B.6 实测 237 条）
  - 指纹同 + role 同 → UNCHANGED
  - 指纹同 + role 变 → MODIFIED / ROLE（0B.6 实测 99 条）
  - 指纹变（±role）→ MODIFIED / TEXT 或 SEVERE
- **历史不可物理覆盖**：任何内容变化 → 新 revision 行（保留 old_value/old_hash）；
  业务表只存最新值，`revision_no` 指向最新 revision_id。
- `revision_no` 按 logical_record_id 递增；跨表同一逻辑记录（event/持仓/观点）共用 logical_record_id 锚点。

## 7. 每日 ingest 流程

```text
① 22:40 archive_analyst_daily.py 归档 vip0_timeline_YYYYMMDD.json（已有）
② 检测新 snapshot（vs 最新 source_snapshot）
③ 登记 source_snapshot（sha256/日期/记录数）
④ 开 ingest_run（parser v1.1 + resolver b3.3）
⑤ Resolver → Parser → 幂等落 4 张事实表
⑥ 与上一 snapshot 跑 diff → record_revisions（含 role 翻转）
⑦ 幂等复跑校验（第二次 events_created=0）
⑧ 更新 ingest_run status=success（记 events_created/dup_skipped）
⑨ 验收 gate 统计 → 写 Data Layer Benchmark 报告
```

## 8. 验收 gate（用户 2026-08-28 定死，Phase 1 判 PASS 的门槛）

| # | Gate | 门槛 |
|---|---|---|
| 1 | 重复 ingest | **0 duplicate events** |
| 2 | A股可解析事件 | **100%**（A_SHARE_RESOLVABLE 内全部解析，UNRESOLVED=0） |
| 3 | false executed buy / sell | **0** |
| 4 | HOLDING → BUY | **0**（持仓快照绝不升级为已执行买入） |
| 5 | revision 可追踪 | **100%**（每次内容变化都能在 record_revisions 找到 old/new） |
| 6 | source lineage 保留 | **100%**（每事件可回溯到 source_snapshot + source_record_id + 原文） |
| 7 | 同一输入重复运行结果一致 | **100%**（确定性） |

> 参照 0B.7 成绩单格式输出 `reports/benchmark_p1_*.md`，独立 commit 记录。

## 9. 版本拆分（P1.1 ~ P1.5，每阶段独立验收）

| 阶段 | 内容 | 验收 | 独立 commit 命名 |
|---|---|---|---|
| **P1.1** | ✅ Schema DDL（8 表）+ 索引/CHECK/时间戳 + `PRAGMA user_version=1`；只建结构，不导入快照、不写 ingest（`507712b`） | ① 8 表存在 + 唯一键存在；② FK/logical 引用字段齐全；③ 所有枚举列受 CHECK；④ 重复插入唯一键失败；⑤ `PRAGMA user_version`=1；⑥ 空库可 `DROP/CREATE` 重放 — **6/6 PASS** | `feat(phase1): consensus data layer schema (8 tables)` |
| **P1.2** | Event Ingest：vip0_timeline → Resolver → Parser → `analyst_stock_events` + `analyst_daily_views` | 事件数=parser 生产数；source lineage 100%；幂等复跑 duplicate=0 | `feat(phase1): event ingest pipeline (idempotent)` |
| **P1.3** | Position 双轨落库：`analyst_position_snapshots` | HOLDING→BUY=0；同一股票 ADD+HOLDING 并存合法；每日 snapshot 形成 | `feat(phase1): dual-track position snapshots` |
| **P1.4** | Revision 持久化：ingest 后 diff → `record_revisions` | revision 可追踪 100%；历史不可物理覆盖（无 UPDATE 删除旧值） | `feat(phase1): persist revisions from cross-day diff` |
| **P1.5** | Data Layer Benchmark：全 gate 复现 + 报告 | 7 项 gate 全 PASS → Phase 1 收口 → Phase 2 市场方向/Theme Heat | `feat(phase1): data layer benchmark (7 gates)` |

## 10. 与既有组件的衔接（不重复造轮子）

- Resolver：复用 `exact_resolver_benchmark_p0b.py` 的 EXACT/ALIAS/OUT_OF_SCOPE 逻辑（读 security_master.db）
- Parser：复用 `action_temporal_parser_v11_p0b.py`（已 LOCKED，Gold 112/112）
- Diff：复用 `diff_analyst_snapshots_v2.py`（role 语义已按用户细化）
- 快照：复用 `archive_analyst_daily.py`（22:40 自动归档）
- 重建 as-of 快照：复用 `reconstruct_prev_snapshot_p0b.py`

## 11. 明确不做（Phase 1 边界）

- 不计算 Consensus Score / 不计算市场温度 / 主题热度 / 个股共识 / 操作资金流
- 不接 LLM 抽取（本阶段全部确定性规则）
- 不修改 Gold v1 FINAL / 不碰 Parser 已锁定语义
- 不改 security_master.db 的 stock_master（只读引用）

## 12. 用户已拍板的设计点（2026-08-28）

1. ✅ `analyst_stock_events` 存**全部 11 类动作**（完整事件事实层，非只存成交），
   `event_category` 分层：TRADE / OBSERVATION / STATE / COMPOSITE_TACTICAL / UNKNOWN；
   WATCH stance 必填；持仓升级 BUY 由"只从当日正文解析"杜绝（门禁 HOLDING→BUY=0）。
2. ✅ 独立 `data/analyst_consensus.db`；security_master.db 只负责证券主数据 + Resolver，
   Consensus 层只读引用、不复制 stock_master、不让业务事件反向污染主数据。
3. ✅ 唯一键 `(source_record_id, event_index)` 依赖 ops 数组顺序 —— 即 0B.6 决策 4
   （ordinal 身份）的自然延续；上游改序会产生 ADDED+REMOVED 而非 MODIFIED，与 0B.6 语义一致。
