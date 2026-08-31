#!/usr/bin/env python3
"""P1.5: Data Layer Benchmark —— Phase 1 全链路复现 + 准入判定（GO/NO-GO）。

定位（用户 2026-08-29 P1.5 决策）：不再新增业务逻辑，只做聚合验收、可复现检查、GO/NO-GO。

流程：
  1) 输入与版本（快照 / parser / resolver / schema / ingest_runs 基线）
  2) 全链路重跑（p12 events → p13 positions → p14 revisions，幂等）→ G1/G7
  3) 7 个核心 Gate 复现
       G1 重复 ingest   0 duplicate events/positions/revisions
       G2 A股可解析     A_SHARE_RESOLVABLE = 100%
       G3 false executed BUY/SELL 高风险误执行 = 0（parser 用原文复现同判定）
       G4 HOLDING→BUY   0
       G5 revision 可追踪 100%
       G6 source lineage 100%
       G7 重复运行一致   result hash 100% 一致
  4) 5 个辅助审计指标
       A1 events/positions/revisions 当前行数
       A2 OUT_OF_SCOPE/THEME/MARKET/COMPOSITE/UNRESOLVED 分布
       A3 CLEAR+HOLDING / SELL+HOLDING 冲突审计
       A4 ROLE/TEXT/SEVERE revision 分布
       A5 schema_version / parser_version / resolver_version / source snapshots
  5) Data Contract Summary（Phase 1 锁定边界）
  6) 最终判定 GO / NO-GO + Next

已知遗留（本步不改数据，仅报告）：P1.2 的 3 条 COMPOSITE 残留单股事件（天赢居 08-28
  东微半导/瑞芯微、天齐锂业/赣锋锂业、黄河旋风/四方达）→ 建议 Phase 1 冻结后单独评估。

用法: python3 scripts/benchmark_phase1_p15.py
输出: reports/phase1_benchmark_p15.md / .json
"""
import hashlib, json, sqlite3, subprocess, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
DB = ROOT / "data/analyst_consensus.db"

# 审计/验收参考基准快照（自动发现：record_revisions 最新两个 snapshot_date 对应的时间线快照）。
# 冻结阶段后随日期推进自动更新，不改算法语义。无 revision 时回退到 08-28 基线。
def _latest_rev_snapshot_pair():
    try:
        import sqlite3 as _sq
        _c = _sq.connect(DB)
        dates = sorted(r[0] for r in _c.execute(
            "SELECT DISTINCT snapshot_date FROM record_revisions"))
        _c.close()
    except Exception:
        dates = []
    if len(dates) >= 2:
        a, b = dates[-2], dates[-1]
    else:
        a = b = "2026-08-28"
    fmt = lambda d: "".join(d.split("-"))
    return (ROOT / f"data/analyst_snapshots/vip0_timeline_{fmt(a)}.json",
            ROOT / f"data/analyst_snapshots/vip0_timeline_{fmt(b)}.json")


def _latest_snapshot_file():
    """最新时间线快照（用于 A2 分层审计）。"""
    try:
        import sqlite3 as _sq
        _c = _sq.connect(DB)
        dates = sorted(r[0] for r in _c.execute(
            "SELECT DISTINCT snapshot_date FROM source_snapshots"))
        _c.close()
    except Exception:
        dates = []
    d = dates[-1] if dates else "2026-08-28"
    fmt = lambda x: "".join(x.split("-"))
    return ROOT / f"data/analyst_snapshots/vip0_timeline_{fmt(d)}.json"

from action_temporal_parser_v11_p0b import parse as parse_v11
from ingest_consensus_p12 import Resolver, collect_source_records
from ingest_revision_p14 import full_payload  # noqa

# ---------- hash 函数（与各 ingest 一致） ----------
def events_hash(con):
    rows = con.execute(
        "SELECT source_record_id, event_index, action_type, event_category, action_status,"
        " temporal_type, stock_code, stock_name, raw_target, resolve_method"
        " FROM analyst_stock_events ORDER BY source_record_id, event_index").fetchall()
    return hashlib.sha256("\n".join("|".join(str(x) for x in r) for r in rows).encode()).hexdigest()[:16]


