#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P3.0 Stock Consensus Readiness — 数据盘点

回答 Phase 3 的第一个问题：
  934 eligible stock events + 124 positions 实际覆盖多少只股票、
  多少位分析师、多少个交易日，以及 positions 对 events 股票的覆盖关系。
  该结果决定 Stock Consensus 的分母定义。

口径（继承 Phase 2）：
  - eligible events = 物理表 analyst_stock_events 排除 consensus_event_exclusions 中 3 条治理事件 = 934
  - positions 全量 = analyst_position_snapshots 124（无 exclusion 机制）
  - analyst_weight = 1.0

输出：data/p30/stock_consensus_readiness.json（只读盘点，不改 DB）
"""
import json
import sqlite3
import os
from collections import Counter, defaultdict

DB = os.path.join(os.path.dirname(__file__), "..", "data", "analyst_consensus.db")
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "p30", "stock_consensus_readiness.json")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row
c = db.cursor()

# ---------- 1. 原始行数与 eligible ----------
physical_events = c.execute("SELECT COUNT(*) FROM analyst_stock_events").fetchone()[0]
excluded_ids = [r["event_id"] for r in c.execute(
    "SELECT event_id FROM consensus_event_exclusions")]
n_excluded = len(excluded_ids)
eligible_events = physical_events - n_excluded

# ---------- 2. eligible events 全量拉取 ----------
events = [dict(r) for r in c.execute(
    """SELECT event_id, analyst_id, event_date, stock_code, stock_name,
              action_type, event_category, action_status, stance, direction, temporal_type
       FROM analyst_stock_events
       WHERE event_id NOT IN (SELECT event_id FROM consensus_event_exclusions)""")]

# ---------- 3. positions 全量拉取 ----------
positions = [dict(r) for r in c.execute(
    """SELECT snapshot_id, analyst_id, snapshot_date, stock_code, stock_name, position_state
       FROM analyst_position_snapshots""")]

# ---------- 4. 股票级 / 分析师级 / 日期级 覆盖 ----------
def stock_set(rows, code_key="stock_code"):
    return sorted({r[code_key] for r in rows if r[code_key]})

ev_stocks = stock_set(events)
po_stocks = stock_set(positions)
ev_analysts = sorted({r["analyst_id"] for r in events})
po_analysts = sorted({r["analyst_id"] for r in positions})
ev_dates = sorted({r["event_date"] for r in events})
po_dates = sorted({r["snapshot_date"] for r in positions})

all_stocks = sorted(set(ev_stocks) | set(po_stocks))

# ---------- 5. 每股聚合 ----------
ev_by_stock = defaultdict(list)
for e in events:
    ev_by_stock[e["stock_code"]].append(e)
po_by_stock = defaultdict(list)
for p in positions:
    po_by_stock[p["stock_code"]].append(p)

# 每股: 事件数 / 分析师数 / 覆盖日期数 / 持仓数
per_stock = {}
for code in all_stocks:
    evs = ev_by_stock.get(code, [])
    pos = po_by_stock.get(code, [])
    ev_dates_set = sorted({e["event_date"] for e in evs})
    po_dates_set = sorted({p["snapshot_date"] for p in pos})
    per_stock[code] = {
        "stock_name": (evs[0]["stock_name"] if evs else pos[0]["stock_name"]),
        "n_events": len(evs),
        "n_analysts": len({e["analyst_id"] for e in evs}),
        "n_event_dates": len(ev_dates_set),
        "event_dates": ev_dates_set,
        "n_positions": len(pos),
        "n_position_dates": len(po_dates_set),
        "position_dates": po_dates_set,
        "n_position_analysts": len({p["analyst_id"] for p in pos}),
    }

# ---------- 6. 分布统计 ----------
n_events_dist = Counter(s["n_events"] for s in per_stock.values())
n_analysts_dist = Counter(s["n_analysts"] for s in per_stock.values())
n_dates_dist = Counter(s["n_event_dates"] for s in per_stock.values())

# 覆盖关系
both = sorted({c for c in all_stocks if ev_by_stock.get(c) and po_by_stock.get(c)})
events_only = sorted(set(ev_stocks) - set(po_stocks))
positions_only = sorted(set(po_stocks) - set(ev_stocks))

# ---------- 7. 日期连续性（事件视角：连续天数 / 间断） ----------
def continuity(dates):
    if not dates:
        return {"span_days": 0, "consecutive_max": 0, "gaps": 0}
    from datetime import date as _d, datetime as _dt
    ds = sorted({_dt.strptime(d, "%Y-%m-%d").date() for d in dates})
    max_run = 1
    cur = 1
    gaps = 0
    for a, b in zip(ds, ds[1:]):
        diff = (b - a).days
        if diff == 1:
            cur += 1
            max_run = max(max_run, cur)
        else:
            gaps += 1
            cur = 1
    return {
        "span_days": (ds[-1] - ds[0]).days + 1,
        "consecutive_max": max_run,
        "gaps": gaps,
        "first_date": str(ds[0]),
        "last_date": str(ds[-1]),
    }

cont_by_stock = {code: continuity(s["event_dates"]) for code, s in per_stock.items()}

# ---------- 8. action_type 词表分布（P3.2 预备） ----------
action_dist = Counter(e["action_type"] for e in events)
action_by_stock = Counter(e["action_type"] for e in events)

# ---------- 9. 候选分母定义建议 ----------
# 候选 A: 至少 1 事件 或 1 持仓（全候选）
denom_a = len(all_stocks)
# 候选 B: 至少 1 事件（事件池）
denom_b = len(ev_stocks)
# 候选 C: 至少 2 个事件观测日（有"连续性"可追踪）
denom_c = sum(1 for s in per_stock.values() if s["n_event_dates"] >= 2)
# 候选 D: 既有事件又有持仓（双证据）
denom_d = len(both)

result = {
    "generated_at": "P3.0 v1",
    "data_source": "data/analyst_consensus.db (只读盘点)",
    "events": {
        "physical": physical_events,
        "excluded": n_excluded,
        "excluded_ids": excluded_ids,
        "eligible": eligible_events,
        "n_stocks": len(ev_stocks),
        "n_analysts": len(ev_analysts),
        "analyst_ids": ev_analysts,
        "n_dates": len(ev_dates),
        "dates": ev_dates,
    },
    "positions": {
        "total": len(positions),
        "n_stocks": len(po_stocks),
        "n_analysts": len(po_analysts),
        "analyst_ids": po_analysts,
        "n_dates": len(po_dates),
        "dates": po_dates,
    },
    "coverage": {
        "all_stocks": all_stocks,
        "both_events_and_positions": both,
        "events_only": events_only,
        "positions_only": positions_only,
        "n_both": len(both),
        "n_events_only": len(events_only),
        "n_positions_only": len(positions_only),
    },
    "distributions": {
        "events_per_stock": dict(sorted(n_events_dist.items())),
        "analysts_per_stock": dict(sorted(n_analysts_dist.items())),
        "event_dates_per_stock": dict(sorted(n_dates_dist.items())),
    },
    "continuity": cont_by_stock,
    "action_distribution": dict(action_dist.most_common()),
    "denominator_options": {
        "A_all_events_or_positions": denom_a,
        "B_events_only": denom_b,
        "C_events_ge2_dates": denom_c,
        "D_both_events_and_positions": denom_d,
    },
    "per_stock": per_stock,
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2, default=str)

# ---------- 打印人类可读摘要 ----------
print(f"物理事件={physical_events}  排除={n_excluded}  eligible={eligible_events}")
print(f"事件覆盖: 股票={len(ev_stocks)} 分析师={len(ev_analysts)} 日期={len(ev_dates)} ({ev_dates[0]}~{ev_dates[-1]})")
print(f"持仓覆盖: 总={len(positions)} 股票={len(po_stocks)} 分析师={len(po_analysts)} 日期={len(po_dates)} ({po_dates[0]}~{po_dates[-1]})")
print(f"覆盖关系: 双有={len(both)}  仅事件={len(events_only)}  仅持仓={len(positions_only)}  并集={len(all_stocks)}")
print(f"每股事件数分布: {dict(sorted(n_events_dist.items()))}")
print(f"每股分析师数分布: {dict(sorted(n_analysts_dist.items()))}")
print(f"每股事件日期数分布: {dict(sorted(n_dates_dist.items()))}")
print(f"action_type 分布: {dict(action_dist.most_common())}")
print(f"分母候选: A(事件或持仓)={denom_a}  B(仅事件)={denom_b}  C(≥2事件日)={denom_c}  D(双证据)={denom_d}")
# 日期连续性概览
runs = Counter()
for code, ct in cont_by_stock.items():
    runs[ct["consecutive_max"] if ct["span_days"] else 0] += 1
print(f"最长连续事件日分布(按股票): {dict(sorted(runs.items(), key=lambda x: -x[0]))}")
print(f"输出: {OUT}")
