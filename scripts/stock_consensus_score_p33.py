#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stock_consensus_score_p33.py — P3.3 Stock Consensus Score / State
=================================================================
用户 2026-08-30 锁定：
  - Stock Consensus Score（每股净共识 + consensus_strength + divergence）
  - Stock Consensus State：STRONG_POSITIVE / POSITIVE / NEUTRAL / NEGATIVE / STRONG_NEGATIVE
  - 继承 Phase 2 治理哲学：固定语义归一化（禁 min-max）/ analyst cap / Missing ≠ Zero / 低证据不硬算

Score 构成（每股全期，有符号净共识）：
  consensus_raw = action_net + holding_net
    action_net = positive_weighted + negative_weighted   # 正负动作加权和（P2.2B 权重，负为负）
    holding_net = unique_holding_analysts × 0.5          # 持仓支持（软证据，半权重，Missing≠Zero 不补零）
  consensus_strength：证据分级（P3.0 分层 S1/S2/S3 → STRONG/MEDIUM/WEAK）
  divergence：正负分析师方向分歧 min(pos_a,neg_a)/max(pos_a,neg_a)（仅 ≥2 分析师可算，单分析师=0 标 LOW_SIGNAL）

State 判定（固定语义阈值，v1 锁定）：
  NO_DATA         无任何事件且无持仓
  STRONG_POSITIVE action_net >= +2.0（≥2 个 BUY 量级）且 strength ∈ {STRONG, MEDIUM}
  STRONG_NEGATIVE action_net <= -2.0 且 strength ∈ {STRONG, MEDIUM}
  POSITIVE        action_net >= +0.5
  NEGATIVE        action_net <= -0.5
  NEUTRAL         其余（含弱证据正负抵消）

