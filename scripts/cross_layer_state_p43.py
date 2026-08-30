#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cross_layer_state_p43.py — P4.3 Cross-Layer State（个股×主题联动状态机）
=========================================================================
用户 2026-08-30 锁定 6 状态：
  DISCOVERY / CONFIRMING / CONFIRMED / DIVERGING / WEAKENING / REVERSING

输入（每股）：
  S = 个股方向（P4.1）  T = 主题方向（P4.1）  linkage（P4.1）
  div_score（P4.2）  holding_action_divergence（P4.2）  view_action_divergence（P4.2）
  theme_momentum_eff（P2.3）  consensus_state（P3.3）

v1 判定（优先级从高到低，规则可复算）：
  1 UNMAPPED        无主题映射（P2.2A 保留 unmapped）
  2 REVERSING       dir 为正 且 (holding_neg 或 view_mismatch) 且 theme 不升温
                    → 曾看多但持仓/观点操作开始转负 → 反转风险
  3 CONFIRMED       dir≠0 且 theme 同向 且 div<0.5 且 linkage∈{CONFIRMED_BULLISH,CONFIRMED_BEARISH}
                    → 三维共振 + 低分歧 = 确认
  4 CONFIRMING      dir≠0 且 theme 同向 且 (div≥0.5 或 linkage==THEME_CONFIRMED_STOCK)
                    → 方向对但分歧/强度未到 CONFIRMED
  5 DIVERGING       dir≠0 且 theme 反向（S·T<0）
                    → 个股与主题背离
  6 WEAKENING       theme_down 且 dir∈{0,+1}
                    → 主题退潮，个股信号残留/中性
  7 DISCOVERY       theme_up 且 dir∈{0,−1}
                    → 主题刚开始升温，个股尚未跟上
  8 NEUTRAL         其余

注：当前为横截面状态（8 天样本）；时间序列转移状态机待样本 15-20 日后升级（v2）。

输出：data/p43/cross_layer_state.json + reports/cross_layer_state_p43.md
用法：python3 scripts/cross_layer_state_p43.py
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P41_JSON = ROOT / "data" / "p41" / "stock_theme_linkage.json"
P42_JSON = ROOT / "data" / "p42" / "consensus_divergence.json"
OUT_JSON = ROOT / "data" / "p43" / "cross_layer_state.json"
OUT_MD = ROOT / "reports" / "cross_layer_state_p43.md"
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

p41 = json.loads(P41_JSON.read_text(encoding="utf-8"))["per_stock"]
p42 = json.loads(P42_JSON.read_text(encoding="utf-8"))["per_stock"]

UP_THEMES = {"HEATING", "EMERGING", "DISCOVERY"}   # theme 升温/新出现（DISCOVERY 也算主题侧发现）
DOWN_THEMES = {"COOLING", "FADING"}

def decide_state(v):
    code = v["stock_code"]
    if not v["mapped"]:
        return "UNMAPPED", ["no_theme_mapping"]
    S = v["S"]
    T = v["T"]
    dir_pos = S == 1
    dir_neg = S == -1
    theme_up = T == 1
    theme_down = T == -1
    theme_neutral = T == 0
    holding_neg = p42[code]["holding_action_divergence"] == 1.0
    view_mismatch = p42[code]["view_action_divergence"] == 1.0
    div = p42[code]["divergence_score"]
    linkage = v["linkage_signal"]
    notes = []

    # 2 REVERSING：曾看多但持仓/操作转负，且主题未在升温支撑
    if dir_pos and (holding_neg or view_mismatch) and not theme_up:
        notes.append("positive_but_holding_or_view_turning_negative")
        return "REVERSING", notes
    # 3 CONFIRMED
    if dir_pos and theme_up and div < 0.5 and linkage in ("CONFIRMED_BULLISH",):
        notes.append("bullish_resonance_low_divergence")
        return "CONFIRMED", notes
    if dir_neg and theme_down and div < 0.5 and linkage in ("CONFIRMED_BEARISH",):
        notes.append("bearish_resonance_low_divergence")
        return "CONFIRMED", notes
    # 4 CONFIRMING
    if dir_pos and theme_up and (div >= 0.5 or linkage == "THEME_CONFIRMED_STOCK"):
        notes.append("bullish_direction_confirming")
        return "CONFIRMING", notes
    if dir_neg and theme_down and (div >= 0.5 or linkage == "THEME_CONFIRMED_STOCK"):
        notes.append("bearish_direction_confirming")
        return "CONFIRMING", notes
    # 5 DIVERGING
    if S != 0 and T != 0 and S * T < 0:
        notes.append("stock_theme_opposite_direction")
        return "DIVERGING", notes
    # 6 WEAKENING
    if theme_down and (dir_pos or S == 0):
        notes.append("theme_fading_stock_residual")
        return "WEAKENING", notes
    # 7 DISCOVERY
    if theme_up and (dir_neg or S == 0):
        notes.append("theme_rising_stock_not_yet")
        return "DISCOVERY", notes
    return "NEUTRAL", notes or ["no_clear_signal"]

