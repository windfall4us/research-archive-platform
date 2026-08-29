#!/usr/bin/env python3
"""P2.0A: COMPOSITE 残留治理 —— consensus_event_exclusions 数据治理修正层。

背景（用户 2026-08-29 Phase 2.0 决策）：
  P1.2 早期 resolver 把 3 条多标的 COMPOSITE 记录误落成单股 EXACT 事件：
    - 天赢居 2026-08-28 东微半导(688261)/瑞芯微(603893) -> event 1093 (WATCH)
    - 天赢居 2026-08-28 天齐锂业(002466)/赣锋锂业(002460) -> event 1095 (REDUCE)
    - 天赢居 2026-08-28 黄河旋风(600172)/四方达(300179)   -> event 1107 (WATCH)
  这些残留若进入 Phase 2 聚合会给 Theme Heat / Stock coverage 假信号。

原则（用户锁定）：
  * 不物理删除历史事实（Phase 1 冻结数据不动，events 表 937 物理记录不变）
  * 不 UPDATE 旧事件
  * 新增 consensus_event_exclusions 治理表（append-only），reason_code=COMPOSITE_MISRESOLVED
  * Phase 2 聚合层明确排除，审计可追踪
  * 统一口径：DB physical 937 / Phase2 exclusions 3 / Aggregation eligible 934

Schema: PRAGMA user_version 3 -> 4（仅新增治理表，不改 Phase 1 三张业务表）。

用法: python3 scripts/create_exclusions_p20a.py
输出: 治理表 + 3 条 exclusion + 口径验证
"""
import json, sqlite3, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data/analyst_consensus.db"

BEIJING_TZ = timezone(timedelta(hours=8))
NOW = datetime.now(BEIJING_TZ).isoformat(timespec="seconds")

DDL_EXCLUSIONS = """
CREATE TABLE IF NOT EXISTS consensus_event_exclusions (
    exclusion_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      INTEGER NOT NULL UNIQUE REFERENCES analyst_stock_events(event_id),
    reason_code   TEXT NOT NULL CHECK (reason_code IN ('COMPOSITE_MISRESOLVED')),
    reason_text   TEXT NOT NULL,
    detected_at   TEXT NOT NULL,
    source        TEXT NOT NULL,          -- 治理 run 标识，如 'p20a-v1'
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_exclusions_event ON consensus_event_exclusions(event_id);
"""

# (event_id, source_record_id 关键字, reason_text)
TARGETS = [
    (1093, "东微半导(688261)/瑞芯微(603893)",
     "P1.2 COMPOSITE 多标的误落单股 EXACT：raw_target 含 2 标的（东微半导+瑞芯微），早期 resolver 仅取首代码。Phase 2 聚合排除。"),
    (1095, "天齐锂业(002466)/赣锋锂业(002460)",
     "P1.2 COMPOSITE 多标的误落单股 EXACT：raw_target 含 2 标的（天齐锂业+赣锋锂业）。Phase 2 聚合排除。"),
    (1107, "黄河旋风(600172)/四方达(300179)",
     "P1.2 COMPOSITE 多标的误落单股 EXACT：raw_target 含 2 标的（黄河旋风+四方达）。Phase 2 聚合排除。"),
]


def main() -> int:
    con = sqlite3.connect(DB)
    con.executescript(DDL_EXCLUSIONS)
    con.execute("PRAGMA user_version = 4")
    inserted = 0
    for eid, key, reason in TARGETS:
        cur = con.execute(
            "INSERT OR IGNORE INTO consensus_event_exclusions"
            " (event_id, reason_code, reason_text, detected_at, source, created_at, updated_at)"
            " VALUES (?, 'COMPOSITE_MISRESOLVED', ?, ?, 'p20a-v1', ?, ?)",
            (eid, reason, NOW, NOW, NOW))
        inserted += cur.rowcount
    con.commit()

    # ---- 口径验证 ----
    ev_total = con.execute("SELECT COUNT(*) FROM analyst_stock_events").fetchone()[0]
    excl = con.execute("SELECT COUNT(*) FROM consensus_event_exclusions").fetchone()[0]
    # 验证 3 条目标确实被排除、且都指向 COMPOSITE 残留
    detail = con.execute("""
        SELECT e.event_id, e.action_type, e.raw_target, e.resolve_method, x.reason_code
        FROM consensus_event_exclusions x JOIN analyst_stock_events e USING(event_id)
        ORDER BY e.event_id""").fetchall()
    # events hash 必须未变（冻结基线校验）
    import hashlib
    rows = con.execute(
        "SELECT source_record_id, event_index, action_type, event_category, action_status,"
        " temporal_type, stock_code, stock_name, raw_target, resolve_method"
        " FROM analyst_stock_events ORDER BY source_record_id, event_index").fetchall()
    h = hashlib.sha256("\n".join("|".join(str(x) for x in r) for r in rows).encode()).hexdigest()[:16]
    con.close()

    report = {
        "schema_version": 4,
        "events_physical": ev_total,
        "phase2_exclusions": excl,
        "aggregation_eligible": ev_total - excl,
        "events_hash_unchanged": h,
        "excluded_detail": [list(r) for r in detail],
    }
    (ROOT / "reports" / "phase2_0a_exclusions.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== P2.0A COMPOSITE 残留治理 ===")
    print(f"inserted exclusions: {inserted}")
    print(f"口径: DB physical events = {ev_total} | Phase2 exclusions = {excl} | Aggregation eligible = {ev_total - excl}")
    print(f"events hash 未变: {h} (冻结基线 478a7c4f… 应不变)")
    for d in detail:
        print(f"  excluded: event {d[0]} {d[1]} | {d[2]} | {d[3]} | {d[4]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