输出：data/p33/stock_consensus_score.json + reports/stock_consensus_score_p33.md
用法：python3 scripts/stock_consensus_score_p33.py
"""
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "analyst_consensus.db"
OUT_JSON = ROOT / "data" / "p33" / "stock_consensus_score.json"
OUT_MD = ROOT / "reports" / "stock_consensus_score_p33.md"
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

ACTION_WEIGHT = {
    "BUY": 1.00, "ADD": 0.80, "LOW_BUY": 0.70, "TRIAL": 0.40,
    "REDUCE": -0.50, "SELL": -0.80, "CLEAR": -1.00,
    "WATCH": 0.0, "HOLD": 0.0, "UNKNOWN": 0.0,
}
POSITIVE = {"BUY", "ADD", "LOW_BUY", "TRIAL"}
NEGATIVE = {"REDUCE", "SELL", "CLEAR"}
HOLDING_BONUS = 0.5          # 每股每个 unique 持仓分析师 = +0.5（软证据半权重）
STRONG_THRESHOLD = 2.0       # STRONG 档 action_net 阈值（固定语义锚）
STATE_THRESHOLD = 0.5        # POSITIVE/NEGATIVE 最低档阈值

db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row
c = db.cursor()

events = [dict(r) for r in c.execute(
    """SELECT analyst_id, event_date, stock_code, action_type
       FROM analyst_stock_events
       WHERE event_id NOT IN (SELECT event_id FROM consensus_event_exclusions)""")]
positions = [dict(r) for r in c.execute(
    """SELECT analyst_id, snapshot_date, stock_code
       FROM analyst_position_snapshots""")]

# ---------- 每股聚合 ----------
agg = defaultdict(lambda: {
    "positive_weighted": 0.0, "negative_weighted": 0.0,
    "pos_events": 0, "neg_events": 0,
    "pos_analysts": set(), "neg_analysts": set(), "all_analysts": set(),
    "event_dates": set(), "n_events": 0,
    "holding_analysts": set(), "holding_records": 0, "holding_dates": set(),
    "watch_events": 0, "do_t_events": 0, "hold_events": 0,
})
for e in events:
    a = agg[e["stock_code"]]
    a["n_events"] += 1
    a["event_dates"].add(e["event_date"])
    a["all_analysts"].add(e["analyst_id"])
    at = e["action_type"]
    if at in POSITIVE:
        a["positive_weighted"] += ACTION_WEIGHT[at]
        a["pos_events"] += 1
        a["pos_analysts"].add(e["analyst_id"])
    elif at in NEGATIVE:
        a["negative_weighted"] += ACTION_WEIGHT[at]
        a["neg_events"] += 1
        a["neg_analysts"].add(e["analyst_id"])
    elif at == "WATCH":
        a["watch_events"] += 1
    elif at == "DO_T":
        a["do_t_events"] += 1
    elif at == "HOLD":
        a["hold_events"] += 1
for p in positions:
    a = agg[p["stock_code"]]
    a["holding_analysts"].add(p["analyst_id"])
    a["holding_records"] += 1
    a["holding_dates"].add(p["snapshot_date"])

# ---------- Score 计算 ----------
def state_for(action_net, strength):
    if strength == "NO_DATA":
        return "NO_DATA"
    if action_net >= STRONG_THRESHOLD and strength in ("STRONG", "MEDIUM"):
        return "STRONG_POSITIVE"
    if action_net <= -STRONG_THRESHOLD and strength in ("STRONG", "MEDIUM"):
        return "STRONG_NEGATIVE"
    if action_net >= STATE_THRESHOLD:
        return "POSITIVE"
    if action_net <= -STATE_THRESHOLD:
        return "NEGATIVE"
    return "NEUTRAL"

result = {}
for code, a in agg.items():
    action_net = round(a["positive_weighted"] + a["negative_weighted"], 4)
    holding_net = round(len(a["holding_analysts"]) * HOLDING_BONUS, 4)
    consensus_raw = round(action_net + holding_net, 4)

    n_analysts = len(a["all_analysts"])
    n_dates = len(a["event_dates"])
    has_holding = a["holding_records"] > 0

    # consensus_strength（P3.0 分层 S1/S2/S3 → STRONG/MEDIUM/WEAK）
    if has_holding and n_dates >= 3:
        strength = "STRONG"
    elif n_dates >= 2:
        strength = "MEDIUM"
    elif a["n_events"] == 0 and not has_holding:
        strength = "NO_DATA"
    else:
        strength = "WEAK"

    # divergence：正负分析师方向分歧（仅 ≥2 分析师可算）
    pos_a, neg_a = len(a["pos_analysts"]), len(a["neg_analysts"])
    if n_analysts >= 2 and max(pos_a, neg_a) > 0:
        divergence = round(min(pos_a, neg_a) / max(pos_a, neg_a), 4)
    else:
        divergence = 0.0

    result[code] = {
        "stock_code": code,
        "n_events": a["n_events"],
        "n_analysts": n_analysts,
        "n_dates": n_dates,
        "has_holding": has_holding,
        "n_holding_analysts": len(a["holding_analysts"]),
        "n_holding_records": a["holding_records"],
        "positive_weighted": round(a["positive_weighted"], 4),
        "negative_weighted": round(a["negative_weighted"], 4),
        "pos_events": a["pos_events"],
        "neg_events": a["neg_events"],
        "action_net": action_net,
        "holding_net": holding_net,
        "consensus_raw": consensus_raw,
        "consensus_strength": strength,
        "divergence": divergence,
        "pos_analysts": pos_a,
        "neg_analysts": neg_a,
        "watch_events": a["watch_events"],
        "do_t_events": a["do_t_events"],
        "hold_events": a["hold_events"],
        "consensus_state": state_for(action_net, strength),
    }

# 补充：无观测的 eligible 股票（P3.0 350 全池）
p30_eligible = set()
ev_stocks = {e["stock_code"] for e in events}
po_stocks = {p["stock_code"] for p in positions}
all_eligible = sorted(ev_stocks | po_stocks)
for code in all_eligible:
    if code not in result:
        result[code] = {
            "stock_code": code, "n_events": 0, "n_analysts": 0, "n_dates": 0,
            "has_holding": False, "n_holding_analysts": 0, "n_holding_records": 0,
            "positive_weighted": 0.0, "negative_weighted": 0.0,
            "action_net": 0.0, "holding_net": 0.0, "consensus_raw": 0.0,
            "consensus_strength": "NO_DATA", "divergence": 0.0,
            "pos_analysts": 0, "neg_analysts": 0, "watch_events": 0,
            "do_t_events": 0, "hold_events": 0, "consensus_state": "NO_DATA",
        }

# ---------- 汇总 ----------
from collections import Counter
state_dist = Counter(v["consensus_state"] for v in result.values())
strength_dist = Counter(v["consensus_strength"] for v in result.values())

summary = {
    "n_stocks": len(result),
    "state_distribution": dict(state_dist),
    "strength_distribution": dict(strength_dist),
    "score_definition": {
        "action_net": "positive_weighted + negative_weighted（P2.2B 动作权重）",
        "holding_net": "unique_holding_analysts × 0.5（软证据半权重）",
        "consensus_raw": "action_net + holding_net（有符号净共识）",
        "consensus_strength": "S1(双证据且事件日≥3)=STRONG / S2(事件日≥2)=MEDIUM / 其他=WEAK / 无观测=NO_DATA",
        "divergence": "min(pos_a,neg_a)/max(pos_a,neg_a)，仅 ≥2 分析师可算，否则 0（单分析师标 LOW_SIGNAL 语义）",
    },
    "state_rules": {
        "STRONG_POSITIVE": "action_net >= +2.0 且 strength ∈ {STRONG, MEDIUM}",
        "STRONG_NEGATIVE": "action_net <= -2.0 且 strength ∈ {STRONG, MEDIUM}",
        "POSITIVE": "action_net >= +0.5",
        "NEGATIVE": "action_net <= -0.5",
        "NEUTRAL": "其余（含弱证据正负抵消）",
        "NO_DATA": "无任何事件且无持仓",
    },
}

output = {
    "generated_at": "P3.3 v1",
    "summary": summary,
    "per_stock": dict(sorted(result.items())),
}
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

# ---------- 报告 ----------
def rows_by_state(st):
    return [v for v in result.values() if v["consensus_state"] == st]

top_pos = sorted([v for v in result.values() if v["consensus_state"] in ("POSITIVE", "STRONG_POSITIVE")],
                 key=lambda x: -x["consensus_raw"])[:8]
top_neg = sorted([v for v in result.values() if v["consensus_state"] in ("NEGATIVE", "STRONG_NEGATIVE")],
                 key=lambda x: x["consensus_raw"])[:8]

md = f"""# P3.3 Stock Consensus Score / State

