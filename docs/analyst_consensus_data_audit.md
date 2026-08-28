# Analyst Consensus Phase 0A 数据审计与契约草案

- 状态：Phase 0A 完成，Phase 1 未开始
- 审计时间：2026-08-27（UTC+8）
- 数据源：`https://reports.wmsora.vip/analysts/vip0_timeline.html`
- 原则：本阶段只审计边界与可追溯性，不计算市场温度、主题热度或个股共识。

## 1. 实测页面概况

| 指标 | 实测值 |
|---|---:|
| 页面快照大小 | 394,654 bytes |
| 页面 SHA-256 | `0e9a895c7277d7b4c7525d67cf9db7ced8c2776dd43ae4633ee8e52c52dc96d8` |
| 博主 | 10 位 |
| 日分析块 | 68 个 |
| 页面汇总个股操作 | 846 条 |
| 页面日期范围 | 2026-08-13 ~ 2026-08-27 |
| `.blogger-card` | 10 |
| `.day-entry` | 68 |
| `.analysis-item` | 183 |
| `.ops-timeline` | 71（含最新持仓表） |
| `<tr>` | 1,016 |

## 2. 已确认 HTML 边界

```text
blogger-card[id=分析师]
  ├─ card-head：分析师名、分析天数、操作记录数
  ├─ style-tip：风格说明
  ├─ latest-summary：截至日期的持仓汇总（不是当日动作）
  └─ day-entry
       ├─ day-header/date-badge：分析日期
       ├─ analysis-item[label/value]：核心主线、趋势分析、推荐逻辑
       └─ ops-timeline
            └─ tr：个股/原始逻辑/操作建议/方向/日期
```

因此，**日内 `ops-timeline` 与 `latest-summary` 必须分表保存**，不能把最新持仓当成当天买入。

## 3. Phase 0A 解析产物

脚本：`scripts/parse_analyst_timeline_p0a.py`

产物：

- `data/analyst_snapshots/vip0_timeline_YYYYMMDD_HHMMSS.html`
- `data/analyst_snapshots/p0a_parsed_records.json`
- `data/analyst_snapshots/p0a_latest_audit.json`

每条日内操作保留原始字段：

```json
{
  "source_record_id": "vip0:老樊:2026-08-27:daily_action:001",
  "analyst": "老樊",
  "analysis_date": "2026-08-27",
  "section_type": "daily_action",
  "raw_target": "联瑞新材",
  "raw_logic": "...",
  "raw_action_text": "突破买点结构，重点关注",
  "raw_direction": "买入",
  "raw_date": "2026-08-27"
}
```

`source_record_id` 是页面行号提示，不作为跨快照唯一身份；跨快照使用完整原始字段的 SHA-256 `record_hash`。

## 4. 对象分类审计

当前不猜股票名称对应代码：

| 类别 | 条数 | 说明 |
|---|---:|---|
| 直接带六位代码 | 312 | 可进入代码级后续审计，但仍要校验代码格式/市场 |
| 名称精确命中本地主表 | 22 | 当前本地 `telegram_stock_bot/stocks.db` 只有 41 条，覆盖不足 |
| 名称别名命中 | 0 | 主表暂无可用别名覆盖 |
| 非个股对象（规则识别） | 9 | 如大盘、市场、科技线等 |
| 未解析 | 503 | 主要是股票简称/公司名，禁止直接算入个股共识 |

结论：当前股票名称解析基础不足，**Phase 0 不能 Go**。下一阶段必须接入同花顺 `meta/tickers/search` 或完整 `stock_master`，并保留 `match_method`、`match_confidence`。

## 5. 快照与增量契约

脚本：`scripts/diff_analyst_snapshots_p0a.py`

跨快照比较规则：

```text
record_hash = SHA256(
  analyst + analysis_date + raw_target + raw_logic
  + raw_action_text + raw_direction + raw_date
)
```

当前两次同日快照实测：

```text
before_actions=846
after_actions=846
added=0
removed=0
unchanged=846
```

后续数据库至少保留：

- `snapshot_id`
- `captured_at`
- `page_generated_at`
- `page_sha256`
- `record_hash`
- `first_seen_at`
- `last_seen_at`
- `revision_no`
- `raw_payload`

页面后续修改同一日期记录时，应新增 revision，不应静默覆盖旧版本。

## 6. 暂不进入计算的字段

Phase 0A 只保存原文，不做标准化：

- `raw_action_text` 不转换成 BUY/HOLD/SELL
- `raw_direction` 不等同于已执行动作
- `raw_target` 不等同于 STOCK
- `latest-summary` 不等同于当天操作
- `analysis-item` 只作为观点原文，不转市场方向分

## 7. Go / No-Go（Phase 0A）

### 当前结论：NO-GO 进入 Phase 1

原因：

1. 846 条记录中只有 312 条有直接代码；名称解析主表仅 41 条，无法达到代码匹配门槛。
2. 当前页面没有稳定的消息 ID；必须先运行多日快照，验证 revision/diff。
3. 页面同时包含“当前持仓汇总”和“日内操作表”，虽然边界已明确，但尚未完成分离后的人工 Gold Sample。
4. 操作语义、时间语义、主题语义尚未审计，不允许先计算热度或共识。

### 进入 Phase 0B 的前置条件

- 连续至少 3 次快照成功保存
- 快照 diff 能识别新增/删除/修改记录
- 建立 100 条 Gold Sample
- 引入完整股票主表/同花顺标的检索
- 对名称解析、对象类型、操作/持仓边界进行人工标注

## 8. 已生成代码

- `scripts/audit_analyst_timeline_p0a.py`：页面总览审计与快照
- `scripts/parse_analyst_timeline_p0a.py`：HTML 边界解析
- `scripts/audit_name_code_p0a.py`：不猜测的名称→代码覆盖审计
- `scripts/diff_analyst_snapshots_p0a.py`：快照记录差异比较
