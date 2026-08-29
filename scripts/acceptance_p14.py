#!/usr/bin/env python3
"""P1.4 Revision 持久化验收（7 Gate + 2 审计）。

Gate：
  G1 同一 revision 重跑 0 duplicate   最近两条 revision run：第二条 inserted=0 + hash 一致
  G2 revision_no 连续 100%           每个 logical_record_id 的 revision_no = 1..N 无跳号
  G3 old/new hash 完整 100%          MODIFIED 行 old_hash/new_hash 非空
  G4 changed_fields 可解析 100%      changed_fields_json 均为合法 JSON 数组
  G5 ROLE 不改事件语义 100%          severity=ROLE 的 MODIFIED：old/new payload 的 action/direction/stock/date 全等（仅 role 变）
  G6 SEVERE 可回溯 old/new payload 100%  MODIFIED+SEVERE 行 old_payload/new_payload 非空（ADDED/REMOVED 有对应侧）
  G7 历史事实物理覆盖 0               events/positions 表 hash 与 P1.2/P1.3 验收基线一致（P1.4 只 INSERT revisions）
审计：
  A1 orphan revision = 0             每条 revision.source_record_id 存在于 before 或 after 快照 sections
  A2 revision → source lineage 100%  source_snapshot_id 非空且指向已登记快照

用法: python3 scripts/acceptance_p14.py
"""
import hashlib, json, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
DB = ROOT / "data/analyst_consensus.db"

# P1.2 / P1.3 验收基线 hash（业务表在 P1.4 前最后一次 event/position run 的结果）
BASE_EVENTS_HASH = "478a7c4f712b8bce"      # P1.2 run result_hash（analyst_stock_events）
BASE_POS_HASH = "8826975fa9b8fb14"         # P1.3 run result_hash（analyst_position_snapshots）


