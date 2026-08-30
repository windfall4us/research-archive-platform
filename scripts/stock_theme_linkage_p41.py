#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stock_theme_linkage_p41.py — P4.1 Stock × Theme Linkage（个股×主题联动信号）
=============================================================================
用户 2026-08-30 定义：
  个股是否被持续看多 + 所属主题是否升温 + 个股动作流是否与主题一致 → 联动标签
    例1: STRONG_POSITIVE + HEATING + ENTRY→ACCUMULATE → CONFIRMED_BULLISH
    例2: POSITIVE + FADING → STOCK_THEME_DIVERGENCE
    例3: HEATING + 连续 REDUCE/SELL → LAGGING_OR_DISTRIBUTION

三维信号（每股，主主题 = confidence 最高的映射）：
  S stock_direction = +1(STRONG_POSITIVE/POSITIVE) / 0(NEUTRAL) / -1(STRONG_NEGATIVE/NEGATIVE)
  T theme_direction = +1(momentum_eff∈{HEATING,EMERGING}) / 0(STABLE/DISCOVERY/BASELINE_ONLY)
                     / -1(COOLING/FADING)
  A action_net_recent = 每股最近3事件动作加权方向（BUY/ADD/LOW_BUY/TRIAL=+，REDUCE/SELL/CLEAR=−）
                        +1(>+0.5) / 0(−0.5~+0.5) / −1(<−0.5)

联动标签（v1 规则，P4.3 再演进状态机）：
  S+1 T+1 A+1 → CONFIRMED_BULLISH
  S−1 T−1 A−1 → CONFIRMED_BEARISH
  S+1 T−1 或 S−1 T+1 → STOCK_THEME_DIVERGENCE（个股与主题方向矛盾）
  T+1 A−1   → LAGGING_OR_DISTRIBUTION（主题升温但个股动作转负）
  S+1 T+1 A 0 → THEME_CONFIRMED_STOCK（个股主题一致看多，动作中性）
  其他        → NEUTRAL

