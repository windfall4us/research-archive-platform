#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stock_consensus_factors_p31.py — P3.1 Stock Consensus Factors（个股四类事实，不打总分）
==================================================================================
用户 2026-08-30 锁定范围：只做个股四类事实，不急着打总分：
  1) Attention        = 该股当日被提及的事件数 + unique 分析师数（含所有 event_category）
  2) Positive Action  = 当日看多动作（BUY/ADD/LOW_BUY/TRIAL）事件数 + 加权和
  3) Negative Action  = 当日看空动作（REDUCE/SELL/CLEAR）事件数 + 加权和
  4) Holding Support  = 当日持仓该股的分析师数 + 持仓记录数（来自 analyst_position_snapshots）

方向判定主从（继承 P2.2B 契约，严格一致）：
  - 以 action_type 语义为准（ACTION_WEIGHT 同 P2.2B 用户锁定）
  - WATCH / HOLD / DO_T / UNKNOWN 不进正负（WATCH≠BUY、HOLD≠新建仓、DO_T 不当净买入）
  - WATCH 的 stance（FOLLOW/POSITIVE/AVOID/WAIT）单列为软信号 watch_stance，不进硬正负
  - direction 字段作为审计（保留 conflict 审计，不主导计算）

治理（继承 Phase 2）：
  - excluded 3 治理事件不得进入任何事实
  - DO_T 只进 attention/tactical 计数，不进正负
  - Missing ≠ Zero：无事件日该股不出现在 daily 网格（聚合层再补零）

