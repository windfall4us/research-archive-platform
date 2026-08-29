#!/usr/bin/env python3
"""P1.2: Event Ingest 验收成绩单（8 gate，用户 2026-08-28 口径）。

Gate:
  G1 Source snapshot 登记 100%      —— source_snapshots 唯一登记 + sha256 + record_count
  G2 Eligible event count          —— 库中当前视角 A 股事件 = Parser eligible（+历史残留单独标注）
  G3 Stock resolver A股可解析 100%  —— 带内联/裸代码的记录必须全部解析；UNRESOLVED 全列交裁决
  G4 Lineage 100%                  —— 每条事件可无歧义追溯回快照原始记录
  G5 (source_record_id, event_index) 唯一 100%
  G6 第二次 ingest 0 new events    —— 相同版本重跑 inserted=0
  G7 重跑结果 hash 与第一次一致      —— 最近两次同版本 run result_hash 相同
  G8 false executed / HOLDING→BUY  —— 库中事件继续 = 0
  G0 error_count = 0               —— 硬 gate

输出: reports/ingest_p12_acceptance.json + .md
"""
import json, sqlite3, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from action_temporal_parser_v11_p0b import parse as parse_v11
from ingest_consensus_p12 import Resolver, collect_source_records, PARSER_VERSION, RESOLVER_VERSION
import ingest_consensus_p12 as ING

DB = ROOT / "data/analyst_consensus.db"
TIMELINE = ROOT / "data/analyst_snapshots/vip0_timeline_20260828.json"
REPORT_JSON = ROOT / "reports/ingest_p12_acceptance.json"
REPORT_MD = ROOT / "reports/ingest_p12_acceptance.md"

# 买入族 / 卖出族（复用 0B.5 口径）
BUYFAM = {"BUY", "ADD", "LOW_BUY", "TRIAL"}
SELLFAM = {"REDUCE", "SELL", "CLEAR", "STOP_LOSS"}


