#!/usr/bin/env python3
"""P1.4: Revision 持久化 —— 跨天快照 Diff → record_revisions（immutable history）。

设计（用户 2026-08-29 P1.4 决策）：
- 原则：Revision 只记录"同一 logical_record 的历史版本变化"，绝不回写覆盖旧事实。
  record_revisions 只 INSERT；P1.4 不触碰业务表（events/positions），历史事实物理覆盖 = 0。
- 数据流：Diff v2（复用 diff_analyst_snapshots_v2 的 logical_key / record_id / fingerprint / severity 判定）
  → logical_record 对齐 → ROLE/TEXT/SEVERE 分类 → append record_revisions → 重跑幂等验收。
- change_type：ADDED / REMOVED / MODIFIED（MODIFIED 内部分 ROLE|TEXT|SEVERE，0B.6 分级）
  - ROLE（position_summary↔daily_action 角色翻转）= INFO 级，不污染核心内容变更统计
    （核心报表单列 role_changes / text_changes / severe_changes）
- old_payload_json / new_payload_json：完整 raw_fields+role（schema v3），可回放"当时改了什么"
- revision_no：按 logical_record_id 递增（1,2,3…，不按 snapshot 全局编号）
- 幂等：INSERT ... ON CONFLICT (source_record_id, snapshot_date) DO NOTHING（禁 REPLACE）
- 不修 parser：v1.1 LOCKED；P1.3 Q/R/S gap 记在 parser_gap_backlog.md，Revision 层不重新解释语义

用法: python3 scripts/ingest_revision_p14.py [--before .../vip0_timeline_20260827.json] [--after .../vip0_timeline_20260828.json]
可重复运行（幂等）；重跑 0 new + result_hash 不变 + ingest_runs 新增一条 run。
"""
import argparse, hashlib, json, sqlite3, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from diff_analyst_snapshots_v2 import load_sections, logical_key, record_id, fingerprint, SEVERE

DB = ROOT / "data/analyst_consensus.db"
PARSER_VERSION = "p14-diff-v2"     # revision diff 版本标识
RESOLVER_VERSION = "p14-diff-v2"
SCHEMA_VERSION = "3"
BEIJING_TZ = timezone(timedelta(hours=8))
now_iso = lambda: datetime.now(BEIJING_TZ).strftime("%Y-%m-%dT%H:%M:%S%z")

# section_type → 受影响事实表
TABLE_BY_ROLE = {"daily_action": "analyst_stock_events", "position_summary": "analyst_stock_events",
                 "analysis_item": "analyst_daily_views"}


def full_payload(s):
    """完整 payload = raw_fields + role（可回放"当时改了什么"）。"""
    p = dict(s.get("raw_fields", {}))
    p["role"] = s.get("section_type", "")
    return p


def build_diff(a_sections, b_sections):
    """→ list of revision dict（UNCHANGED 不产出）。与 0B.6 判定一致，但带完整 payload。"""
    a = {record_id(s, logical_key(s)): s for s in a_sections}
    b = {record_id(s, logical_key(s)): s for s in b_sections}
    revs = []
    for rid, sa in a.items():
        if rid not in b:
            revs.append({
                "record_id": rid, "logical_record_id": logical_key(sa),
                "change_type": "REMOVED", "severity": "SEVERE",
                "old_hash": fingerprint(sa), "new_hash": None,
                "old_payload": full_payload(sa), "new_payload": None,
                "changed_fields": list(sa["raw_fields"].keys()),
                "role": sa["section_type"],
            })
            continue
        sb = b[rid]
        fa, fb = fingerprint(sa), fingerprint(sb)
        role_a, role_b = sa["section_type"], sb["section_type"]
        role_changed = role_a != role_b
        if fa == fb and not role_changed:
            continue  # UNCHANGED，不落 revision
        changed = [k for k in sa["raw_fields"] if sa["raw_fields"].get(k) != sb["raw_fields"].get(k)]
        if role_changed:
            changed.append("role")
        if SEVERE & set(changed):
            severity = "SEVERE"
        elif [k for k in changed if k != "role"]:
            severity = "TEXT"
        else:
            severity = "ROLE"
        revs.append({
            "record_id": rid, "logical_record_id": logical_key(sa),
            "change_type": "MODIFIED", "severity": severity,
            "old_hash": fa, "new_hash": fb,
            "old_payload": full_payload(sa), "new_payload": full_payload(sb),
            "changed_fields": changed, "role": sb["section_type"],
        })
    for rid, sb in b.items():
        if rid not in a:
            revs.append({
                "record_id": rid, "logical_record_id": logical_key(sb),
                "change_type": "ADDED", "severity": "SEVERE",
                "old_hash": None, "new_hash": fingerprint(sb),
                "old_payload": None, "new_payload": full_payload(sb),
                "changed_fields": list(sb["raw_fields"].keys()),
                "role": sb["section_type"],
            })
    return revs