def fmt(v):
    return "✅" if v else "❌"


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


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    out = {}

    # G1 幂等重跑
    runs = con.execute(
        "SELECT run_id, inserted_event_count, result_hash, parser_version"
        " FROM ingest_runs WHERE parser_version='p14-diff-v2' ORDER BY run_id DESC LIMIT 2").fetchall()
    g1 = False
    if len(runs) >= 2:
        g1 = (runs[0]["inserted_event_count"] == 0 and runs[0]["result_hash"] == runs[1]["result_hash"])
    out["G1_rerun_0duplicate"] = {"pass": g1,
                                  "detail": f"recent={[{'run_id': r['run_id'], 'inserted': r['inserted_event_count'], 'hash': r['result_hash'][:16]} for r in runs]}"}

    # G2 revision_no 连续
    bad_no = 0
    logicals = con.execute("SELECT DISTINCT logical_record_id FROM record_revisions").fetchall()
    for (logical,) in logicals:
        nos = sorted(r[0] for r in con.execute(
            "SELECT revision_no FROM record_revisions WHERE logical_record_id=?", (logical,)))
        expect = list(range(1, len(nos) + 1))
        if nos != expect:
            bad_no += 1
    g2 = (bad_no == 0)
    out["G2_revision_no_contiguous"] = {"pass": g2, "detail": f"logicals={len(logicals)}, non_contiguous={bad_no}"}

    # G3 old/new hash 完整（MODIFIED）
    mod_rows = con.execute("SELECT old_hash, new_hash FROM record_revisions WHERE change_type='MODIFIED'").fetchall()
    miss_hash = sum(1 for r in mod_rows if not r["old_hash"] or not r["new_hash"])
    g3 = (miss_hash == 0)
    out["G3_old_new_hash"] = {"pass": g3, "detail": f"modified={len(mod_rows)}, missing_hash={miss_hash}"}

    # G4 changed_fields 可解析
    bad_cf = 0
    for (cf,) in con.execute("SELECT changed_fields_json FROM record_revisions"):
        try:
            v = json.loads(cf)
            if not isinstance(v, list):
                bad_cf += 1
        except Exception:
            bad_cf += 1
    g4 = (bad_cf == 0)
    out["G4_changed_fields_parseable"] = {"pass": g4, "detail": f"unparseable={bad_cf}"}

    # G5 ROLE 不改事件语义
    role_rows = con.execute(
        "SELECT old_payload_json, new_payload_json FROM record_revisions WHERE change_type='MODIFIED' AND severity='ROLE'").fetchall()
    semantic_broken = 0
    for r in role_rows:
        old = json.loads(r["old_payload_json"])
        new = json.loads(r["new_payload_json"])
        for k in ("stock", "action", "direction", "date", "logic"):
            if old.get(k) != new.get(k):
                semantic_broken += 1
                break
    g5 = (semantic_broken == 0)
    out["G5_role_keeps_semantics"] = {"pass": g5, "detail": f"role_rows={len(role_rows)}, semantic_broken={semantic_broken}"}

    # G6 SEVERE 可回溯 payload
    severe_mod = con.execute(
        "SELECT old_payload_json, new_payload_json FROM record_revisions WHERE change_type='MODIFIED' AND severity='SEVERE'").fetchall()
    severe_broken = sum(1 for r in severe_mod if not r["old_payload_json"] or not r["new_payload_json"])
    # ADDED/REMOVED 有对应侧 payload
    add_broken = con.execute(
        "SELECT COUNT(*) FROM record_revisions WHERE change_type='ADDED' AND (new_payload_json IS NULL OR new_payload_json='')").fetchone()[0]
    rem_broken = con.execute(
        "SELECT COUNT(*) FROM record_revisions WHERE change_type='REMOVED' AND (old_payload_json IS NULL OR old_payload_json='')").fetchone()[0]
    g6 = (severe_broken == 0 and add_broken == 0 and rem_broken == 0)
    out["G6_severe_payload_replay"] = {"pass": g6,
                                       "detail": f"severe_modified={len(severe_mod)}, broken={severe_broken}; added_payload_missing={add_broken}, removed_payload_missing={rem_broken}"}

    # G7 历史事实物理覆盖 0
    ev_h = events_hash(con)
    po_h = pos_hash(con)
    g7 = (ev_h == BASE_EVENTS_HASH and po_h == BASE_POS_HASH)
    out["G7_no_physical_overwrite"] = {"pass": g7,
                                       "detail": f"events_hash={ev_h} (基线 {BASE_EVENTS_HASH}); positions_hash={po_h} (基线 {BASE_POS_HASH})"}

    # A1 orphan revision
    from diff_analyst_snapshots_v2 import load_sections, logical_key, record_id
    before = load_sections(ROOT / "data/analyst_snapshots/vip0_timeline_20260827.json")
    after = load_sections(ROOT / "data/analyst_snapshots/vip0_timeline_20260828.json")
    known = {record_id(s, logical_key(s)) for s in before} | {record_id(s, logical_key(s)) for s in after}
    all_rids = [r[0] for r in con.execute("SELECT DISTINCT source_record_id FROM record_revisions")]
    orphan = [rid for rid in all_rids if rid not in known]
    out["A1_orphan_revision"] = {"pass": len(orphan) == 0, "detail": f"orphan={len(orphan)}", "items": orphan[:5]}

    # A2 revision → source lineage
    snap_count = con.execute("SELECT COUNT(*) FROM source_snapshots").fetchone()[0]
    null_snap = con.execute(
        "SELECT COUNT(*) FROM record_revisions WHERE source_snapshot_id IS NULL").fetchone()[0]
    dangling = con.execute(
        "SELECT COUNT(*) FROM record_revisions r WHERE NOT EXISTS (SELECT 1 FROM source_snapshots s WHERE s.snapshot_id=r.source_snapshot_id)").fetchone()[0]
    a2 = (null_snap == 0 and dangling == 0)
    out["A2_source_lineage"] = {"pass": a2, "detail": f"snapshots={snap_count}, null_snapshot_id={null_snap}, dangling={dangling}"}

    overall = all(v["pass"] for k, v in out.items() if k != "A1_orphan_revision" or v["pass"])
    # A1/A2 是审计项；gate 只看 G1-G7
    gates_pass = all(v["pass"] for k, v in out.items() if k.startswith("G"))
    out["Gates"] = "PASS" if gates_pass else "FAIL"
    out["Audit"] = "PASS" if (out["A1_orphan_revision"]["pass"] and out["A2_source_lineage"]["pass"]) else "FAIL"
    out["Overall"] = "PASS" if (gates_pass and out["A1_orphan_revision"]["pass"] and out["A2_source_lineage"]["pass"]) else "FAIL"

    report = {k: v for k, v in out.items() if k not in ("Gates", "Audit", "Overall")}
    (ROOT / "reports" / "ingest_p14_acceptance.json").write_text(
        json.dumps({"gates": report, "Gates": out["Gates"], "Audit": out["Audit"], "Overall": out["Overall"]},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    md = ["# P1.4 Revision 持久化验收报告\n"]
    for k, v in out.items():
        if k in ("Gates", "Audit", "Overall"):
            md.append(f"**{k}: {v}**")
        elif isinstance(v, dict) and "pass" in v:
            md.append(f"- {fmt(v['pass'])} **{k}** — {v.get('detail', '')}")
    (ROOT / "reports" / "ingest_p14_acceptance.md").write_text("\n".join(md), encoding="utf-8")

    print(json.dumps({k: (v if not isinstance(v, dict) else {"pass": v.get("pass"), "detail": v.get("detail", "")})
                      for k, v in out.items()}, ensure_ascii=False, indent=1))
    con.close()
    return 0 if out["Overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
