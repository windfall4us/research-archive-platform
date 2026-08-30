#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyst_action_flow_p32.py — P3.2 Analyst Action Flow（分析师动作流）
====================================================================
用户 2026-08-30 锁定词表与契约：
  动作词表：BUY / ADD / LOW_BUY / TRIAL / REDUCE / SELL / CLEAR / DO_T / WATCH / HOLD
  语义契约（必须保持）：
    - DO_T 不当净买入（只算 tactical 活动，不进 BUY/ADD/LOW_BUY/TRIAL 净买入集合）
    - WATCH 不等于 BUY（WATCH 是关注/观察，单独 stage=SCAN，不进建仓）
    - HOLD 不等于新建仓（HOLD 是持仓状态，不是买入动作）

输出（每股 × 每分析师的动作序列 = 一条 flow）：
  data/p32/analyst_action_flow.json
    per_analyst_stock_flow: { "analyst|stock": [ {date, action_type, stage, status, temporal, dir, event_id, category}, ...按时间序 ] }
    stage_map: WATCH→SCAN / BUY·LOW_BUY·TRIAL→ENTRY / ADD→ACCUMULATE / HOLD→HOLD
               REDUCE→REDUCE / SELL·CLEAR→EXIT / DO_T→TACTICAL / UNKNOWN→UNKNOWN
    flow_summary: pairs_by_action / flow_length_dist / stage_transition / net_buy 统计
    governance: DO_T 隔离 / WATCH 隔离 / HOLD 隔离 / net_buy 一致性

用法：python3 scripts/analyst_action_flow_p32.py
"""
import json
import sqlite3
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "analyst_consensus.db"
OUT_JSON = ROOT / "data" / "p32" / "analyst_action_flow.json"
OUT_MD = ROOT / "reports" / "analyst_action_flow_p32.md"
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

# 动作词表（用户锁定）与 stage 映射
ACTION_WEIGHT = {
    "BUY": 1.00, "ADD": 0.80, "LOW_BUY": 0.70, "TRIAL": 0.40,
    "REDUCE": -0.50, "SELL": -0.80, "CLEAR": -1.00,
    "WATCH": 0.0, "HOLD": 0.0, "UNKNOWN": 0.0,
}
NET_BUY_ACTIONS = {"BUY", "ADD", "LOW_BUY", "TRIAL"}
NET_SELL_ACTIONS = {"REDUCE", "SELL", "CLEAR"}
STAGE_MAP = {
    "WATCH": "SCAN", "BUY": "ENTRY", "LOW_BUY": "ENTRY", "TRIAL": "ENTRY",
    "ADD": "ACCUMULATE", "HOLD": "HOLD", "REDUCE": "REDUCE",
    "SELL": "EXIT", "CLEAR": "EXIT", "DO_T": "TACTICAL", "UNKNOWN": "UNKNOWN",
}
# 动作流生命周期顺序（用于 stage 转移分析）
STAGE_ORDER = ["SCAN", "ENTRY", "ACCUMULATE", "HOLD", "REDUCE", "EXIT", "TACTICAL", "UNKNOWN"]

db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row
c = db.cursor()

events = [dict(r) for r in c.execute(
    """SELECT event_id, analyst_id, event_date, stock_code, stock_name,
              action_type, event_category, action_status, stance, direction, temporal_type
       FROM analyst_stock_events
       WHERE event_id NOT IN (SELECT event_id FROM consensus_event_exclusions)""")]

# ---------- 1. 每股 × 每分析师动作序列 ----------
flow = defaultdict(list)
for e in events:
    key = (e["analyst_id"], e["stock_code"])
    flow[key].append({
        "date": e["event_date"],
        "action_type": e["action_type"],
        "stage": STAGE_MAP.get(e["action_type"], "UNKNOWN"),
        "status": e["action_status"],
        "temporal": e["temporal_type"],
        "dir": e["direction"],
        "category": e["event_category"],
        "event_id": e["event_id"],
    })
# 按 (date, event_id) 排序成时间序列
for key in flow:
    flow[key].sort(key=lambda x: (x["date"], x["event_id"]))

# ---------- 2. 动作流统计 ----------
pairs_by_action = Counter()          # (analyst,stock) 对里出现过的 action_type
flow_length_dist = Counter(len(v) for v in flow.values())
stage_transitions = Counter()        # 相邻事件 stage 转移
net_buy_events = 0
net_buy_weighted = 0.0
do_t_pairs = []
for key, seq in flow.items():
    seen = set()
    prev_stage = None
    for ev in seq:
        at = ev["action_type"]
        pairs_by_action[at] += 1 if at not in seen else 0
        seen.add(at)
        st = ev["stage"]
        if at in NET_BUY_ACTIONS:
            net_buy_events += 1
            net_buy_weighted += ACTION_WEIGHT[at]
        if at == "DO_T":
            do_t_pairs.append(key)
        if prev_stage is not None:
            stage_transitions[(prev_stage, st)] += 1
        prev_stage = st

# ---------- 3. 治理验证 ----------
# DO_T 事件不得是 NET_BUY_ACTIONS
do_t_in_netbuy = sum(1 for e in events if e["action_type"] == "DO_T" and e["action_type"] in NET_BUY_ACTIONS)
watch_in_netbuy = sum(1 for e in events if e["action_type"] == "WATCH" and e["action_type"] in NET_BUY_ACTIONS)
hold_in_netbuy = sum(1 for e in events if e["action_type"] == "HOLD" and e["action_type"] in NET_BUY_ACTIONS)
# net_buy 计数应与 P3.1 positive_events=205 一致
n_pos_events = sum(1 for e in events if e["action_type"] in NET_BUY_ACTIONS)
n_neg_events = sum(1 for e in events if e["action_type"] in NET_SELL_ACTIONS)

governance = {
    "do_t_events_in_net_buy": do_t_in_netbuy,
    "watch_events_in_net_buy": watch_in_netbuy,
    "hold_events_in_net_buy": hold_in_netbuy,
    "net_buy_events": net_buy_events,
    "net_buy_events_expected": n_pos_events,
    "net_buy_weighted": round(net_buy_weighted, 4),
    "net_sell_events": n_neg_events,
    "consistency_with_p31": net_buy_events == n_pos_events == 205,
}

# ---------- 4. 每股动作流概览（首末事件 + 阶段序列） ----------
per_stock_flow_summary = defaultdict(list)
for (analyst, code), seq in flow.items():
    per_stock_flow_summary[code].append({
        "analyst": analyst,
        "n_events": len(seq),
        "first_date": seq[0]["date"],
        "last_date": seq[-1]["date"],
        "stage_sequence": [ev["stage"] for ev in seq],
        "action_sequence": [ev["action_type"] for ev in seq],
    })

result = {
    "generated_at": "P3.2 v1",
    "semantic_contract": {
        "do_t_not_net_buy": "DO_T 只计 tactical 活动，不进 BUY/ADD/LOW_BUY/TRIAL 净买入集合",
        "watch_not_buy": "WATCH 是关注/观察（stage=SCAN），不等于 BUY",
        "hold_not_entry": "HOLD 是持仓状态，不是新建仓动作",
    },
    "stage_map": STAGE_MAP,
    "governance": governance,
    "flow_summary": {
        "n_analyst_stock_pairs": len(flow),
        "pairs_by_action_type": dict(sorted(pairs_by_action.items(), key=lambda x: -x[1])),
        "flow_length_dist": dict(sorted(flow_length_dist.items())),
        "stage_transitions": {f"{a}→{b}": n for (a, b), n in stage_transitions.most_common()},
        "n_do_t_pairs": len(set(do_t_pairs)),
    },
    "per_analyst_stock_flow": {f"{a}|{c}": seq for (a, c), seq in flow.items()},
    "per_stock_flow_summary": dict(sorted(per_stock_flow_summary.items())),
}

with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

# ---------- 报告 ----------
top_pairs = sorted(flow.items(), key=lambda x: -len(x[1]))[:10]

md = f"""# P3.2 Analyst Action Flow — 分析师动作流