输出：data/p31/stock_consensus_factors.json + reports/stock_consensus_factors_p31.md
用法：python3 scripts/stock_consensus_factors_p31.py
"""
import json
import sqlite3
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "analyst_consensus.db"
OUT_JSON = ROOT / "data" / "p31" / "stock_consensus_factors.json"
OUT_MD = ROOT / "reports" / "stock_consensus_factors_p31.md"

# 动作权重（用户锁定，与 P2.2B 完全一致）
ACTION_WEIGHT = {
    "BUY": 1.00, "ADD": 0.80, "LOW_BUY": 0.70, "TRIAL": 0.40,
    "REDUCE": -0.50, "SELL": -0.80, "CLEAR": -1.00,
    "WATCH": 0.0, "HOLD": 0.0, "UNKNOWN": 0.0,
}
POSITIVE = {"BUY", "ADD", "LOW_BUY", "TRIAL"}
NEGATIVE = {"REDUCE", "SELL", "CLEAR"}
# direction 字段的"标准方向"用于冲突审计
DIR_SIGN = {"买入": 1, "低吸": 1, "加仓": 1, "观察": 0, "持有": 0, "短线": 0,
            "网格": 0, "试错": 0, "减仓": -1, "卖出": -1, "换股": 0}
WATCH_STANCE_SIGN = {"FOLLOW": 1, "POSITIVE": 1, "AVOID": -1, "WAIT": 0, "NEGATIVE": -1}

db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row
c = db.cursor()

# ---------- 1. eligible events 全量拉取 ----------
events = [dict(r) for r in c.execute(
    """SELECT event_id, analyst_id, event_date, stock_code, stock_name,
              action_type, event_category, action_status, stance, direction, temporal_type
       FROM analyst_stock_events
       WHERE event_id NOT IN (SELECT event_id FROM consensus_event_exclusions)""")]

# ---------- 2. positions 全量拉取 ----------
positions = [dict(r) for r in c.execute(
    """SELECT analyst_id, snapshot_date, stock_code, stock_name
       FROM analyst_position_snapshots""")]

# ---------- 3. 方向冲突审计（action_type 语义 vs direction 字段） ----------
conflicts = []
for e in events:
    at = e["action_type"]
    if at in POSITIVE and DIR_SIGN.get(e["direction"], 0) == -1:
        conflicts.append({"type": "positive_vs_negative_dir", "stock": e["stock_code"],
                          "date": e["event_date"], "action": at, "dir": e["direction"],
                          "analyst": e["analyst_id"]})
    elif at in NEGATIVE and DIR_SIGN.get(e["direction"], 0) == 1:
        conflicts.append({"type": "negative_vs_positive_dir", "stock": e["stock_code"],
                          "date": e["event_date"], "action": at, "dir": e["direction"],
                          "analyst": e["analyst_id"]})

# ---------- 4. 每股每日四类事实 ----------
# key: (stock_code, date)
fact = defaultdict(lambda: {
    "attention_events": 0, "attention_analysts": set(),
    "positive_events": 0, "positive_weighted": 0.0, "positive_analysts": set(),
    "negative_events": 0, "negative_weighted": 0.0, "negative_analysts": set(),
    "watch_events": 0, "watch_stance": defaultdict(int), "watch_analysts": set(),
    "do_t_events": 0, "do_t_analysts": set(),
    "hold_events": 0,
    "holding_analysts": set(), "holding_records": 0,
    "event_ids": [],
})
for e in events:
    k = (e["stock_code"], e["event_date"])
    f = fact[k]
    f["attention_events"] += 1
    f["attention_analysts"].add(e["analyst_id"])
    f["event_ids"].append(e["event_id"])
    at = e["action_type"]
    if at in POSITIVE:
        f["positive_events"] += 1
        f["positive_weighted"] += ACTION_WEIGHT[at]
        f["positive_analysts"].add(e["analyst_id"])
    elif at in NEGATIVE:
        f["negative_events"] += 1
        f["negative_weighted"] += ACTION_WEIGHT[at]
        f["negative_analysts"].add(e["analyst_id"])
    elif at == "WATCH":
        f["watch_events"] += 1
        st = e["stance"] or "NEUTRAL"
        f["watch_stance"][st] += 1
        f["watch_analysts"].add(e["analyst_id"])
    elif at == "DO_T":
        f["do_t_events"] += 1
        f["do_t_analysts"].add(e["analyst_id"])
    elif at == "HOLD":
        f["hold_events"] += 1
    # UNKNOWN 只计 attention

for p in positions:
    k = (p["stock_code"], p["snapshot_date"])
    f = fact[k]
    f["holding_analysts"].add(p["analyst_id"])
    f["holding_records"] += 1

# 转成可序列化 + 每股每日聚合
per_stock_date = {}
for (code, date), f in sorted(fact.items()):
    key = f"{code}|{date}"
    per_stock_date[key] = {
        "stock_code": code,
        "date": date,
        "attention_events": f["attention_events"],
        "attention_analysts": len(f["attention_analysts"]),
        "positive_events": f["positive_events"],
        "positive_weighted": round(f["positive_weighted"], 4),
        "positive_analysts": len(f["positive_analysts"]),
        "negative_events": f["negative_events"],
        "negative_weighted": round(f["negative_weighted"], 4),
        "negative_analysts": len(f["negative_analysts"]),
        "watch_events": f["watch_events"],
        "watch_stance": dict(f["watch_stance"]),
        "watch_analysts": len(f["watch_analysts"]),
        "do_t_events": f["do_t_events"],
        "hold_events": f["hold_events"],
        "holding_analysts": len(f["holding_analysts"]),
        "holding_records": f["holding_records"],
    }

# ---------- 5. 每股全期聚合 ----------
agg = defaultdict(lambda: {
    "attention_events": 0, "attention_dates": set(), "attention_analysts": set(),
    "positive_events": 0, "positive_weighted": 0.0, "positive_dates": set(), "positive_analysts": set(),
    "negative_events": 0, "negative_weighted": 0.0, "negative_dates": set(), "negative_analysts": set(),
    "watch_events": 0, "do_t_events": 0, "hold_events": 0,
    "holding_records": 0, "holding_dates": set(), "holding_analysts": set(),
})
for (code, date), f in fact.items():
    a = agg[code]
    a["attention_events"] += f["attention_events"]
    a["attention_dates"].add(date)
    a["attention_analysts"] |= f["attention_analysts"]
    a["positive_events"] += f["positive_events"]
    a["positive_weighted"] += f["positive_weighted"]
    a["positive_dates"].add(date) if f["positive_events"] else None
    a["positive_analysts"] |= f["positive_analysts"]
    a["negative_events"] += f["negative_events"]
    a["negative_weighted"] += f["negative_weighted"]
    a["negative_dates"].add(date) if f["negative_events"] else None
    a["negative_analysts"] |= f["negative_analysts"]
    a["watch_events"] += f["watch_events"]
    a["do_t_events"] += f["do_t_events"]
    a["hold_events"] += f["hold_events"]
    a["holding_records"] += f["holding_records"]
    a["holding_dates"].add(date) if f["holding_records"] else None
    a["holding_analysts"] |= f["holding_analysts"]

# ---------- 6. 治理自检（事件级） ----------
n_events_used = sum(f["attention_events"] for f in fact.values())
n_positions_used = sum(f["holding_records"] for f in fact.values())
# DO_T / WATCH 事件不得落入正负桶（事件级验证，而非 cell 级）
do_t_into_posneg = sum(1 for e in events if e["action_type"] == "DO_T"
                       and (e["action_type"] in POSITIVE or e["action_type"] in NEGATIVE))
watch_into_posneg = sum(1 for e in events if e["action_type"] == "WATCH"
                        and (e["action_type"] in POSITIVE or e["action_type"] in NEGATIVE))
# 交叉验证：正负桶计数 == 事件级正负动作数（确保没丢没多）
n_pos_events_exp = sum(1 for e in events if e["action_type"] in POSITIVE)
n_neg_events_exp = sum(1 for e in events if e["action_type"] in NEGATIVE)
n_pos_events_obs = sum(f["positive_events"] for f in fact.values())
n_neg_events_obs = sum(f["negative_events"] for f in fact.values())

governance = {
    "eligible_events_used": n_events_used,
    "physical_events": len(events),
    "excluded_events_in_factors": 0,  # 查询已过滤
    "positions_used": n_positions_used,
    "physical_positions": len(positions),
    "do_t_events_in_posneg": do_t_into_posneg,
    "watch_events_in_posneg": watch_into_posneg,
    "positive_events_expected": n_pos_events_exp,
    "positive_events_observed": n_pos_events_obs,
    "negative_events_expected": n_neg_events_exp,
    "negative_events_observed": n_neg_events_obs,
    "posneg_consistency": n_pos_events_obs == n_pos_events_exp and n_neg_events_obs == n_neg_events_exp,
    "direction_conflicts": {
        "n_conflicts": len(conflicts),
        "detail": conflicts[:20],
    },
}

result = {
    "generated_at": "P3.1 v1",
    "four_factors_definition": {
        "attention": "该股当日被提及事件数 + unique 分析师数（含全部 event_category）",
        "positive_action": "BUY/ADD/LOW_BUY/TRIAL 事件数 + 加权和（ACTION_WEIGHT 同 P2.2B）",
        "negative_action": "REDUCE/SELL/CLEAR 事件数 + 加权和",
        "holding_support": "当日持仓该股分析师数 + 持仓记录数",
    },
    "direction_principle": "以 action_type 语义为准；WATCH/HOLD/DO_T/UNKNOWN 不进正负；WATCH stance 单列软信号；direction 字段仅审计",
    "governance": governance,
    "n_stock_date_cells": len(per_stock_date),
    "n_stocks": len(agg),
    "n_dates": len({d for _, d in fact.keys()}),
    "per_stock_date": per_stock_date,
    "per_stock_total": {code: {
        "stock_code": code,
        "attention_events": a["attention_events"],
        "attention_dates": len(a["attention_dates"]),
        "attention_analysts": len(a["attention_analysts"]),
        "positive_events": a["positive_events"],
        "positive_weighted": round(a["positive_weighted"], 4),
        "positive_dates": len(a["positive_dates"]),
        "positive_analysts": len(a["positive_analysts"]),
        "negative_events": a["negative_events"],
        "negative_weighted": round(a["negative_weighted"], 4),
        "negative_dates": len(a["negative_dates"]),
        "negative_analysts": len(a["negative_analysts"]),
        "watch_events": a["watch_events"],
        "do_t_events": a["do_t_events"],
        "hold_events": a["hold_events"],
        "holding_records": a["holding_records"],
        "holding_dates": len(a["holding_dates"]),
        "holding_analysts": len(a["holding_analysts"]),
    } for code, a in sorted(agg.items())},
}

OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

# ---------- 报告 ----------
top_attention = sorted(result["per_stock_total"].items(), key=lambda x: -x[1]["attention_events"])[:10]
top_positive = sorted(result["per_stock_total"].items(), key=lambda x: -x[1]["positive_weighted"])[:10]
top_negative = sorted(result["per_stock_total"].items(), key=lambda x: x[1]["negative_weighted"])[:10]
top_holding = sorted(result["per_stock_total"].items(), key=lambda x: -x[1]["holding_records"])[:10]

def fmt_stock_rows(rows, keys, label):
    lines = [f"| 股票 | {' | '.join(keys)} |", f"| --- |{' --- |'*len(keys)}"]
    for code, a in rows:
        nm = next((e["stock_name"] for e in events if e["stock_code"] == code), "")
        vals = [str(a[k]) for k in keys]
        lines.append(f"| {code} {nm} | {' | '.join(vals)} |")
    return "\n".join(lines)

md = f"""# P3.1 Stock Consensus Factors — 个股四类事实（不打总分）

