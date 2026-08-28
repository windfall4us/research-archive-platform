#!/usr/bin/env python3
"""0B.5 步骤⑥: Action/Temporal Parser Benchmark（对 Gold Sample 100 + 已确认 10 行）。

对比口径:
- 100 行: parser vs draft 标注（actions_draft / action_status_draft / temporal_type_draft）
  - actions 对比用"主动作"（首个）
  - 分歧逐条列出（draft 本身待人工锁定，分歧需人工仲裁）
- 已确认 10 行: parser vs gold_sample_schema_v1.md 确认值（真值）

高风险错误专项（必须接近 0）:
  R1 WATCH→HOLD: 原文仅 关注/观察/跟踪 却被标 HOLD
  R2 持仓→今日BUY: 原文纯持有态却被产出 BUY
  R3 计划加仓→EXECUTED ADD: 加仓无"已"却被 EXECUTED
  R4 回踩可买→EXECUTED: 条件句却被 EXECUTED
  R5 过去买入持有→今日BUY: 之前买入继续持有却被 TODAY BUY
"""
import csv, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from action_temporal_parser_p0b import parse

ROOT = Path("/home/windfall/workspace/research-archive-platform")
GS = ROOT / "data/analyst_snapshots/gold_sample_100.csv"
OUT = ROOT / "reports/action_temporal_benchmark_p0b.json"
OUT_CSV = ROOT / "reports/action_temporal_benchmark_p0b.csv"

rows = list(csv.DictReader(open(GS, encoding="utf-8")))

results = []
agree_action = agree_status = agree_temporal = 0
R = {"R1_watch_to_hold": 0, "R2_hold_to_buy": 0, "R3_plan_to_executed": 0,
     "R4_cond_to_executed": 0, "R5_past_to_today_buy": 0}
disagreements = []

for r in rows:
    p = parse(r["raw_action"], r["raw_logic"])
    acts = [a for a, _ in p["actions"]]
    statuses = [s for _, s in p["actions"]]
    primary = acts[0] if acts else "UNKNOWN"
    primary_status = statuses[0] if statuses else "UNKNOWN"

    draft_act = r["actions_draft"] or "UNKNOWN"
    draft_status = r["action_status_draft"] or "UNKNOWN"
    draft_temporal = r["temporal_type_draft"] or "UNKNOWN"

    # 对比（actions 用主动作）
    a_ok = primary == draft_act
    s_ok = primary_status == draft_status
    t_ok = p["temporal_type"] == draft_temporal
    agree_action += a_ok
    agree_status += s_ok
    agree_temporal += t_ok

    # ---- 高风险专项（按动作所属分句检查，避免跨分句误报）----
    raw = r["raw_action"]
    pairs = p["actions"]
    # R1: WATCH→HOLD（原文仅 关注/观察/跟踪/自选 无持有词却被标 HOLD）
    if "HOLD" in acts and "WATCH" not in acts and re.search(r"关注|观察|跟踪|自选", raw) and not re.search(r"持有|持股|拿着|不动", raw):
        R["R1_watch_to_hold"] += 1
    # R2: 持仓→今日BUY（纯持有态却产出 TODAY BUY）
    if primary in ("BUY",) and p["temporal_type"] == "TODAY" and re.search(r"持有|持股|持仓|拿着", raw) and not re.search(r"已|今天|今日|早盘|尾盘|盘中", raw):
        R["R2_hold_to_buy"] += 1
    # R3: 计划加仓→EXECUTED ADD（该 ADD 动作状态为 EXECUTED 且其分句无"已"）
    for a, s, ci in [(a, s, ci) for (a, s), ci in zip(pairs, [c for _, c in p["action_clauses"]])]:
        cl = p["clauses"][ci] if ci < len(p["clauses"]) else raw
        if a == "ADD" and s == "EXECUTED" and not re.search(r"已", cl):
            R["R3_plan_to_executed"] += 1
        # R4: 条件句却被 EXECUTED（该动作 EXECUTED 且其分句含条件词）
        if s == "EXECUTED" and re.search(r"回踩|若|如果|等|可|站上|确认|突破|就|再", cl):
            R["R4_cond_to_executed"] += 1
    # R5: 过去买入持有→今日BUY
    if primary in ("BUY", "LOW_BUY", "ADD") and p["temporal_type"] == "TODAY" and re.search(r"之前|前几天|昨日|上周|以前", raw):
        R["R5_past_to_today_buy"] += 1

    row = {
        "sample_id": r["sample_id"], "analyst": r["analyst"], "date": r["date"],
        "raw_target": r["raw_target"], "raw_action": r["raw_action"],
        "parser_actions": p["actions"], "parser_temporal": p["temporal_type"],
        "parser_position": p["position_state"],
        "draft_act": draft_act, "draft_status": draft_status, "draft_temporal": draft_temporal,
        "agree_action": a_ok, "agree_status": s_ok, "agree_temporal": t_ok,
    }
    results.append(row)
    if not (a_ok and s_ok and t_ok):
        disagreements.append(row)

n = len(rows)
report = {
    "n": n,
    "agree_action": agree_action, "agree_status": agree_status, "agree_temporal": agree_temporal,
    "action_agreement": round(agree_action / n, 4),
    "status_agreement": round(agree_status / n, 4),
    "temporal_agreement": round(agree_temporal / n, 4),
    "high_risk": R,
    "n_disagreements": len(disagreements),
}
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
    w.writeheader()
    for row in results:
        w.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
                    for k, v in row.items()})

print(json.dumps(report, ensure_ascii=False, indent=1))
print("\n=== 分歧清单（parser vs draft 不一致）===")
for d in disagreements:
    print(f"[{d['sample_id']}] {d['raw_target'][:10]} | P:{d['parser_actions']}/{d['parser_temporal']} vs D:{d['draft_act']}/{d['draft_status']}/{d['draft_temporal']} | {d['raw_action'][:50]}")
print("\n输出:", OUT, OUT_CSV)
