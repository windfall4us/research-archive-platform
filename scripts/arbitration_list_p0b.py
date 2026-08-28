#!/usr/bin/env python3
"""0B.5 仲裁清单生成器 — 100 行 draft vs parser 分歧，按用户指定优先级分桶。

输出: reports/arbitration_list_p0b.csv（含用户固定 schema + 优先级桶）
分桶优先级（用户 2026-08-28 指定）:
  P1_ACTION_OPPOSITE   动作相反（买入族 vs 卖出族 vs 持有族）— 最高危
  P2_STATUS_CONFLICT   EXECUTED / CONDITIONAL 冲突
  P3_TEMPORAL_CONFLICT TODAY / PAST / CURRENT_STATE / FUTURE_PLAN 真实冲突（双方均非 UNKNOWN）
  P4_BUY_SUBTYPE       BUY vs LOW_BUY vs ADD vs TRIAL 买入族细分类（后置）
  P5_DRAFT_UNKNOWN_TEMPORAL  draft temporal=UNKNOWN（批量补标候选，低价值）
桶内再按 sample_id 排序，保证稳定。
"""
import csv, json, sys
from pathlib import Path

ROOT = Path("/home/windfall/workspace/research-archive-platform")
BENCH = ROOT / "reports/action_temporal_benchmark_p0b.csv"
GS100 = ROOT / "data/analyst_snapshots/gold_sample_100.csv"
OUT = ROOT / "reports/arbitration_list_p0b.csv"

# 动作族（方向相反判定）
FAMILY = {
    "BUY": "BUY_FAMILY", "LOW_BUY": "BUY_FAMILY", "ADD": "BUY_FAMILY", "TRIAL": "BUY_FAMILY",
    "REDUCE": "SELL_FAMILY", "SELL": "SELL_FAMILY", "CLEAR": "SELL_FAMILY", "STOP_LOSS": "SELL_FAMILY",
    "HOLD": "HOLD_FAMILY", "WATCH": "HOLD_FAMILY",
    "DO_T": "NEUTRAL", "UNKNOWN": "UNKNOWN",
}
# temporal 语义对（用户协议② 并列，不算冲突）
COUPLE = {"CONDITIONAL", "FUTURE_PLAN"}

def parse_actions(s):
    """CSV 里 parser_actions 是 JSON 字符串 [['ACT','STATUS'],...]"""
    try:
        v = json.loads(s)
        return v
    except Exception:
        return []

# 读 100 行 gold（补 raw_logic/raw_target）
gold = {}
for r in csv.DictReader(open(GS100, encoding="utf-8")):
    gold[r["sample_id"]] = r

rows = list(csv.DictReader(open(BENCH, encoding="utf-8")))
bucket_counts = {}
entries = []

for r in rows:
    sid = r["sample_id"]
    g = gold.get(sid, {})
    parser_acts = parse_actions(r["parser_actions"])
    p_action = parser_acts[0][0] if parser_acts else "UNKNOWN"
    p_status = parser_acts[0][1] if parser_acts else "UNKNOWN"
    p_temporal = r["parser_temporal"]
    d_action = r["draft_act"] or "UNKNOWN"
    d_status = r["draft_status"] or "UNKNOWN"
    d_temporal = r["draft_temporal"] or "UNKNOWN"

    # 各维度是否分歧
    act_diff = p_action != d_action
    status_diff = p_status != d_status
    t_diff = p_temporal != d_temporal

    # 分桶（取最高优先级）
    bucket = None
    p_fam, d_fam = FAMILY.get(p_action, "UNKNOWN"), FAMILY.get(d_action, "UNKNOWN")
    if act_diff and p_fam != "UNKNOWN" and d_fam != "UNKNOWN" and p_fam != d_fam:
        bucket = "P1_ACTION_OPPOSITE"
    elif status_diff and {p_status, d_status} >= {"EXECUTED"} and {"CONDITIONAL", "INTENDED"} & {p_status, d_status}:
        bucket = "P2_STATUS_CONFLICT"    # EXECUTED vs (CONDITIONAL|INTENDED)
    elif t_diff and d_temporal != "UNKNOWN" and p_temporal != "UNKNOWN" and not ({p_temporal, d_temporal} <= COUPLE):
        bucket = "P3_TEMPORAL_CONFLICT"
    elif act_diff and p_fam == d_fam == "BUY_FAMILY":
        bucket = "P4_BUY_SUBTYPE"
    elif d_temporal == "UNKNOWN" and p_temporal != "UNKNOWN":
        bucket = "P5_DRAFT_UNKNOWN_TEMPORAL"
    elif act_diff or status_diff or t_diff:
        bucket = "P6_OTHER"

    if bucket is None:
        continue   # 完全一致

    bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    entries.append({
        "priority": bucket,
        "sample_id": sid,
        "analyst": r["analyst"], "date": r["date"],
        "raw_target": r["raw_target"],
        "raw_action": g.get("raw_action", ""),
        "raw_logic": g.get("raw_logic", ""),
        "draft_action": d_action, "parser_action": p_action,
        "draft_status": d_status, "parser_status": p_status,
        "draft_temporal": d_temporal, "parser_temporal": p_temporal,
        "arbiter_result": "",      # 待填: PARSER_CORRECT / DRAFT_CORRECT / BOTH_WRONG / AMBIGUOUS
        "final_action": "", "final_status": "", "final_temporal": "",
        "exclude_from_core_benchmark": "",   # AMBIGUOUS=true（不参与核心基准）
        "review_note": "",
    })

# 排序: 桶优先级 + sample_id
PRIO_ORDER = ["P1_ACTION_OPPOSITE", "P2_STATUS_CONFLICT", "P3_TEMPORAL_CONFLICT",
              "P4_BUY_SUBTYPE", "P5_DRAFT_UNKNOWN_TEMPORAL", "P6_OTHER"]
entries.sort(key=lambda e: (PRIO_ORDER.index(e["priority"]), int(e["sample_id"])))

fields = ["priority", "sample_id", "analyst", "date", "raw_target", "raw_action", "raw_logic",
          "draft_action", "parser_action", "draft_status", "parser_status",
          "draft_temporal", "parser_temporal",
          "arbiter_result", "final_action", "final_status", "final_temporal",
          "exclude_from_core_benchmark", "review_note"]
with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(entries)

print(f"仲裁清单: {len(entries)} 条分歧 → {OUT}")
for b in PRIO_ORDER:
    c = bucket_counts.get(b, 0)
    print(f"  {b}: {c}")