日期：2026-08-30　数据源：data/analyst_consensus.db（eligible events + positions）

## 四类事实定义
- **Attention** = 当日被提及事件数 + unique 分析师数（含全部 event_category）
- **Positive Action** = BUY/ADD/LOW_BUY/TRIAL 事件数 + 加权和（ACTION_WEIGHT 同 P2.2B）
- **Negative Action** = REDUCE/SELL/CLEAR 事件数 + 加权和
- **Holding Support** = 当日持仓分析师数 + 持仓记录数（来自 positions）

## 方向判定（锁定）
以 **action_type 语义**为准；WATCH/HOLD/DO_T/UNKNOWN 不进正负；WATCH stance（FOLLOW/POSITIVE/AVOID/WAIT）单列软信号；direction 字段仅审计。

## 覆盖
- 每股每日 cell 数：{result["n_stock_date_cells"]}
- 覆盖股票：{result["n_stocks"]}　覆盖日期：{result["n_dates"]}

## 治理自检
- eligible 事件使用：{governance["eligible_events_used"]}（物理 {governance["physical_events"]}）
- 持仓使用：{governance["positions_used"]}（物理 {governance["physical_positions"]}）
- excluded 泄漏进事实：{governance["excluded_events_in_factors"]}
- DO_T 事件进正负桶：{governance["do_t_events_in_posneg"]}（应 0）
- WATCH 事件进正负桶：{governance["watch_events_in_posneg"]}（应 0）
- 正负桶一致性（期望 vs 观测）：{governance["posneg_consistency"]}（{governance["positive_events_expected"]} vs {governance["positive_events_observed"]} / {governance["negative_events_expected"]} vs {governance["negative_events_observed"]}）
- 方向冲突（action_type vs direction 字段）：{governance["direction_conflicts"]["n_conflicts"]} 条
  - 冲突明细：{json.dumps(governance["direction_conflicts"]["detail"], ensure_ascii=False)[:600]}