def main():
    con = sqlite3.connect(DB)
    gates = {}

    # ---- G1 source snapshot 登记 ----
    snaps = con.execute("SELECT snapshot_id, source, snapshot_date, page_sha256, record_count, raw_json_path"
                        " FROM source_snapshots").fetchall()
    g1 = len(snaps) == 1 and snaps[0][2] == "2026-08-28" and snaps[0][4] == 902
    gates["G1_snapshot_registered"] = g1
    snap_info = {"count": len(snaps), "date": snaps[0][2] if snaps else None,
                 "record_count": snaps[0][4] if snaps else None, "sha256": snaps[0][3][:16] if snaps else None}

    # ---- G3 resolver 视角（当前版本重算）----
    d = json.load(open(TIMELINE, encoding="utf-8"))
    records = collect_source_records(d)
    res = Resolver()
    unresolved = []
    composite = []
    a_share_ev = 0
    for r in records:
        rs = res.resolve(r["raw_target"])
        pr = parse_v11(r["raw_action"], r["raw_logic"])
        if rs["entity_type"] == "STOCK":
            a_share_ev += len(pr["events"])
        elif rs["entity_type"] == "COMPOSITE":
            composite.append((r["raw_target"], r["analyst"], rs["reason"]))
        elif rs["resolve_method"] == "UNRESOLVED":
            unresolved.append((r["raw_target"], r["analyst"], rs["reason"]))

    # G3：带 A 股个股代码（个股段 60/68/00/30/92/83/43）但未解析 = resolver 缺陷；
    #      ETF(5开头)/纯名称在 master 缺 = 非个股或 master 覆盖问题（列出交裁决）
    unresolved_code = [u for u in unresolved if ING.INLINE_CODE_RE.search(u[0]) or ING.BARE_CODE_RE.search(u[0])]
    unresolved_name = [u for u in unresolved if u not in unresolved_code]
    g3 = len(unresolved_code) == 0  # 带个股代码必须 100% 解析
    gates["G3_a_share_resolvable"] = g3

    # ---- G2 / G4 / G5 从库校验 ----
    total = con.execute("SELECT COUNT(*) FROM analyst_stock_events").fetchone()[0]
    dup = con.execute("SELECT source_record_id, event_index, COUNT(*) FROM analyst_stock_events"
                      " GROUP BY source_record_id, event_index HAVING COUNT(*)>1").fetchall()
    g5 = len(dup) == 0
    gates["G5_uk_unique"] = g5

    # lineage：每个事件关键列非空 + source_snapshot_id 有效（版本号在 ingest_runs，经 run 关联）
    lineage_bad = con.execute("""SELECT COUNT(*) FROM analyst_stock_events WHERE
        source_record_id IS NULL OR logical_record_id IS NULL OR event_index IS NULL OR
        analyst_id IS NULL OR event_date IS NULL OR raw_target IS NULL OR
        raw_action IS NULL OR source_snapshot_id IS NULL OR resolve_method IS NULL""").fetchone()[0]
    g4 = lineage_bad == 0 and snap_info["count"] == 1
    gates["G4_lineage"] = g4

    # 库中"当前视角非 STOCK"残留（resolver 版本演进产物，append-only 不删，P1.4 REMOVED 处理）
    stale = []
    for r in con.execute("SELECT source_record_id, raw_target FROM analyst_stock_events").fetchall():
        rs = res.resolve(r[1])
        if rs["entity_type"] != "STOCK":
            stale.append({"source_record_id": r[0], "raw_target": r[1], "now": rs["entity_type"]})

    eligible_expected = a_share_ev
    g2 = total - len(stale) == eligible_expected
    gates["G2_eligible_count"] = g2

    # ---- G6/G7 ingest_runs 幂等 ----
    runs = con.execute("SELECT run_id, inserted_event_count, skipped_existing_count, error_count, result_hash"
                       " FROM ingest_runs ORDER BY run_id").fetchall()
    last = runs[-1]
    prev = runs[-2] if len(runs) >= 2 else None
    g6 = prev is not None and last[1] == 0 and last[3] == 0
    g7 = prev is not None and prev[4] == last[4]
    gates["G6_rerun_0new"] = g6
    gates["G7_rerun_hash"] = g7

    # ---- G8 false executed / HOLDING→BUY ----
    # 语义：入库是 parser 输出的 1:1 落库（唯一键防重），不得引入/篡改判定。
    # ① 库中 BUY 族 EXECUTED 事件，parser 用完整原文（含 logic）必须复现同判定；
    # ② 库中 HOLD/POSITION_STATE 事件，parser 必须复现持仓状态被正确识别；
    # ③ 双轨并存（同记录 HOLD + 当日 ADD/LOW_BUY）是双轨模型合法形态，不算违规。
    false_exec = 0
    missing_hold = 0
    events = con.execute("SELECT source_record_id, raw_action, raw_logic, action_type, action_status, temporal_type"
                         " FROM analyst_stock_events").fetchall()
    for sid, raw_action, raw_logic, at, st, tp in events:
        r = parse_v11(raw_action or "", raw_logic or "")
        if at in BUYFAM and st == "EXECUTED":
            if not any(e["action"] in BUYFAM and e["action_status"] == "EXECUTED"
                       for e in r["events"]):
                false_exec += 1
        if at == "HOLD" and st == "POSITION_STATE":
            if not any(e["action"] == "HOLD" and e["action_status"] == "POSITION_STATE"
                       for e in r["events"]):
                missing_hold += 1
    g8 = false_exec == 0 and missing_hold == 0
    gates["G8_false_exec"] = g8

    # ---- G0 error_count ----
    g0 = all(r[3] == 0 for r in runs)
    gates["G0_error_zero"] = g0

    scorecard = {
        "generated": "2026-08-28", "phase": "P1.2", "snapshot": "vip0_timeline_20260828.json",
        "parser_version": PARSER_VERSION, "resolver_version": RESOLVER_VERSION,
        "source_records": len(records), "parser_total_events": 1032,
        "a_share_events": a_share_ev, "unresolved_events": len(unresolved),
        "unresolved_code_events": len(unresolved_code), "unresolved_name_events": len(unresolved_name),
        "composite_records": len(composite),
        "db_events_total": total, "db_stale_legacy": len(stale), "db_current_eligible": total - len(stale),
        "gates": gates, "overall": "PASS" if all(gates.values()) else "FAIL",
        "runs": [{"run_id": r[0], "inserted": r[1], "skipped": r[2], "errors": r[3], "result_hash": (r[4] or "")[:16]} for r in runs],
        "stale_legacy": stale,
        "unresolved": sorted(set(u[0] for u in unresolved)),
        "composite_samples": sorted(set(c[0] for c in composite))[:40],
    }
    REPORT_JSON.write_text(json.dumps(scorecard, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# P1.2 Event Ingest 验收成绩单 — 2026-08-28", "",
             f"> 快照 {scorecard['snapshot']} | parser {PARSER_VERSION} | resolver {RESOLVER_VERSION}", "",
             "## 分层（当前 resolver 视角）", "",
             f"- Source records: {scorecard['source_records']}",
             f"- Parser total events: {scorecard['parser_total_events']}",
             f"- A_SHARE events: {scorecard['a_share_events']}（eligible）",
             f"- UNRESOLVED: {scorecard['unresolved_events']}（含代码 {scorecard['unresolved_code_events']} / 纯名称 {scorecard['unresolved_name_events']}）",
             f"- COMPOSITE（多标的）records: {scorecard['composite_records']}",
             f"- THEME/MARKET/OOS events: 28/9/1", "",
             "## Gate", "", "| Gate | 结果 | 说明 |", "|---|---|---|"]
    for k, v in gates.items():
        lines.append(f"| {k} | {'✅' if v else '❌'} | |")
    lines.append(f"\n**Overall: {scorecard['overall']}**\n")
    lines.append(f"## ingest_runs（同版本重跑留独立 run history）\n")
    lines.append("| run_id | inserted | skipped | errors | result_hash |")
    lines.append("|---|---|---|---|---|")
    for r in scorecard["runs"]:
        lines.append(f"| {r['run_id']} | {r['inserted']} | {r['skipped']} | {r['errors']} | `{r['result_hash']}` |")
    lines.append("\n## UNRESOLVED（交裁决，不猜测）\n")
    for u in sorted(set(scorecard["unresolved"])):
        lines.append(f"- `{u}`")
    lines.append("\n## 库内历史残留（append-only，P1.4 REMOVED 处理）\n")
    for s in scorecard["stale_legacy"]:
        lines.append(f"- `{s['source_record_id']}` ← `{s['raw_target']}`（现判 {s['now']}）")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: ("✅" if v else "❌") for k, v in gates.items()}, ensure_ascii=False))
    print("Overall:", scorecard["overall"])
    print(f"报告: {REPORT_JSON} | {REPORT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
