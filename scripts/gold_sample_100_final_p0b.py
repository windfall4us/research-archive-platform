#!/usr/bin/env python3
"""0B.5 Gold Sample v1 FINAL 生成器 — 事件级。

输入: gold_sample_100.csv（原始标注）+ reports/arbitration_list_p0b.csv（P1-P6 已锁仲裁）
输出: data/analyst_snapshots/gold_sample_100_final.json + 统计表

数据模型（用户确认，事件级）:
  sample_id, analyst, date, raw_target, raw_action, raw_logic, direction,
  entity_type, entity_scope,
  events: [{action, action_status, temporal_type}...],   # 每个动作独立 status+temporal（协议11）
  position_state: HOLDING|null,                          # 双轨
  exclude_from_core_benchmark, ambig, stance, arbiter_result, review_note
"""
import csv, json, sys
from collections import Counter
from pathlib import Path

ROOT = Path("/home/windfall/workspace/research-archive-platform")
GS100 = ROOT / "data/analyst_snapshots/gold_sample_100.csv"
ARB = ROOT / "reports/arbitration_list_p0b.csv"
OUT = ROOT / "data/analyst_snapshots/gold_sample_100_final.json"

# 多事件行（用户仲裁确认的完整事件列表；primary 与仲裁 CSV final_* 一致）
MULTI_EVENTS = {
    "5":  [("REDUCE", "EXECUTED", "TODAY"), ("ADD", "CONDITIONAL", "CONDITIONAL")],
    "7":  [("HOLD", "POSITION_STATE", "CONDITIONAL"), ("REDUCE", "CONDITIONAL", "CONDITIONAL"),
           ("ADD", "CONDITIONAL", "CONDITIONAL")],
    "9":  [("REDUCE", "EXECUTED", "PAST"), ("HOLD", "INTENDED", "TODAY")],
    "59": [("DO_T", "INTENDED", "CONDITIONAL"), ("REDUCE", "CONDITIONAL", "CONDITIONAL"),
           ("ADD", "CONDITIONAL", "CONDITIONAL")],
    "62": [("LOW_BUY", "INTENDED", "TODAY"), ("HOLD", "POSITION_STATE", "CURRENT_STATE")],
    "64": [("LOW_BUY", "INTENDED", "TODAY"), ("HOLD", "POSITION_STATE", "CURRENT_STATE")],
    "68": [("LOW_BUY", "INTENDED", "TODAY"), ("DO_T", "INTENDED", "TODAY")],
    "69": [("BUY", "INTENDED", "TODAY"), ("ADD", "CONDITIONAL", "CONDITIONAL")],
    "73": [("ADD", "EXECUTED", "PAST"), ("HOLD", "INTENDED", "CONDITIONAL")],
    "74": [("SELL", "CONDITIONAL", "CONDITIONAL"), ("ADD", "CONDITIONAL", "CONDITIONAL")],
    "75": [("ADD", "EXECUTED", "TODAY"), ("HOLD", "POSITION_STATE", "CURRENT_STATE")],
    "80": [("HOLD", "POSITION_STATE", "CURRENT_STATE"), ("SELL", "CONDITIONAL", "CONDITIONAL")],
    "92": [("REDUCE", "EXECUTED", "TODAY"), ("CLEAR", "INTENDED", "TODAY"),
           ("ADD", "CONDITIONAL", "CONDITIONAL")],
    "100":[("HOLD", "POSITION_STATE", "CONDITIONAL"), ("REDUCE", "CONDITIONAL", "CONDITIONAL")],
}

# 实体范围（0B.4 已注册/协议7）
ENTITY_SCOPE = {
    "61": "MARKET",       # 大盘
    "23": "OUT_OF_SCOPE", # 中国金茂(0B.4 out_of_scope 注册)
    "98": "THEME",        # 特高压方向
    "38": "THEME",        # 半导体硅片
    "57": "THEME",        # 折叠屏
    "58": "THEME",        # 冷液
}
# 姿态（P6 负面/正面 stance 标注，保留扩展点）
STANCE = {"33": "AVOID", "15": "CAUTION", "35": "POSITIVE"}