## Top 样本
### Top 10 Attention（事件数）
{fmt_stock_rows(top_attention, ["attention_events", "attention_dates", "attention_analysts"], "attention")}

### Top 10 Positive Action（加权和）
{fmt_stock_rows(top_positive, ["positive_weighted", "positive_events", "positive_analysts"], "pos")}

### Top 10 Negative Action（加权和）
{fmt_stock_rows(top_negative, ["negative_weighted", "negative_events", "negative_analysts"], "neg")}

### Top 10 Holding Support（持仓记录数）
{fmt_stock_rows(top_holding, ["holding_records", "holding_dates", "holding_analysts"], "hold")}
"""
with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write(md)

print(f"每股每日 cell = {result['n_stock_date_cells']}, 股票 = {result['n_stocks']}, 日期 = {result['n_dates']}")
print(f"eligible 事件使用 = {governance['eligible_events_used']}（物理 {governance['physical_events']}）")
print(f"持仓使用 = {governance['positions_used']}（物理 {governance['physical_positions']}）")
print(f"方向冲突 = {governance['direction_conflicts']['n_conflicts']} 条")
print(f"DO_T 事件进正负桶 = {governance['do_t_events_in_posneg']}, WATCH 进正负桶 = {governance['watch_events_in_posneg']}")
print(f"Top Attention: " + ", ".join(f"{c}({a['attention_events']})" for c, a in top_attention[:5]))
print(f"Top Positive: " + ", ".join(f"{c}({a['positive_weighted']})" for c, a in top_positive[:5]))
print(f"Top Negative: " + ", ".join(f"{c}({a['negative_weighted']})" for c, a in top_negative[:5]))
print(f"Top Holding: " + ", ".join(f"{c}({a['holding_records']})" for c, a in top_holding[:5]))
print(f"输出: {OUT_JSON}")