def pos_hash(con):
    rows = con.execute(
        "SELECT analyst_id, snapshot_date, stock_code, raw_target, source_record_id,"
        " position_state, resolve_method FROM analyst_position_snapshots"
        " ORDER BY analyst_id, snapshot_date, source_record_id").fetchall()
    return hashlib.sha256("\n".join("|".join(str(x) for x in r) for r in rows).encode()).hexdigest()[:16]


def rev_hash(con):
    rows = con.execute(
        "SELECT source_record_id, logical_record_id, snapshot_date, revision_no, change_type,"
        " severity, old_hash, new_hash, changed_fields_json"
        " FROM record_revisions ORDER BY source_record_id, snapshot_date").fetchall()
    return hashlib.sha256("\n".join("|".join(str(x) for x in r) for r in rows).encode()).hexdigest()[:16]


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    out = {}

    # ---------- 1) 输入与版本 ----------
    ver = {
        "schema_version": con.execute("PRAGMA user_version").fetchone()[0],
        "source_snapshots": [dict(r) for r in con.execute(
            "SELECT snapshot_id, source, snapshot_date, record_count FROM source_snapshots ORDER BY snapshot_date")],
        "ingest_runs_count": con.execute("SELECT COUNT(*) FROM ingest_runs").fetchone()[0],
        "parser_versions": [dict(r) for r in con.execute(
            "SELECT parser_version, COUNT(*) c, MAX(run_id) latest FROM ingest_runs GROUP BY parser_version")],
    }
    out["input_and_versions"] = ver

    # ---------- 2) 全链路重跑（幂等；subprocess 独立进程，保持各 ingest 自身事务/报告逻辑） ----------
    scripts = ["ingest_consensus_p12.py", "ingest_position_p13.py", "ingest_revision_p14.py"]
    pre_hashes = {"events": events_hash(con), "positions": pos_hash(con), "revisions": rev_hash(con)}
    pre_runs = {r["parser_version"]: r["latest"] for r in ver["parser_versions"]}
    rerun = []
    all_ok = True
    for sc in scripts:
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / sc)], capture_output=True, text=True, cwd=ROOT)
        # 最新 run 是否 inserted=0
        last = con.execute(
            "SELECT run_id, inserted_event_count, skipped_existing_count, result_hash, error_count"
            " FROM ingest_runs ORDER BY run_id DESC LIMIT 1").fetchone()
        rerun.append({"script": sc, "exit": p.returncode, "run_id": last["run_id"],
                      "inserted": last["inserted_event_count"], "skipped": last["skipped_existing_count"],
                      "hash": last["result_hash"][:16] if last["result_hash"] else None,
                      "error_count": last["error_count"]})
        if last["inserted_event_count"] != 0 or last["error_count"] != 0:
            all_ok = False
    post_hashes = {"events": events_hash(con), "positions": pos_hash(con), "revisions": rev_hash(con)}
    out["rerun"] = rerun

    # G1 重复 ingest = 0（三个 ingest 重跑 inserted 均 0）
    g1 = all_ok and all(r["inserted"] == 0 for r in rerun)
    out["G1_duplicate_ingest"] = {"pass": g1, "detail": rerun}

    # G7 重复运行一致（重跑前后各表 hash 一致）
    g7 = all(post_hashes[k] == pre_hashes[k] for k in pre_hashes)
    out["G7_repeat_run_consistent"] = {"pass": g7,
                                       "detail": {k: {"pre": pre_hashes[k], "post": post_hashes[k]} for k in pre_hashes}}

    # ---------- 3) 核心 Gate 全库视角 ----------
    # G2 A股可解析 100%
    ev_total = con.execute("SELECT COUNT(*) FROM analyst_stock_events").fetchone()[0]
    ev_res = con.execute("SELECT resolve_method, COUNT(*) FROM analyst_stock_events GROUP BY resolve_method").fetchall()
    ev_ok = sum(r["COUNT(*)"] for r in ev_res if r["resolve_method"] in ("EXACT", "ALIAS"))
    g2 = (ev_total > 0 and ev_ok == ev_total)
    out["G2_a_share_resolvable"] = {"pass": g2, "detail": f"total={ev_total}, resolvable={ev_ok}, by={[tuple(r) for r in ev_res]}"}

    # G3 false executed：库中 BUY/SELL 族 EXECUTED 事件，parser 用完整原文必须复现同判定
    risk_rows = con.execute("""
        SELECT source_record_id, action_type, action_status, raw_target, raw_action, raw_logic
        FROM analyst_stock_events
        WHERE action_type IN ('BUY','ADD','LOW_BUY','TRIAL','REDUCE','SELL','CLEAR','STOP_LOSS')
          AND action_status='EXECUTED'""").fetchall()
    false_exec = []
    for r in risk_rows:
        pr = parse_v11(r["raw_action"] or "", r["raw_logic"] or "")
        reproduced = any(e.get("action") == r["action_type"] and e.get("action_status") == "EXECUTED"
                         for e in pr["events"])
        if not reproduced:
            false_exec.append({"source_record_id": r["source_record_id"], "action": r["action_type"],
                               "raw_target": r["raw_target"]})
    g3 = (len(false_exec) == 0)
    out["G3_false_executed"] = {"pass": g3,
                                "detail": f"risk_executed={len(risk_rows)} (BUY族+SELL族), non_reproducible={len(false_exec)}",
                                "items": false_exec[:10]}

    # G4 HOLDING→BUY = 0
    pos_not_holding = con.execute("SELECT COUNT(*) FROM analyst_position_snapshots WHERE position_state!='HOLDING'").fetchone()[0]
    pos_buy_like = con.execute("SELECT COUNT(*) FROM analyst_position_snapshots WHERE position_state IN ('BUY','ADD','LOW_BUY','TRIAL')").fetchone()[0]
    # 双轨：position 来源 op 在 events 轨不允许被 P1.3 生成 BUY 族 EXECUTED（P1.3 只写 snapshots）
    g4 = (pos_not_holding == 0 and pos_buy_like == 0)
    out["G4_holding_to_buy"] = {"pass": g4, "detail": f"position_snapshots not_holding={pos_not_holding}, buy_like={pos_buy_like}"}

    # G5 revision 可追踪 100%（每条能在 before/after 快照反查 + revision_no 连续）
    # 2026-08-31 修正（用户批准）：排除 change_type='REMOVED' 的 rid——REMOVED 是时间线滚动清除的
    #   合法审计证据（记录已不存在于任何当前快照），不应要求其在最新快照对中可反查。
    #   orphan 判定只针对仍"存活"（非 REMOVED）的 revision rid。
    from diff_analyst_snapshots_v2 import load_sections, logical_key, record_id as _rid
    _bp, _ap = _latest_rev_snapshot_pair()
    before = load_sections(_bp)
    after = load_sections(_ap)
    known = {_rid(s, logical_key(s)) for s in before} | {_rid(s, logical_key(s)) for s in after}
    removed_rids = {r[0] for r in con.execute(
        "SELECT DISTINCT source_record_id FROM record_revisions WHERE change_type='REMOVED'")}
    rev_rids = [r[0] for r in con.execute("SELECT DISTINCT source_record_id FROM record_revisions")]
    rev_rids = [rid for rid in rev_rids if rid not in removed_rids]
    orphan = [rid for rid in rev_rids if rid not in known]
    # revision_no 连续
    bad_no = 0
    for (logical,) in con.execute("SELECT DISTINCT logical_record_id FROM record_revisions"):
        nos = sorted(r[0] for r in con.execute(
            "SELECT revision_no FROM record_revisions WHERE logical_record_id=?", (logical,)))
        if nos != list(range(1, len(nos) + 1)):
            bad_no += 1
    g5 = (len(orphan) == 0 and bad_no == 0)
    out["G5_revision_traceable"] = {"pass": g5, "detail": f"revisions={len(rev_rids)}, orphan={len(orphan)}, non_contiguous_logicals={bad_no}"}

    # G6 source lineage 100%（events/positions/revisions 全 source_snapshot_id 非空且有效）
    lineage_bad = 0
    for tbl in ("analyst_stock_events", "analyst_position_snapshots", "record_revisions"):
        null_snap = con.execute(f"SELECT COUNT(*) FROM {tbl} WHERE source_snapshot_id IS NULL").fetchone()[0]
        dangling = con.execute(
            f"SELECT COUNT(*) FROM {tbl} r WHERE NOT EXISTS (SELECT 1 FROM source_snapshots s WHERE s.snapshot_id=r.source_snapshot_id)").fetchone()[0]
        lineage_bad += null_snap + dangling
    g6 = (lineage_bad == 0)
    out["G6_source_lineage"] = {"pass": g6, "detail": f"bad_lineage={lineage_bad} (events+positions+revisions)"}

    # ---------- 4) 辅助审计 ----------
    a1 = {
        "analyst_stock_events": con.execute("SELECT COUNT(*) FROM analyst_stock_events").fetchone()[0],
        "analyst_position_snapshots": con.execute("SELECT COUNT(*) FROM analyst_position_snapshots").fetchone()[0],
        "record_revisions": con.execute("SELECT COUNT(*) FROM record_revisions").fetchone()[0],
        "analyst_profiles": con.execute("SELECT COUNT(*) FROM analyst_profiles").fetchone()[0],
        "ingest_runs": con.execute("SELECT COUNT(*) FROM ingest_runs").fetchone()[0],
    }
    out["A1_row_counts"] = a1

    # A2 分层分布（最新快照 resolver 分层，与 P1.2 口径一致）
    d = json.loads(_latest_snapshot_file().read_bytes().decode("utf-8"))
    resolver = Resolver()
    bucket = Counter()
    for r in collect_source_records(d):
        rs = resolver.resolve(r["raw_target"])
        bucket[rs["entity_type"]] += 1
    out["A2_entity_bucket"] = dict(bucket)

    # A3 冲突审计
    clear_hold = con.execute("""
        SELECT COUNT(*) FROM analyst_position_snapshots p
        JOIN analyst_stock_events e ON e.source_record_id = p.source_record_id
        WHERE e.action_type='CLEAR'""").fetchone()[0]
    sell_hold = con.execute("""
        SELECT COUNT(*) FROM analyst_position_snapshots p
        JOIN analyst_stock_events e ON e.source_record_id = p.source_record_id
        WHERE e.action_type='SELL'""").fetchone()[0]
    out["A3_conflict_audit"] = {"CLEAR+HOLDING": clear_hold, "SELL+HOLDING": sell_hold}

    # A4 revision severity 分布
    out["A4_revision_severity"] = {k: v for k, v in con.execute(
        "SELECT severity, COUNT(*) FROM record_revisions GROUP BY severity").fetchall()}

    # A5 版本（并入 input_and_versions；补充 parser/resolver 常量）
    out["A5_versions"] = {
        "schema_version": con.execute("PRAGMA user_version").fetchone()[0],
        "parser": "v1.1", "resolver": "exact-alias-v1",
        "snapshots": [r["snapshot_date"] for r in ver["source_snapshots"]],
    }

    # ---------- 5) Data Contract Summary ----------
    contract = {
        "analyst_stock_events": "完整事件事实层，存全部 11 类动作（TRADE/OBSERVATION/STATE/COMPOSITE_TACTICAL/UNKNOWN）",
        "analyst_position_snapshots": "日终确认持仓观察值，position_state 仅 HOLDING（CHECK 强制）",
        "position_snapshot_derives_buy": False,
        "event_position_dual_track": "允许并存（ADD/LOW_BUY/REDUCE/SELL + HOLDING 合法；CLEAR+HOLDING 需审计）",
        "composite_theme_market_oos": "不强拆为 A 股个股事件；仅 A_SHARE 落 events/positions",
        "revision": "append-only，不物理覆盖历史（old_payload/new_payload 完整回放）",
        "security_master": "独立 DB（security_master.db），只读引用，不复制",
        "parser_baseline": "v1.1 LOCKED；Q/R/S gap 走独立版本升级，不在 Phase 2 内修改",
    }
    out["data_contract"] = contract

    # ---------- 6) 最终判定 ----------
    gates = {k: v for k, v in out.items() if k.startswith("G")}
    gate_pass = all(v["pass"] for v in gates.values())
    overall = "GO" if gate_pass else "NO-GO"
    out["Overall"] = overall
    out["GateSummary"] = {k: ("✅" if v["pass"] else "❌") for k, v in gates.items()}

    (ROOT / "reports" / "phase1_benchmark_p15.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # Markdown 报告
    md = ["# Phase 1 Data Layer Benchmark（P1.5）\n",
          "## 1. 输入与版本",
          f"- schema_version: {ver['schema_version']}",
          f"- source_snapshots: {[r['snapshot_date'] for r in ver['source_snapshots']]}",
          f"- ingest_runs: {ver['ingest_runs_count']} 条；parser 版本: {ver['parser_versions']}",
          f"- 重跑链路: {', '.join(sc for sc in scripts)}\n",
          "## 2. 全链路重跑（幂等）", "| script | run_id | inserted | skipped | hash | error |", "|---|---|---|---|---|---|"]
    for r in rerun:
        md.append(f"| {r['script']} | {r['run_id']} | {r['inserted']} | {r['skipped']} | {r['hash']} | {r['error_count']} |")
    md += ["\n## 3. 7 个核心 Gate", "", "| Gate | 判定 | 明细 |", "|---|---|---|"]
    gate_keys = ["G1_duplicate_ingest", "G2_a_share_resolvable", "G3_false_executed",
                 "G4_holding_to_buy", "G5_revision_traceable", "G6_source_lineage",
                 "G7_repeat_run_consistent"]
    for k in gate_keys:
        v = out[k]
        md.append(f"| {k} | {'✅' if v['pass'] else '❌'} | {v.get('detail','')} |")
    md += ["\n## 4. 辅助审计指标",
           f"- A1 行数: {a1}",
           f"- A2 分层: {dict(bucket)}",
           f"- A3 冲突: {out['A3_conflict_audit']}",
           f"- A4 revision severity: {out['A4_revision_severity']}",
           f"- A5 版本: {out['A5_versions']}",
           "\n## 5. Data Contract Summary（Phase 1 锁定边界）", ""]
    for k, v in contract.items():
        md.append(f"- **{k}**: {v}")
    md += ["\n## 6. 最终判定", "",
           f"**Overall: {'GO' if gate_pass else 'NO-GO'}**",
           f"Gate 明细: {out['GateSummary']}",
           "\n> 已知遗留：P1.2 的 3 条 COMPOSITE 残留单股事件（天赢居 08-28 多标的）建议 Phase 1 冻结后单独评估，不混入本 benchmark。",
           "\n**Next: Phase 2 — Market Direction + Theme Heat**" if gate_pass else "\n**Next: 修复失败 Gate 后重跑 P1.5**"]
    (ROOT / "reports" / "phase1_benchmark_p15.md").write_text("\n".join(md), encoding="utf-8")

    print("=== Phase 1 Data Layer Benchmark ===")
    print(f"rerun: {[(r['script'], r['inserted']) for r in rerun]}")
    print(f"Gates: {out['GateSummary']}")
    print(f"Overall: {overall}")
    print("报告: reports/phase1_benchmark_p15.md | .json")
    con.close()
    return 0 if gate_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