日期：2026-08-30　数据源：data/analyst_consensus.db（eligible events）

## 语义契约（锁定）
- **DO_T 不当净买入**：只计 tactical 活动，不进 BUY/ADD/LOW_BUY/TRIAL 净买入集合
- **WATCH 不等于 BUY**：WATCH 是关注/观察（stage=SCAN），不等于建仓
- **HOLD 不等于新建仓**：HOLD 是持仓状态，不是买入动作

## Stage 映射
WATCH→SCAN / BUY·LOW_BUY·TRIAL→ENTRY / ADD→ACCUMULATE / HOLD→HOLD / REDUCE→REDUCE / SELL·CLEAR→EXIT / DO_T→TACTICAL / UNKNOWN→UNKNOWN

## 动作流规模
- 分析师×股票对：**{len(flow)}**　最长序列事件数：{max(flow_length_dist.keys()) if flow_length_dist else 0}
- 每股每日 cell 事件流长度分布：{json.dumps(dict(sorted(flow_length_dist.items())), ensure_ascii=False)}

## 动作流统计（(分析师,股票) 对出现过的动作）
{chr(10).join(f"- **{k}**: {v} 对" for k, v in sorted(pairs_by_action.items(), key=lambda x: -x[1]))}

## 治理自检
- DO_T 事件进净买入：{governance["do_t_events_in_net_buy"]}（应 0）
- WATCH 事件进净买入：{governance["watch_events_in_net_buy"]}（应 0）
- HOLD 事件进净买入：{governance["hold_events_in_net_buy"]}（应 0）
- 净买入事件：{governance["net_buy_events"]}（期望 {governance["net_buy_events_expected"]}，P3.1 positive=205）
- 净买入加权：{governance["net_buy_weighted"]}　净卖出事件：{governance["net_sell_events"]}
- 与 P3.1 一致性：{governance["consistency_with_p31"]}

## Top 动作流（分析师×股票，按事件数）
| 分析师 | 股票 | 事件数 | 动作序列 |
| --- | --- | --- | --- |
{chr(10).join(f"| {k[0]} | {k[1]} | {len(v)} | {'→'.join(x['action_type'] for x in v)} |" for k, v in top_pairs)}

## 常见 Stage 转移（Top 10）
{chr(10).join(f"- {k}: {v}" for k, v in list(stage_transitions.most_common())[:10])}
"""
with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write(md)

print(f"分析师×股票对 = {len(flow)}")
print(f"flow 长度分布 = {dict(sorted(flow_length_dist.items()))}")
print(f"pairs_by_action = {dict(sorted(pairs_by_action.items(), key=lambda x: -x[1]))}")
print(f"DO_T 进净买入 = {governance['do_t_events_in_net_buy']}, WATCH 进净买入 = {governance['watch_events_in_net_buy']}, HOLD 进净买入 = {governance['hold_events_in_net_buy']}")
print(f"净买入 = {governance['net_buy_events']} 事件 / {governance['net_buy_weighted']} 加权（P3.1 一致性 {governance['consistency_with_p31']}）")
print(f"Top 动作流: " + ", ".join(f"{k[0]}|{k[1]}({len(v)})" for k, v in top_pairs[:5]))
print(f"输出: {OUT_JSON}")
