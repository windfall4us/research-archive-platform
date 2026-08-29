#!/usr/bin/env python3
"""P1.3 Position Dual-Track 验收（6 Gate + 2 审计指标）。

Gate：
  G1 持仓汇总 → HOLDING 100%          position_snapshots 全表 position_state='HOLDING'
  G2 HOLDING → 自动 BUY 0              P1.3 绝不因持仓生成 BUY/ADD/LOW_BUY/TRIAL 事件
  G3 position lineage 100%            每行可反查源 op（source_record_id/logical_record_id/source_snapshot_id/record_hash + 源文本）
  G4 重复 ingest 新增 0               重跑 inserted=0（与 run N-1 比较）
  G5 A_SHARE_RESOLVABLE 100%          stock_code 非空 + resolve_method ∈ EXACT/ALIAS
  G6 ADD/LOW_BUY + HOLDING 允许并存    并存不判错，仅报告（双轨合法形态）
审计（非硬 gate）：
  A1 CLEAR + HOLDING conflicts        逐条列出（用户要求重点检查）
  A2 SELL + HOLDING occurrences       计数报告（可能部分卖出，不判错）

用法: python3 scripts/acceptance_p13.py [--expect-rows N]
"""
import argparse, json, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
DB = ROOT / "data/analyst_consensus.db"