日期：2026-08-30　数据源：data/p31 + data/p32 同源（eligible events + positions）

## Score 构成（每股，有符号净共识）
- `action_net` = positive_weighted + negative_weighted（P2.2B 动作权重，负为负）
- `holding_net` = unique_holding_analysts × 0.5（持仓软证据，半权重，Missing≠Zero 不补零）
- `consensus_raw` = action_net + holding_net
- `consensus_strength` = S1(双证据&事件日≥3)→STRONG / S2(事件日≥2)→MEDIUM / 其他→WEAK / 无观测→NO_DATA
- `divergence` = min(pos_a,neg_a)/max(pos_a,neg_a)，仅 ≥2 分析师可算，否则 0（单分析师=低置信语义）

## State 判定（固定语义阈值，v1）
| State | 条件 |
| --- | --- |
| STRONG_POSITIVE | action_net ≥ +2.0 且 strength ∈ {{STRONG, MEDIUM}} |
| STRONG_NEGATIVE | action_net ≤ −2.0 且 strength ∈ {{STRONG, MEDIUM}} |
| POSITIVE | action_net ≥ +0.5 |
| NEGATIVE | action_net ≤ −0.5 |
| NEUTRAL | 其余（含弱证据正负抵消） |
| NO_DATA | 无任何事件且无持仓 |

## 分布
- 覆盖股票：{summary["n_stocks"]}
- State 分布：{json.dumps(state_dist, ensure_ascii=False)}
- Strength 分布：{json.dumps(strength_dist, ensure_ascii=False)}

## Top 正共识（consensus_raw）
| 股票 | state | action_net | holding_net | raw | strength | divergence | 分析师(+/-) |
| --- | --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(f"| {v['stock_code']} | {v['consensus_state']} | {v['action_net']} | {v['holding_net']} | {v['consensus_raw']} | {v['consensus_strength']} | {v['divergence']} | {v['pos_analysts']}/{v['neg_analysts']} |" for v in top_pos)}

## Top 负共识（consensus_raw）
| 股票 | state | action_net | holding_net | raw | strength | divergence | 分析师(+/-) |
| --- | --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(f"| {v['stock_code']} | {v['consensus_state']} | {v['action_net']} | {v['holding_net']} | {v['consensus_raw']} | {v['consensus_strength']} | {v['divergence']} | {v['pos_analysts']}/{v['neg_analysts']} |" for v in top_neg)}
"""
with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write(md)

print(f"覆盖股票 = {summary['n_stocks']}")
print(f"State 分布 = {dict(state_dist)}")
print(f"Strength 分布 = {dict(strength_dist)}")
print(f"Top 正: " + ", ".join(f"{v['stock_code']}({v['consensus_state']},{v['consensus_raw']})" for v in top_pos[:5]))
print(f"Top 负: " + ", ".join(f"{v['stock_code']}({v['consensus_state']},{v['consensus_raw']})" for v in top_neg[:5]))
print(f"输出: {OUT_JSON}")
