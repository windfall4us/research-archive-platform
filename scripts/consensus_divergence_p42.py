#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
consensus_divergence_p42.py — P4.2 Consensus / Divergence（量化分歧指标）
=========================================================================
用户 2026-08-30 重点识别（5 项）：
  1) 多分析师同向           → consensus_strength（同向率 × 分析师数加权）
  2) 分析师意见分裂         → analyst_divergence（0~1）
  3) 主题与个股不同步       → theme_stock_divergence（S vs T 方向差）
  4) 观点与真实操作不同步   → view_action_divergence（INTENDED 意图 vs EXECUTED 执行）
  5) 持仓仍在但动作开始转负 → holding_action_divergence（has_holding 且近期动作转负）

指标（每股，全 350 只）：
  consensus_strength   = 0~1：same_direction_rate × min(1, n_analysts/3)
                         （同向率 = max(pos_a,neg_a)/n_analysts；分析师数<3 打折防单分析师虚高）
  analyst_divergence   = 0~1：有正负两派时 min(pos,neg)/max(pos,neg)，单边=0
  theme_stock_divergence = |S−T|/2（S,T∈{−1,0,1}，P4.1 方向）
  view_action_divergence = INTENDED 加权方向 vs EXECUTED 加权方向：异号=1，同号=0，一方中性=0.5
  holding_action_divergence = has_holding 且最近3动作净方向：负=1 / 中性=0.5 / 正=0 / 无持仓=0
  divergence_score    = 4 维分歧均分（analyst / theme_stock / view_action / holding_action）

输出：data/p42/consensus_divergence.json + reports/consensus_divergence_p42.md
用法：python3 scripts/consensus_divergence_p42.py
"""
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "analyst_consensus.db"
P33_JSON = ROOT / "data" / "p33" / "stock_consensus_score.json"
P41_JSON = ROOT / "data" / "p41" / "stock_theme_linkage.json"
P32_JSON = ROOT / "data" / "p32" / "analyst_action_flow.json"
OUT_JSON = ROOT / "data" / "p42" / "consensus_divergence.json"
OUT_MD = ROOT / "reports" / "consensus_divergence_p42.md"
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

ACTION_W = {"BUY": 1.0, "ADD": 0.8, "LOW_BUY": 0.7, "TRIAL": 0.4,
            "REDUCE": -0.5, "SELL": -0.8, "CLEAR": -1.0}
POS = {"BUY", "ADD", "LOW_BUY", "TRIAL"}
NEG = {"REDUCE", "SELL", "CLEAR"}

db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row
c = db.cursor()

p33 = json.loads(P33_JSON.read_text(encoding="utf-8"))["per_stock"]
p41 = json.loads(P41_JSON.read_text(encoding="utf-8"))["per_stock"]
p32f = json.loads(P32_JSON.read_text(encoding="utf-8"))["per_analyst_stock_flow"]

# ---------- 每股 INTENDED vs EXECUTED 加权方向 ----------
# 从 events 表按 action_status 拆分
ev_rows = [dict(r) for r in c.execute(
    """SELECT stock_code, action_type, action_status FROM analyst_stock_events
       WHERE event_id NOT IN (SELECT event_id FROM consensus_event_exclusions)""")]
intended_net = defaultdict(float)
executed_net = defaultdict(float)
intended_n = Counter()
executed_n = Counter()
for e in ev_rows:
    w = ACTION_W.get(e["action_type"], 0.0)
    if w == 0:
        continue
    if e["action_status"] == "INTENDED":
        intended_net[e["stock_code"]] += w
        intended_n[e["stock_code"]] += 1
    elif e["action_status"] == "EXECUTED":
        executed_net[e["stock_code"]] += w
        executed_n[e["stock_code"]] += 1

def sign(x):
    return 1 if x > 0.01 else (-1 if x < -0.01 else 0)

result = {}
for code, sv in p33.items():
    p41v = p41[code]
    S = p41v["S"]
    T = p41v["T"]

    # 1) consensus_strength
    n_a = sv["n_analysts"]
    pos_a, neg_a = sv["pos_analysts"], sv["neg_analysts"]
    if n_a >= 1:
        same_rate = max(pos_a, neg_a) / n_a
    else:
        same_rate = 0.0
    consensus_strength = round(same_rate * min(1.0, n_a / 3.0), 4)

    # 2) analyst_divergence
    if n_a >= 2 and max(pos_a, neg_a) > 0:
        analyst_div = round(min(pos_a, neg_a) / max(pos_a, neg_a), 4)
    else:
        analyst_div = 0.0

    # 3) theme_stock_divergence
    theme_stock_div = round(abs((S or 0) - (T or 0)) / 2.0, 4)

    # 4) view_action_divergence
    iv, ev_ = sign(intended_net.get(code, 0.0)), sign(executed_net.get(code, 0.0))
    if iv == 0 and ev_ == 0:
        view_action_div = 0.0
    elif iv != 0 and ev_ != 0 and iv != ev_:
        view_action_div = 1.0
    elif iv == 0 or ev_ == 0:
        view_action_div = 0.5
    else:
        view_action_div = 0.0

    # 5) holding_action_divergence
    has_hold = sv["has_holding"]
    a_net = p41v["action_net_recent"]
    if has_hold:
        if a_net is not None and a_net < -0.01:
            holding_action_div = 1.0
        elif a_net is not None and a_net > 0.01:
            holding_action_div = 0.0
        else:
            holding_action_div = 0.5
    else:
        holding_action_div = 0.0

    divergence_score = round((analyst_div + theme_stock_div + view_action_div + holding_action_div) / 4.0, 4)

    result[code] = {
        "stock_code": code,
        "n_analysts": n_a,
        "pos_analysts": pos_a,
        "neg_analysts": neg_a,
        "consensus_strength": consensus_strength,
        "analyst_divergence": analyst_div,
        "theme_stock_divergence": theme_stock_div,
        "view_action_divergence": view_action_div,
        "holding_action_divergence": holding_action_div,
        "divergence_score": divergence_score,
        "S": S, "T": T,
        "linkage_signal": p41v["linkage_signal"],
        "consensus_state": sv["consensus_state"],
        "has_holding": has_hold,
        "recent_actions": p41v["recent_actions"],
        "intended_net": round(intended_net.get(code, 0.0), 4),
        "executed_net": round(executed_net.get(code, 0.0), 4),
    }

# ---------- 汇总 ----------
sig_dist = Counter(v["linkage_signal"] for v in result.values())
high_div = [v for v in result.values() if v["divergence_score"] >= 0.5]
multi_analyst = [v for v in result.values() if v["n_analysts"] >= 3]
same_direction = [v for v in result.values() if v["n_analysts"] >= 2 and v["analyst_divergence"] == 0.0]
split = [v for v in result.values() if v["analyst_divergence"] >= 0.5]
theme_stock_mismatch = [v for v in result.values() if v["theme_stock_divergence"] == 1.0]
view_action_mismatch = [v for v in result.values() if v["view_action_divergence"] == 1.0]
holding_turning_neg = [v for v in result.values() if v["holding_action_divergence"] == 1.0]

summary = {
    "n_stocks": len(result),
    "n_high_divergence(>=0.5)": len(high_div),
    "n_multi_analyst(>=3)": len(multi_analyst),
    "n_analyst_same_direction(>=2,div=0)": len(same_direction),
    "n_analyst_split(div>=0.5)": len(split),
    "n_theme_stock_mismatch": len(theme_stock_mismatch),
    "n_view_action_mismatch": len(view_action_mismatch),
    "n_holding_turning_negative": len(holding_turning_neg),
    "divergence_definition": {
        "consensus_strength": "same_direction_rate × min(1, n_analysts/3)（0~1，防单分析师虚高）",
        "analyst_divergence": "min(pos,neg)/max(pos,neg)（正负两派，单边=0）",
        "theme_stock_divergence": "|S−T|/2（主题与个股方向差）",
        "view_action_divergence": "INTENDED vs EXECUTED 加权方向异号（观点与操作不同步）",
        "holding_action_divergence": "持仓仍在但最近3动作转负",
        "divergence_score": "4 维分歧均分",
    },
}

output = {
    "generated_at": "P4.2 v1",
    "summary": summary,
    "per_stock": dict(sorted(result.items())),
}
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

# ---------- 报告 ----------
def sample(vals, key, n=8, reverse=True):
    return sorted(vals, key=lambda x: x[key], reverse=reverse)[:n]

md = f"""# P4.2 Consensus / Divergence — 量化分歧指标

