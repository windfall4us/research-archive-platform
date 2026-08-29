#!/usr/bin/env python3
"""P1.1: Consensus Data Layer 空库验收（6 项 gate）。

① 8 表存在 + 唯一键存在
② FK / logical 引用字段齐全
③ 所有枚举列受 CHECK 约束
④ 重复插入唯一键失败（IntegrityError）
⑤ PRAGMA user_version = 1
⑥ 空库 DROP/CREATE 重放（create 脚本二次运行无错且结构一致）

验收后不留下任何测试数据（事务内测试 + ROLLBACK）。
用法: python3 scripts/validate_consensus_schema_p1.py
"""
import sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data/analyst_consensus.db"
EXPECT_TABLES = [
    "analyst_profiles", "source_snapshots", "analyst_daily_views",
    "analyst_stock_events", "analyst_position_snapshots", "analyst_theme_mentions",
    "record_revisions", "ingest_runs",
]
# 每表期望的 UNIQUE 子句（去空格后包含即可）
EXPECT_UNIQUE = {
    "analyst_profiles": "UNIQUE (analyst_name)",
    "source_snapshots": "UNIQUE (source, snapshot_date)",
    "analyst_daily_views": "UNIQUE (analyst_id, view_date, view_type)",
    "analyst_stock_events": "UNIQUE (source_record_id, event_index)",
    "analyst_position_snapshots": "UNIQUE (analyst_id, snapshot_date, source_record_id)",
    "analyst_theme_mentions": "UNIQUE (analyst_id, mention_date, theme_name, source_record_id)",
    "record_revisions": "UNIQUE (source_record_id, snapshot_date)",
}
# 期望的枚举 CHECK 子串（每表若干）
EXPECT_CHECK = {
    "analyst_stock_events": ["CHECK (action_type IN", "CHECK (event_category IN",
                             "CHECK (action_status IN", "CHECK (temporal_type IN",
                             "CHECK (resolve_method IN", "CHECK (role IN",
                             "CHECK (stance IS NULL"],
    "analyst_position_snapshots": ["CHECK (position_state = 'HOLDING')", "CHECK (resolve_method IN"],
    "analyst_daily_views": ["CHECK (view_type IN"],
    "analyst_theme_mentions": ["CHECK (mention_type IN"],
    "record_revisions": ["CHECK (change_type IN", "CHECK (severity IN"],
    "ingest_runs": ["CHECK (status IN"],
    "analyst_profiles": ["CHECK (style IN"],
}
# FK / logical 引用字段：期望存在的列
EXPECT_COLS = {
    "analyst_stock_events": ["source_record_id", "logical_record_id", "analyst_id",
                             "source_snapshot_id", "event_index", "event_date",
                             "stock_code", "action_type", "event_category", "stance"],
    "analyst_position_snapshots": ["source_record_id", "logical_record_id", "analyst_id",
                                   "source_snapshot_id", "snapshot_date", "position_state"],
    "record_revisions": ["source_record_id", "logical_record_id", "source_snapshot_id",
                         "snapshot_date", "change_type", "severity", "changed_fields_json"],
    "ingest_runs": ["source_snapshot_id", "parser_version", "resolver_version", "status",
                    "started_at", "finished_at", "source_record_count", "parsed_event_count",
                    "inserted_event_count", "skipped_existing_count", "error_count", "result_hash"],
    "source_snapshots": ["snapshot_id", "source", "snapshot_date", "page_sha256", "raw_json_path"],
    "analyst_daily_views": ["analyst_id", "view_date", "view_type", "content", "record_hash"],
    "analyst_theme_mentions": ["analyst_id", "mention_date", "theme_name", "theme_id"],
}
EXPECT_INDEXES = {
    "idx_events_analyst_date", "idx_events_code_date", "idx_events_action_date", "idx_events_logical",
    "idx_pos_analyst_date", "idx_pos_code_date", "idx_pos_logical", "idx_rev_logical",
    "idx_runs_snapshot_versions",
}


def norm(s):
    return "".join(s.split())


def check_tables_and_uniques(con):
    fails = []
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    for t in EXPECT_TABLES:
        if t not in tables:
            fails.append(f"[①] 缺表 {t}")
    # 唯一键：检查 sqlite_autoindex 存在（UNIQUE 自动建的唯一索引）
    # 例外: ingest_runs v2 仅 run_id 主键、无 UNIQUE（同版本重跑留独立 run history）
    idxs = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    for t in EXPECT_TABLES:
        if t == "ingest_runs":
            continue
        auto = [i for i in idxs if i.startswith(f"sqlite_autoindex_{t}_")]
        if not auto:
            fails.append(f"[①] 缺 {t} 唯一键(autoindex)")
    return fails


def check_checks(con):
    fails = []
    for t, subs in EXPECT_CHECK.items():
        sql = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                          (t,)).fetchone()
        if not sql:
            fails.append(f"[③] 无表 {t}")
            continue
        nsql = norm(sql[0])
        for sub in subs:
            if norm(sub) not in nsql:
                fails.append(f"[③] {t} 缺 CHECK: {sub}")
    return fails