result = {}
for code, v in p41.items():
    state, notes = decide_state(v)
    result[code] = {
        "stock_code": code,
        "cross_layer_state": state,
        "state_notes": notes,
        "linkage_signal": v["linkage_signal"],
        "consensus_state": v["stock_consensus_state"],
        "S": v["S"], "T": v["T"],
        "theme": v.get("main_theme") or v.get("theme_id"),
        "theme_momentum": v.get("theme_momentum_eff") or v.get("theme_momentum"),
        "divergence_score": p42[code]["divergence_score"],
        "holding_action_divergence": p42[code]["holding_action_divergence"],
        "view_action_divergence": p42[code]["view_action_divergence"],
    }

state_dist = Counter(v["cross_layer_state"] for v in result.values())
linkage_vs_state = {}
for sig in ["CONFIRMED_BULLISH", "STOCK_THEME_DIVERGENCE", "CONFIRMED_BEARISH", "THEME_CONFIRMED_STOCK", "LAGGING_OR_DISTRIBUTION", "NEUTRAL", "UNMAPPED"]:
    sub = [v for v in result.values() if v["linkage_signal"] == sig]
    if sub:
        linkage_vs_state[sig] = dict(Counter(v["cross_layer_state"] for v in sub))

summary = {
    "n_stocks": len(result),
    "state_distribution": dict(state_dist),
    "linkage_to_state_map": linkage_vs_state,
    "state_rules_v1": {
        "UNMAPPED": "无主题映射",
        "REVERSING": "曾看多但持仓/观点操作转负，且主题未升温支撑",
        "CONFIRMED": "三维共振（个股+主题同向+动作正）+ 分歧<0.5",
        "CONFIRMING": "方向同向但分歧≥0.5 或仅 THEME_CONFIRMED_STOCK",
        "DIVERGING": "个股与主题方向相反（S·T<0）",
        "WEAKENING": "主题退潮（COOLING/FADING）但个股残留/中性",
        "DISCOVERY": "主题刚开始升温（HEATING/EMERGING/DISCOVERY）但个股未跟上",
        "NEUTRAL": "无明确信号",
    },
    "note": "横截面状态（8 天样本）；时间序列转移状态机待样本 15-20 日后升级 v2",
}

output = {
    "generated_at": "P4.3 v1",
    "summary": summary,
    "per_stock": dict(sorted(result.items())),
}
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

def sample(state, n=8):
    rows = [v for v in result.values() if v["cross_layer_state"] == state]
    rows.sort(key=lambda x: -abs(x["divergence_score"]))
    return rows[:n]

md = f"""# P4.3 Cross-Layer State — 个股×主题联动状态机

日期：2026-08-30　数据源：P4.1 linkage + P4.2 divergence + P2.3 momentum + P3.3 consensus

## 6 状态（用户锁定）
| 状态 | 判定（v1） |
| --- | --- |
| DISCOVERY | 主题刚开始升温（HEATING/EMERGING/DISCOVERY）但个股未跟上（S∈{{0,−1}}） |
| CONFIRMING | 个股主题同向但分歧≥0.5 或仅 THEME_CONFIRMED_STOCK |
| CONFIRMED | 三维共振（个股+主题+动作同向）+ 分歧<0.5 |
| DIVERGING | 个股与主题方向相反（S·T<0） |
| WEAKENING | 主题退潮（COOLING/FADING）但个股残留/中性 |
| REVERSING | 曾看多但持仓/观点操作转负，且主题未升温支撑 |

## 状态分布
{json.dumps(dict(state_dist), ensure_ascii=False)}

## linkage → state 映射
{json.dumps(linkage_vs_state, ensure_ascii=False, indent=1)}

## 样本
### CONFIRMED（{state_dist['CONFIRMED']}）
| 股票 | state | 主题 | theme_mom | consensus | div | notes |
| --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(f"| {v['stock_code']} | {v['cross_layer_state']} | {v['theme']} | {v['theme_momentum']} | {v['consensus_state']} | {v['divergence_score']} | {'/'.join(v['state_notes'])} |" for v in sample('CONFIRMED'))}

### REVERSING（{state_dist['REVERSING']}）
| 股票 | state | 主题 | theme_mom | consensus | div | notes |
| --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(f"| {v['stock_code']} | {v['cross_layer_state']} | {v['theme']} | {v['theme_momentum']} | {v['consensus_state']} | {v['divergence_score']} | {'/'.join(v['state_notes'])} |" for v in sample('REVERSING'))}

### DISCOVERY（{state_dist['DISCOVERY']}）
| 股票 | state | 主题 | theme_mom | consensus | div | notes |
| --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(f"| {v['stock_code']} | {v['cross_layer_state']} | {v['theme']} | {v['theme_momentum']} | {v['consensus_state']} | {v['divergence_score']} | {'/'.join(v['state_notes'])} |" for v in sample('DISCOVERY'))}

## 说明
当前为**横截面状态**（8 天样本，个股观测稀疏）；时间序列转移状态机（如 DISCOVERY→CONFIRMING→CONFIRMED 的跨日转移）待样本 15-20 日后升级 v2。
"""
with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write(md)

print(f"状态分布: {dict(state_dist)}")
for sig, mp in linkage_vs_state.items():
    print(f"  {sig}: {mp}")
print(f"输出: {OUT_JSON}")