日期：2026-08-30　数据源：P3.3 consensus + P4.1 linkage + P3.2 action flow + events(action_status)

## 5 项重点识别（用户锁定）
| 指标 | 定义 | 命中 |
| --- | --- | --- |
| consensus_strength | 同向率 × min(1, 分析师数/3)（0~1，防单分析师虚高） | — |
| analyst_divergence | min(pos,neg)/max(pos,neg)（正负两派） | 分裂(≥0.5) **{len(split)}** 只 |
| theme_stock_divergence | ｜S−T｜/2（主题与个股方向差） | 完全反向 **{len(theme_stock_mismatch)}** 只 |
| view_action_divergence | INTENDED vs EXECUTED 异号（观点≠操作） | 异号 **{len(view_action_mismatch)}** 只 |
| holding_action_divergence | 持仓仍在但最近3动作转负 | **{len(holding_turning_neg)}** 只 |

- 多分析师同向（≥2 且 div=0）：**{len(same_direction)}** 只
- 多分析师（≥3）：**{len(multi_analyst)}** 只
- 高综合分歧（divergence_score≥0.5）：**{len(high_div)}** 只

## 高综合分歧 Top（divergence_score）
| 股票 | state | div_score | analyst_div | theme_stock | view_action | holding | strength |
| --- | --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(f"| {v['stock_code']} | {v['consensus_state']} | {v['divergence_score']} | {v['analyst_divergence']} | {v['theme_stock_divergence']} | {v['view_action_divergence']} | {v['holding_action_divergence']} | {v['consensus_strength']} |" for v in sample(high_div, 'divergence_score'))}

## 持仓转负（holding_action_divergence=1）
| 股票 | state | 近3动作 | has_holding |
| --- | --- | --- | --- |
{chr(10).join(f"| {v['stock_code']} | {v['consensus_state']} | {'→'.join(v['recent_actions']) or '-'} | {v['has_holding']} |" for v in sample(holding_turning_neg, 'consensus_strength'))}
"""
with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write(md)

print(f"高分歧(≥0.5): {len(high_div)}  多分析师同向: {len(same_direction)}  分析师分裂: {len(split)}")
print(f"主题个股反向: {len(theme_stock_mismatch)}  观点操作异号: {len(view_action_mismatch)}  持仓转负: {len(holding_turning_neg)}")
print("持仓转负样本:", ", ".join(f"{v['stock_code']}({'→'.join(v['recent_actions'])})" for v in holding_turning_neg[:8]))
print("高分歧样本:", ", ".join(f"{v['stock_code']}({v['divergence_score']})" for v in high_div[:8]))
print(f"输出: {OUT_JSON}")