def revision_hash_of(con):
    """record_revisions 全表确定性 hash（幂等重跑一致性 gate）。"""
    rows = con.execute(
        "SELECT source_record_id, logical_record_id, snapshot_date, revision_no, change_type,"
        " severity, old_hash, new_hash, changed_fields_json"
        " FROM record_revisions ORDER BY source_record_id, snapshot_date").fetchall()
    payload = "\n".join("|".join(str(x) for x in r) for r in rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", type=Path,
                    default=ROOT / "data/analyst_snapshots/vip0_timeline_20260827.json")
    ap.add_argument("--after", type=Path,
                    default=ROOT / "data/analyst_snapshots/vip0_timeline_20260828.json")
    args = ap.parse_args()
    if not args.before.exists() or not args.after.exists():
        print(f"快照缺失: before={args.before} after={args.after}")
        return 1

    now = now_iso()
    b_sections = load_sections(args.before)
    a_sections = load_sections(args.after)
    before_date = max(s["date"] for s in b_sections)
    after_date = max(s["date"] for s in a_sections)

    revs = build_diff(b_sections, a_sections)
    stats: dict = {"before_records": len(b_sections), "after_records": len(a_sections),
             "added": 0, "removed": 0, "modified": 0, "role": 0, "text": 0, "severe": 0,
             "inserted": 0, "skipped_existing": 0, "error_count": 0}
    for rv in revs:
        if rv["change_type"] == "ADDED": stats["added"] += 1
        elif rv["change_type"] == "REMOVED": stats["removed"] += 1
        else:
            stats["modified"] += 1
            stats[rv["severity"].lower()] += 1

    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")
    errs = []
    try:
        con.execute("BEGIN")
        # 登记 before 快照（幂等；P1.2 只登记过 after/08-28）
        raw_b = args.before.read_bytes()
        con.execute(
            "INSERT INTO source_snapshots (source, snapshot_date, captured_at, page_generated_at, page_sha256, raw_json_path, record_count, created_at, updated_at)"
            " VALUES ('vip0', ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (source, snapshot_date) DO NOTHING",
            (before_date, now, None, hashlib.sha256(raw_b).hexdigest(), str(args.before), len(b_sections), now, now))
        raw_a = args.after.read_bytes()
        con.execute(
            "INSERT INTO source_snapshots (source, snapshot_date, captured_at, page_generated_at, page_sha256, raw_json_path, record_count, created_at, updated_at)"
            " VALUES ('vip0', ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (source, snapshot_date) DO NOTHING",
            (after_date, now, None, hashlib.sha256(raw_a).hexdigest(), str(args.after), len(a_sections), now, now))
        snap_b = con.execute("SELECT snapshot_id FROM source_snapshots WHERE source='vip0' AND snapshot_date=?",
                             (before_date,)).fetchone()[0]
        snap_a = con.execute("SELECT snapshot_id FROM source_snapshots WHERE source='vip0' AND snapshot_date=?",
                             (after_date,)).fetchone()[0]

        # revision_no 按 logical_record_id 递增：预取当前各 logical 最大 revision_no
        max_no = {}
        for r in con.execute("SELECT logical_record_id, MAX(revision_no) FROM record_revisions GROUP BY logical_record_id"):
            max_no[r[0]] = r[1]

        inserted = skipped = 0
        for rv in revs:
            logical = rv["logical_record_id"]
            rv_no = max_no.get(logical, 0) + 1
            max_no[logical] = rv_no
            cur = con.execute(
                "INSERT INTO record_revisions"
                " (source_record_id, logical_record_id, table_name, snapshot_date, detected_at, revision_no,"
                "  change_type, severity, old_hash, new_hash, old_payload_json, new_payload_json,"
                "  changed_fields_json, source_snapshot_id, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT (source_record_id, snapshot_date) DO NOTHING",
                (rv["record_id"], logical, TABLE_BY_ROLE.get(rv["role"], "analyst_stock_events"),
                 after_date, now, rv_no,
                 rv["change_type"], rv["severity"], rv["old_hash"], rv["new_hash"],
                 json.dumps(rv["old_payload"], ensure_ascii=False) if rv["old_payload"] is not None else None,
                 json.dumps(rv["new_payload"], ensure_ascii=False) if rv["new_payload"] is not None else None,
                 json.dumps(rv["changed_fields"], ensure_ascii=False), snap_a, now))
            if cur.rowcount == 1:
                inserted += 1
            else:
                skipped += 1

        # ingest_runs 记账
        h = revision_hash_of(con)
        con.execute(
            "INSERT INTO ingest_runs (source_snapshot_id, parser_version, resolver_version, schema_version,"
            " started_at, finished_at, status, source_record_count, parsed_event_count,"
            " inserted_event_count, skipped_existing_count, error_count, result_hash, errors, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (snap_a, PARSER_VERSION, RESOLVER_VERSION, SCHEMA_VERSION,
             now, now, "success" if not errs else "failed",
             len(a_sections), len(revs), inserted, skipped, len(errs),
             h, json.dumps(errs, ensure_ascii=False) if errs else None, now, now))
        con.commit()
        run_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    stats["inserted"] = inserted
    stats["skipped_existing"] = skipped
    stats["error_count"] = len(errs)
    stats["run_id"] = run_id
    stats["result_hash"] = h[:16]
    stats["modified_breakdown"] = {"ROLE": stats["role"], "TEXT": stats["text"], "SEVERE": stats["severe"]}

    print("=== P1.4 Revision 持久化报告 ===")
    print(f"before: {args.before.name} ({stats['before_records']} records, date={before_date})")
    print(f"after : {args.after.name} ({stats['after_records']} records, date={after_date})")
    print(f"ADDED   : {stats['added']}")
    print(f"REMOVED : {stats['removed']}")
    print(f"MODIFIED: {stats['modified']}  ({json.dumps(stats['modified_breakdown'], ensure_ascii=False)})")
    print(f"Inserted revisions : {stats['inserted']}")
    print(f"Skipped existing   : {stats['skipped_existing']}")
    print(f"error_count        : {stats['error_count']}")
    print(f"ingest_runs run_id : {stats['run_id']} (parser={PARSER_VERSION})")
    print(f"result_hash        : {stats['result_hash']}")
    if errs:
        for e in errs[:10]:
            print("  ERR", e)
    return 0 if not errs else 1


if __name__ == "__main__":
    raise SystemExit(main())