# 读仲裁结果（94 条分歧锁定值）
arb = {}
for r in csv.DictReader(open(ARB, encoding="utf-8")):
    arb[r["sample_id"]] = r

rows = list(csv.DictReader(open(GS100, encoding="utf-8")))
final = []
n_multi = 0
n_excluded = 0
n_ambig = 0
evt_counter = Counter(); act_counter = Counter(); st_counter = Counter(); te_counter = Counter()

for g in rows:
    sid = g["sample_id"]
    a = arb.get(sid)   # None = 完全一致行（6 条）

    if a:
        arb_res = a["arbiter_result"]
        exclude = a["exclude_from_core_benchmark"] == "true"
        note = a["review_note"]
        # 事件：优先多事件表，否则单事件（final_*）；AMBIGUOUS 无终值 → 空事件
        if sid in MULTI_EVENTS:
            events = [{"action": x, "action_status": y, "temporal_type": z}
                      for x, y, z in MULTI_EVENTS[sid]]
        elif a["final_action"]:
            events = [{"action": a["final_action"], "action_status": a["final_status"],
                       "temporal_type": a["final_temporal"]}]
        else:
            events = []   # AMBIGUOUS 无终值（[57][58][87]），exclude=true
    else:
        # 完全一致行：用 draft 值（=parser）
        arb_res = "AGREED"
        exclude = False
        note = ""
        events = [{"action": g["actions_draft"], "action_status": g["action_status_draft"],
                   "temporal_type": g["temporal_type_draft"]}]

    ambig = arb_res in ("AMBIGUOUS",)
    if ambig: n_ambig += 1
    if exclude: n_excluded += 1
    if len(events) > 1: n_multi += 1

    # position_state 双轨：任一 HOLD/POSITION_STATE → HOLDING
    holding = any(e["action"] == "HOLD" and e["action_status"] == "POSITION_STATE" for e in events)
    entity_scope = ENTITY_SCOPE.get(sid, "A_SHARE")

    for e in events:
        evt_counter["events"] += 1
        act_counter[e["action"]] += 1
        st_counter[e["action_status"]] += 1
        te_counter[e["temporal_type"]] += 1

    final.append({
        "sample_id": sid, "analyst": g["analyst"], "date": g["date"],
        "raw_target": g["raw_target"], "raw_action": g["raw_action"], "raw_logic": g["raw_logic"],
        "direction": g["direction"],
        "entity_type": g["entity_type_draft"], "entity_scope": entity_scope,
        "events": events,
        "position_state": "HOLDING" if holding else None,
        "exclude_from_core_benchmark": exclude, "ambig": ambig,
        "stance": STANCE.get(sid),
        "arbiter_result": arb_res, "review_note": note,
    })

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(final, f, ensure_ascii=False, indent=1)

# ---- 统计表 ----
core = [r for r in final if not r["exclude_from_core_benchmark"] and not r["ambig"]]
amb = [r for r in final if r["ambig"]]
excl = [r for r in final if r["exclude_from_core_benchmark"] and not r["ambig"]]
print(f"Gold Sample v1 FINAL → {OUT}")
print()
print("ROW LEVEL（样本级）")
print(f"  原始样本 {len(final)} | CORE rows {len(core)} | AMBIGUOUS rows {len(amb)} | EXCLUDED(非ambig) {len(excl)}")
print(f"  非core去重 {len([r for r in final if r['exclude_from_core_benchmark'] or r['ambig']])} 行"
      f"（[10]同时ambig+exclude，双计）")
print(f"EVENT LEVEL（事件级）")
print(f"  总事件 {evt_counter['events']} = 100 行 + {n_multi} 多事件行")
print(f"  CORE events {sum(len(r['events']) for r in core)}"
      f" | AMBIGUOUS events {sum(len(r['events']) for r in amb)}"
      f" | EXCLUDED events {sum(len(r['events']) for r in excl)}"
      f"  ← Benchmark 输入 = CORE events")
print()
print("Action 分布:", dict(act_counter.most_common()))
print("Status 分布:", dict(st_counter.most_common()))
print("Temporal 分布:", dict(te_counter.most_common()))
print("实体范围:", dict(Counter(r['entity_scope'] for r in final)))
print("仲裁来源:", dict(Counter(r['arbiter_result'] for r in final)))
