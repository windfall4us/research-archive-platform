#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
schema_v6_migration.py — analyst_consensus.db v5 → v6
======================================================
P2.0B Market View Ingest 落地（用户 2026-08-30 收口后补全）。

v5 → v6 变更（analyst_daily_views 扩展，既有 193 行原文 + revision 链路不动）：
  1. view_type CHECK 扩展：IN ('core_theme','trend','logic','market')
     —— SQLite 不能 ALTER CHECK，采用 12 步重建表（本库无表 FK 引用 daily_views、无触发器、无额外索引，重建安全）
  2. 新增 6 列（仅 view_type='market' 行填充，其余行 NULL）：
     market_direction / market_score / risk_level / position_bias / summary / raw_text

幂等：若已含 market 列且 CHECK 已含 'market' 则跳过。执行前备份原表为 analyst_daily_views_v5_bak。
"""

import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "analyst_consensus.db"


def has_market_check(cur):
    row = cur.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='analyst_daily_views'").fetchone()
    return row is not None and "view_type IN ('core_theme','trend','logic','market')" in row[0]


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    v = cur.execute("PRAGMA user_version").fetchone()[0]

    cols = {r[1] for r in cur.execute("PRAGMA table_info(analyst_daily_views)")}
    if "market_direction" in cols and has_market_check(cur):
        print("已迁移到 v6（CHECK 含 market + 6 列），跳过。")
        con.close()
        return 0

    new_ddl = """CREATE TABLE analyst_daily_views_new (
    view_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    analyst_id         TEXT NOT NULL REFERENCES analyst_profiles(analyst_id),
    view_date          TEXT NOT NULL,
    view_type          TEXT NOT NULL CHECK (view_type IN ('core_theme','trend','logic','market')),
    content            TEXT NOT NULL,
    source_snapshot_id INTEGER REFERENCES source_snapshots(snapshot_id),
    record_hash        TEXT NOT NULL,
    first_seen_at      TEXT,
    last_seen_at       TEXT,
    revision_no        INTEGER NOT NULL DEFAULT 1,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    market_direction   TEXT,
    market_score       REAL,
    risk_level         TEXT,
    position_bias      TEXT,
    summary            TEXT,
    raw_text           TEXT,
    UNIQUE (analyst_id, view_date, view_type)
)"""

    old_count = cur.execute("SELECT COUNT(*) FROM analyst_daily_views").fetchone()[0]
    cur.execute("PRAGMA foreign_keys=OFF")
    try:
        cur.execute("ALTER TABLE analyst_daily_views RENAME TO analyst_daily_views_v5_bak")
        cur.execute(new_ddl)
        cur.execute(
            """INSERT INTO analyst_daily_views_new (view_id, analyst_id, view_date, view_type, content, source_snapshot_id,
                record_hash, first_seen_at, last_seen_at, revision_no, created_at, updated_at,
                market_direction, market_score, risk_level, position_bias, summary, raw_text)
               SELECT view_id, analyst_id, view_date, view_type, content, source_snapshot_id,
                record_hash, first_seen_at, last_seen_at, revision_no, created_at, updated_at,
                market_direction, market_score, risk_level, position_bias, summary, raw_text
               FROM analyst_daily_views_v5_bak""")
        cur.execute("DROP TABLE analyst_daily_views_v5_bak")
        cur.execute("ALTER TABLE analyst_daily_views_new RENAME TO analyst_daily_views")
        con.commit()
    except Exception as e:
        con.rollback()
        print(f"❌ 迁移失败：{e}")
        con.close()
        return 1
    finally:
        cur.execute("PRAGMA foreign_keys=ON")

    new_count = cur.execute("SELECT COUNT(*) FROM analyst_daily_views").fetchone()[0]
    ok = has_market_check(cur)
    if old_count != new_count or not ok:
        print(f"❌ 迁移校验失败：old={old_count} new={new_count} check_market={ok}")
        con.close()
        return 1

    if v != 6:
        cur.execute("PRAGMA user_version = 6")
    con.commit()
    v2 = cur.execute("PRAGMA user_version").fetchone()[0]
    cols2 = [r[1] for r in cur.execute("PRAGMA table_info(analyst_daily_views)")]
    print(f"✅ v→v6 重建完成 | 行数 {old_count}→{new_count} | user_version={v2}")
    print(f"   列: {cols2}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