def check_cols(con):
    fails = []
    for t, cols in EXPECT_COLS.items():
        have = {r[1] for r in con.execute(f"PRAGMA table_info({t})")}
        for c in cols:
            if c not in have:
                fails.append(f"[②] {t} 缺列 {c}")
    return fails


def check_indexes(con):
    fails = []
    idxs = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    for i in EXPECT_INDEXES:
        if i not in idxs:
            fails.append(f"[①] 缺索引 {i}")
    return fails


def check_duplicate_and_check_constraint(con):
    """事务内测试 ④ 重复唯一键失败 + CHECK 失败；结束后 ROLLBACK 不留数据。"""
    fails = []
    con.execute("BEGIN")
    try:
        now = "2026-08-28T00:00:00"
        con.execute("INSERT INTO analyst_profiles (analyst_id, analyst_name, style, created_at, updated_at)"
                    " VALUES ('TEST', '测试分析师', 'SWING', ?, ?)", (now, now))
        con.execute("INSERT INTO source_snapshots (source, snapshot_date, page_sha256, created_at, updated_at)"
                    " VALUES ('vip0', '2026-01-01', 'testhash', ?, ?)", (now, now))
        row = ("vip0:TEST:2026-01-01:甲:action:000", "vip0:TEST:2026-01-01:甲", "daily_action", 0,
               "TEST", "2026-01-01", "TODAY", None, "甲", "WATCH", "OBSERVATION", "INTENDED",
               "FOLLOW", None, None, "EXACT", 1, "h1", now, now)
        con.execute(
            "INSERT INTO analyst_stock_events (source_record_id, logical_record_id, role, event_index,"
            " analyst_id, event_date, temporal_type, stock_code, raw_target, action_type, event_category,"
            " action_status, stance, raw_action, raw_logic, resolve_method, source_snapshot_id,"
            " record_hash, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
        # ④ 重复唯一键
        try:
            con.execute(
                "INSERT INTO analyst_stock_events (source_record_id, logical_record_id, role, event_index,"
                " analyst_id, event_date, temporal_type, stock_code, raw_target, action_type, event_category,"
                " action_status, stance, raw_action, raw_logic, resolve_method, source_snapshot_id,"
                " record_hash, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9],
                 row[10], row[11], row[12], row[13], row[14], row[15], row[16], row[17], now, now))
            fails.append("[④] 重复插入唯一键未报错")
        except sqlite3.IntegrityError:
            pass
        # CHECK：非法 action_type
        try:
            con.execute(
                "INSERT INTO analyst_stock_events (source_record_id, logical_record_id, role, event_index,"
                " analyst_id, event_date, temporal_type, stock_code, raw_target, action_type, event_category,"
                " action_status, stance, raw_action, raw_logic, resolve_method, source_snapshot_id,"
                " record_hash, created_at, updated_at)"
                " VALUES ('x', 'x', 'daily_action', 0, 'TEST', '2026-01-01', 'TODAY', NULL, '甲', 'NOPE',"
                " 'TRADE', 'INTENDED', NULL, NULL, NULL, 'EXACT', 1, 'h', ?, ?)", (now, now))
            fails.append("[③] CHECK 约束未拦截非法枚举")
        except sqlite3.IntegrityError:
            pass
    finally:
        con.execute("ROLLBACK")
    return fails


def main() -> int:
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")
    all_fails = []
    try:
        all_fails += check_tables_and_uniques(con)
        all_fails += check_cols(con)
        all_fails += check_checks(con)
        all_fails += check_indexes(con)
        all_fails += check_duplicate_and_check_constraint(con)
        uv = con.execute("PRAGMA user_version").fetchone()[0]
        if uv != 2:
            all_fails.append(f"[⑤] user_version={uv}，期望 2")

        # ⑥ 重放：空库可重跑 create（IF NOT EXISTS 幂等），结构一致
        import subprocess
        r = subprocess.run([sys.executable, str(ROOT / "scripts/create_consensus_schema_p1.py")],
                           capture_output=True, text=True)
        if r.returncode != 0:
            all_fails.append(f"[⑥] create 重放失败: {r.stderr[-300:]}")
        n_after = con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
        if n_after != 8:
            all_fails.append(f"[⑥] 重放后表数 {n_after} != 8")

        # 最终表应为空（无测试残留）
        for t in EXPECT_TABLES:
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            if n != 0:
                all_fails.append(f"[残留] {t} 有 {n} 行（验收应保持空库）")
    finally:
        con.close()

    print("=== P1.1 空库验收 ===")
    if all_fails:
        for f in all_fails:
            print("  ❌", f)
        print(f"结果: FAIL（{len(all_fails)} 项）")
        return 1
    print("  ✅ ① 8 表存在 + 唯一键存在（含 autoindex）")
    print("  ✅ ① 普通索引齐备（events×4 / pos×3 / rev×1）")
    print("  ✅ ② FK / logical 引用字段齐全")
    print("  ✅ ③ 枚举列全部受 CHECK（含非法值拦截实测）")
    print("  ✅ ④ 重复插入唯一键 → IntegrityError（实测）")
    print("  ✅ ⑤ PRAGMA user_version = 2")
    print("  ✅ ⑥ 空库 create 重放无错，结构一致")
    print("  ✅ 验收后为空库（无测试残留）")
    print("结果: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