输出：data/p41/stock_theme_linkage.json + reports/stock_theme_linkage_p41.md
用法：python3 scripts/stock_theme_linkage_p41.py
"""
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "analyst_consensus.db"
HEAT_JSON = ROOT / "data" / "p22c" / "theme_heat_scores.json"
MOM_JSON = ROOT / "data" / "p23" / "theme_momentum.json"
P33_JSON = ROOT / "data" / "p33" / "stock_consensus_score.json"
P32_JSON = ROOT / "data" / "p32" / "analyst_action_flow.json"
OUT_JSON = ROOT / "data" / "p41" / "stock_theme_linkage.json"
OUT_MD = ROOT / "reports" / "stock_theme_linkage_p41.md"
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

HEAT_MIN = 0.60
ACTION_W = {"BUY": 1.0, "ADD": 0.8, "LOW_BUY": 0.7, "TRIAL": 0.4,
            "REDUCE": -0.5, "SELL": -0.8, "CLEAR": -1.0}
POS = {"BUY", "ADD", "LOW_BUY", "TRIAL"}
NEG = {"REDUCE", "SELL", "CLEAR"}
UP_STATES = {"HEATING", "EMERGING"}
DOWN_STATES = {"COOLING", "FADING"}

db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row
c = db.cursor()

# ---------- 1. 数据加载 ----------
p33 = json.loads(P33_JSON.read_text(encoding="utf-8"))["per_stock"]
heat = json.loads(HEAT_JSON.read_text(encoding="utf-8"))
mom = json.loads(MOM_JSON.read_text(encoding="utf-8"))
p32 = json.loads(P32_JSON.read_text(encoding="utf-8"))["per_analyst_stock_flow"]

# 主题最新一天 heat/momentum
latest_by_theme = {}
for tid in sorted({r["theme_id"] for r in heat}):
    tdates = sorted({r["date"] for r in heat if r["theme_id"] == tid})
    if tdates:
        ld = tdates[-1]
        h = next((x for x in heat if x["date"] == ld and x["theme_id"] == tid), None)
        m = next((x for x in mom if x["date"] == ld and x["theme_id"] == tid), None)
        latest_by_theme[tid] = {"heat": h, "momentum": m}

# ---------- 2. 每股主主题（confidence 最高） ----------
mappings = [dict(r) for r in c.execute(
    """SELECT stock_code, theme_id, mapping_source, confidence FROM stock_theme_mapping
       WHERE confidence >= ?""", (HEAT_MIN,))]
main_theme = {}
by_stock = defaultdict(list)
for m in sorted(mappings, key=lambda x: -x["confidence"]):
    existing = {mm["theme_id"] for mm in by_stock[m["stock_code"]]}
    if m["theme_id"] in existing:
        continue
    by_stock[m["stock_code"]].append(m)
for code, links in by_stock.items():
    main_theme[code] = links[0]  # confidence 最高

# ---------- 3. 每股最近 3 动作的净方向 ----------
def recent_action_net(stock_code):
    seq = []
    for key, flow in p32.items():
        a, s = key.split("|")
        if s == stock_code:
            seq.extend(flow)
    seq.sort(key=lambda x: (x["date"], x["event_id"]))
    last3 = seq[-3:]
    net = sum(ACTION_W.get(e["action_type"], 0.0) for e in last3)
    return net, [e["action_type"] for e in last3]

# ---------- 4. 联动信号 ----------
def stock_dir(state):
    if state in ("STRONG_POSITIVE", "POSITIVE"):
        return 1
    if state in ("STRONG_NEGATIVE", "NEGATIVE"):
        return -1
    return 0

def theme_dir(meff):
    if meff in UP_STATES:
        return 1
    if meff in DOWN_STATES:
        return -1
    return 0

def act_dir(net):
    if net > 0.5:
        return 1
    if net < -0.5:
        return -1
    return 0

def linkage(S, T, A):
    if S == 1 and T == 1 and A == 1:
        return "CONFIRMED_BULLISH"
    if S == -1 and T == -1 and A == -1:
        return "CONFIRMED_BEARISH"
    if (S == 1 and T == -1) or (S == -1 and T == 1):
        return "STOCK_THEME_DIVERGENCE"
    if T == 1 and A == -1:
        return "LAGGING_OR_DISTRIBUTION"
    if S == 1 and T == 1 and A == 0:
        return "THEME_CONFIRMED_STOCK"
    return "NEUTRAL"

result = {}
for code, sv in p33.items():
    mt = main_theme.get(code)
    if not mt:
        # 无主题映射（13 只）
        result[code] = {
            "stock_code": code, "mapped": False, "linkage_signal": "UNMAPPED",
            "stock_consensus_state": sv["consensus_state"],
            "consensus_raw": sv["consensus_raw"],
            "theme_id": None, "theme_heat": None, "theme_momentum": None,
            "action_net_recent": None, "recent_actions": [],
            "S": None, "T": None, "A": None,
        }
        continue
    tid = mt["theme_id"]
    lt = latest_by_theme.get(tid, {})
    h = lt.get("heat") or {}
    m = lt.get("momentum") or {}
    meff = m.get("effective_momentum_state")
    net, acts = recent_action_net(code)
    S = stock_dir(sv["consensus_state"])
    T = theme_dir(meff)
    A = act_dir(net)
    result[code] = {
        "stock_code": code,
        "mapped": True,
        "main_theme": tid,
        "theme_heat": h.get("heat_score"),
        "theme_heat_level": h.get("heat_level"),
        "theme_heat_status": h.get("heat_status"),
        "theme_momentum_eff": meff,
        "theme_momentum_obs": m.get("observed_momentum_state"),
        "stock_consensus_state": sv["consensus_state"],
        "consensus_raw": sv["consensus_raw"],
        "consensus_strength": sv["consensus_strength"],
        "action_net_recent": round(net, 4),
        "recent_actions": acts,
        "S": S, "T": T, "A": A,
        "linkage_signal": linkage(S, T, A),
    }

# ---------- 5. 汇总 ----------
sig_dist = Counter(v["linkage_signal"] for v in result.values())
sig_by_theme = Counter(v["linkage_signal"] for v in result.values() if v["mapped"])

summary = {
    "n_stocks": len(result),
    "n_mapped": sum(1 for v in result.values() if v["mapped"]),
    "linkage_distribution": dict(sig_dist),
    "linkage_rules_v1": {
        "CONFIRMED_BULLISH": "S+1 & T+1 & A+1（个股/主题/动作三维共振看多）",
        "CONFIRMED_BEARISH": "S−1 & T−1 & A−1（三维共振看空）",
        "STOCK_THEME_DIVERGENCE": "个股与主题方向矛盾（S+1T−1 或 S−1T+1）",
        "LAGGING_OR_DISTRIBUTION": "主题升温但个股动作转负（T+1 & A−1）",
        "THEME_CONFIRMED_STOCK": "个股主题一致看多，动作中性（S+1 & T+1 & A0）",
        "NEUTRAL": "其他组合",
        "UNMAPPED": "无主题映射（P2.2A 保留 unmapped）",
    },
}

output = {
    "generated_at": "P4.1 v1",
    "summary": summary,
    "per_stock": dict(sorted(result.items())),
}
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

# ---------- 报告 ----------
def sample_rows(sig, n=6):
    rows = [v for v in result.values() if v["linkage_signal"] == sig and v["mapped"]]
    rows.sort(key=lambda x: -abs(x["consensus_raw"]))
    return rows[:n]

md = f"""# P4.1 Stock × Theme Linkage — 个股×主题联动信号