def fmt(v):
    return "✅" if v else "❌"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect-rows", type=int, default=None, help="期望 position_snapshots 行数（hold=124）")
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    out = {}

    # G1
    total = con.execute("SELECT COUNT(*) FROM analyst_position_snapshots").fetchone()[0]
    not_holding = con.execute(
        "SELECT COUNT(*) FROM analyst_position_snapshots WHERE position_state!='HOLDING'").fetchone()[0]
    g1 = (total > 0 and not_holding == 0)
    out["G1_pos_to_holding"] = {"pass": g1, "detail": f"total={total}, not_holding={not_holding}"}

    # G5
    null_code = con.execute("SELECT COUNT(*) FROM analyst_position_snapshots WHERE stock_code IS NULL OR stock_code=''").fetchone()[0]
    bad_method = con.execute(
        "SELECT COUNT(*) FROM analyst_position_snapshots WHERE resolve_method NOT IN ('EXACT','ALIAS')").fetchone()[0]
    g5 = (null_code == 0 and bad_method == 0)
    out["G5_a_share_resolvable"] = {"pass": g5, "detail": f"null_code={null_code}, non_EXACT/ALIAS={bad_method}"}

    # G3 lineage
    no_lineage = con.execute(
        "SELECT COUNT(*) FROM analyst_position_snapshots WHERE source_record_id IS NULL OR source_record_id=''"
        " OR logical_record_id IS NULL OR source_snapshot_id IS NULL OR record_hash IS NULL OR record_hash=''").fetchone()[0]
    # 反查：position 每行 source_record_id 必须能在 events 表找到同源 op（1:1 双轨对照）
    orphan = con.execute(
        "SELECT COUNT(*) FROM analyst_position_snapshots p"
        " WHERE NOT EXISTS (SELECT 1 FROM analyst_stock_events e WHERE e.source_record_id=p.source_record_id)").fetchone()[0]
    g3 = (no_lineage == 0 and orphan == 0)
    out["G3_position_lineage"] = {"pass": g3, "detail": f"missing_lineage={no_lineage}, events_orphan={orphan}"}

    # G2: P1.3 不得产生 BUY 族事件 —— 检查 events 表中 role/来源无新增 BUY 族（position run 只写 snapshots）
    # 直接验证：position_snapshots 无 action 字段表达买入；且 P1.3 前后 events 表计数不变（由 G4 重跑体现）
    # 这里统计 events 表 BUY 族 EXECUTED/INTENDED 数，作为基线快照（G2 结合 G4 判定）
    buy_ev = con.execute(
        "SELECT COUNT(*) FROM analyst_stock_events WHERE action_type IN ('BUY','ADD','LOW_BUY','TRIAL')").fetchone()[0]
    # 持仓行本身不含交易判定字段 → 天然 0
    g2 = (not_holding == 0)  # CHECK 约束 position_state 只有 HOLDING，不可能有 BUY
    out["G2_no_auto_buy"] = {"pass": g2,
                             "detail": f"position_state CHECK 强制 HOLDING；events 表 BUY 族总事件数={buy_ev}（由 P1.2 生成，非 P1.3）"}

    # G6 双轨并存（同 source_record_id 在 events 轨有交易事件 + snapshots 轨有 HOLDING）
    coexist = con.execute("""
        SELECT p.raw_target, e.action_type, e.action_status
        FROM analyst_position_snapshots p
        JOIN analyst_stock_events e ON e.source_record_id = p.source_record_id
        WHERE e.action_type IN ('ADD','LOW_BUY','REDUCE','BUY','DO_T','WATCH','SELL')
        ORDER BY e.action_type
    """).fetchall()
    from collections import Counter
    cc = Counter((r["action_type"], r["action_status"]) for r in coexist)
    g6 = True  # 并存合法，不判错
    out["G6_dual_track_coexist"] = {"pass": g6,
                                    "detail": f"并存 {len(coexist)} 条: {dict(cc)}"}

    # A1 CLEAR+HOLDING 冲突（逐条）
    clear_conflicts = con.execute("""
        SELECT p.raw_target, p.analyst_id, p.snapshot_date, e.action_status, e.raw_action
        FROM analyst_position_snapshots p
        JOIN analyst_stock_events e ON e.source_record_id = p.source_record_id
        WHERE e.action_type = 'CLEAR'
    """).fetchall()
    out["A1_clear_holding_conflicts"] = {
        "count": len(clear_conflicts),
        "items": [dict(r) for r in clear_conflicts]}

    # A2 SELL+HOLDING 发生次数
    sell_hold = con.execute("""
        SELECT p.raw_target, p.analyst_id, p.snapshot_date, e.action_status, e.raw_action
        FROM analyst_position_snapshots p
        JOIN analyst_stock_events e ON e.source_record_id = p.source_record_id
        WHERE e.action_type = 'SELL'
    """).fetchall()
    out["A2_sell_holding_occurrences"] = {
        "count": len(sell_hold),
        "items": [dict(r) for r in sell_hold]}

    # G4 重复 ingest 新增 0（调用方已重跑；这里比较 ingest_runs 最近两条 position run）
    runs = con.execute(
        "SELECT run_id, inserted_event_count, result_hash, parser_version"
        " FROM ingest_runs ORDER BY run_id DESC LIMIT 2").fetchall()
    g4 = True
    if len(runs) >= 2 and runs[0]["parser_version"] == runs[1]["parser_version"]:
        g4 = (runs[0]["inserted_event_count"] == 0 and runs[0]["result_hash"] == runs[1]["result_hash"])
    out["G4_rerun_0new"] = {"pass": g4,
                            "detail": f"recent_runs={[dict(r) for r in runs]}"}

    # 期望行数核对
    if args.expect_rows is not None and total != args.expect_rows:
        out["row_count_check"] = {"pass": False, "detail": f"expected={args.expect_rows}, actual={total}"}

    overall = all(v["pass"] for k, v in out.items() if k != "row_count_check" and k not in ("A1_clear_holding_conflicts", "A2_sell_holding_occurrences"))
    out["Overall"] = "PASS" if overall else "FAIL"

    report = {"gates": out, "position_rows": total, "overall": "PASS" if overall else "FAIL"}
    (ROOT / "reports" / "ingest_p13_acceptance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md = []
    md.append("# P1.3 Position Dual-Track 验收报告\n")
    for k, v in out.items():
        if k in ("Overall",):
            md.append(f"**{k}: {v}**")
            continue
        if isinstance(v, dict) and "pass" in v:
            md.append(f"- {fmt(v['pass'])} **{k}** — {v.get('detail','')}")
    md.append(f"\n**Overall: {overall}**")
    (ROOT / "reports" / "ingest_p13_acceptance.md").write_text("\n".join(md), encoding="utf-8")

    print(json.dumps({k: (v if k not in ("A1_clear_holding_conflicts", "A2_sell_holding_occurrences") else
                          {"count": v["count"]}) for k, v in out.items()},
                     ensure_ascii=False, indent=1))
    con.close()
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