日期：2026-08-30　数据源：P2.2C heat + P2.3 momentum + P3.2 action flow + P3.3 consensus

## 三维信号（主主题 = confidence 最高映射）
- **S stock_direction**：+1(POSITIVE/STRONG_POSITIVE) / 0(NEUTRAL) / −1(NEGATIVE/STRONG_NEGATIVE)
- **T theme_direction**：+1(momentum_eff∈{{HEATING,EMERGING}}) / 0(STABLE/DISCOVERY/BASELINE) / −1(COOLING/FADING)
- **A action_net_recent**：每股最近 3 事件动作加权（BUY/ADD/LOW_BUY/TRIAL=+，REDUCE/SELL/CLEAR=−）

## 联动标签分布
{json.dumps(dict(sig_dist), ensure_ascii=False)}

## 规则（v1）
| 信号 | 规则 |
| --- | --- |
| CONFIRMED_BULLISH | S+1 & T+1 & A+1（三维共振看多） |
| CONFIRMED_BEARISH | S−1 & T−1 & A−1（三维共振看空） |
| STOCK_THEME_DIVERGENCE | 个股与主题方向矛盾（S+1T−1 或 S−1T+1） |
| LAGGING_OR_DISTRIBUTION | 主题升温但个股动作转负（T+1 & A−1） |
| THEME_CONFIRMED_STOCK | 个股主题一致看多，动作中性（S+1 & T+1 & A0） |
| NEUTRAL | 其他组合 |
| UNMAPPED | 无主题映射（13 只） |

## 样本
### CONFIRMED_BULLISH（{sig_dist['CONFIRMED_BULLISH']}）
| 股票 | state | raw | 主题 | theme_heat | theme_mom | 近3动作 | A |
| --- | --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(f"| {v['stock_code']} | {v['stock_consensus_state']} | {v['consensus_raw']} | {v['main_theme']} | {v['theme_heat']} | {v['theme_momentum_eff']} | {'→'.join(v['recent_actions']) or '-'} | {v['A']} |" for v in sample_rows('CONFIRMED_BULLISH'))}

### STOCK_THEME_DIVERGENCE（{sig_dist['STOCK_THEME_DIVERGENCE']}）
| 股票 | state | raw | 主题 | theme_heat | theme_mom | 近3动作 | A |
| --- | --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(f"| {v['stock_code']} | {v['stock_consensus_state']} | {v['consensus_raw']} | {v['main_theme']} | {v['theme_heat']} | {v['theme_momentum_eff']} | {'→'.join(v['recent_actions']) or '-'} | {v['A']} |" for v in sample_rows('STOCK_THEME_DIVERGENCE'))}

### LAGGING_OR_DISTRIBUTION（{sig_dist['LAGGING_OR_DISTRIBUTION']}）
| 股票 | state | raw | 主题 | theme_heat | theme_mom | 近3动作 | A |
| --- | --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(f"| {v['stock_code']} | {v['stock_consensus_state']} | {v['consensus_raw']} | {v['main_theme']} | {v['theme_heat']} | {v['theme_momentum_eff']} | {'→'.join(v['recent_actions']) or '-'} | {v['A']} |" for v in sample_rows('LAGGING_OR_DISTRIBUTION'))}
"""
with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write(md)

print(f"联动标签分布: {dict(sig_dist)}")
print(f"映射数: {summary['n_mapped']}/{summary['n_stocks']}")
print("CONFIRMED_BULLISH 样本:", ", ".join(f"{v['stock_code']}({v['main_theme']},{v['consensus_raw']})" for v in sample_rows('CONFIRMED_BULLISH', 5)))
print("DIVERGENCE 样本:", ", ".join(f"{v['stock_code']}({v['main_theme']},{v['theme_momentum_eff']})" for v in sample_rows('STOCK_THEME_DIVERGENCE', 5)))
print("LAGGING 样本:", ", ".join(f"{v['stock_code']}({v['main_theme']})" for v in sample_rows('LAGGING_OR_DISTRIBUTION', 5)))
print(f"输出: {OUT_JSON}")
