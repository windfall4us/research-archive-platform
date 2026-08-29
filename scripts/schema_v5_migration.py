#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
schema_v5_migration.py — analyst_consensus.db v4 → v5
======================================================
P2.0C Theme Mention Ingest 的 schema 规范迁移（用户 2026-08-30 确认）。

v4 → v5 变更（仅 analyst_theme_mentions 扩展，不改既有冻结表）：
  + normalized_theme  TEXT                       -- 归一化主题名（L2 名）
  + l1               TEXT                        -- L1 大方向中文名
  + l2               TEXT                        -- L2 主题中文名
  + stance           TEXT CHECK(...)             -- POSITIVE/NEGATIVE/NEUTRAL/UNKNOWN（枚举含 UNKNOWN 防未来再迁移）
  + mention_source   TEXT NOT NULL DEFAULT 'DIRECT'
                     CHECK(...)                  -- DIRECT / INFERRED_FROM_STOCK（Phase 2.2 扩展位）

幂等：可重复执行；已迁移则跳过。仅当 user_version==4 时执行，否则中止。
"""

import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "analyst_consensus.db"
V5_ADD_COLUMNS = [
    ("normalized_theme", "TEXT"),
    ("l1", "TEXT"),
    ("l2", "TEXT"),
    ("stance", "TEXT CHECK (stance IN ('POSITIVE','NEGATIVE','NEUTRAL','UNKNOWN'))"),
    ("mention_source", "TEXT NOT NULL DEFAULT 'DIRECT' CHECK (mention_source IN ('DIRECT','INFERRED_FROM_STOCK'))"),
]


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    v = cur.execute("PRAGMA user_version").fetchone()[0]
    if v == 5:
        print("已在 v5，跳过迁移。")
        return 0
    if v != 4:
        print(f"中止：当前 user_version={v}，仅支持从 v4 迁移到 v5。")
        return 1

    existing = {r[1] for r in cur.execute("PRAGMA table_info(analyst_theme_mentions)")}
    for col, ddl in V5_ADD_COLUMNS:
        if col not in existing:
            cur.execute(f"ALTER TABLE analyst_theme_mentions ADD COLUMN {col} {ddl}")
            print(f"  + {col} {ddl}")
        else:
            print(f"  = {col} 已存在，跳过")

    cur.execute("PRAGMA user_version = 5")
    con.commit()

    # 验证
    v2 = cur.execute("PRAGMA user_version").fetchone()[0]
    cols = [r[1] for r in cur.execute("PRAGMA table_info(analyst_theme_mentions)")]
    print(f"  user_version -> {v2}")
    print(f"  analyst_theme_mentions 列: {cols}")
    print("✅ v4 → v5 迁移完成")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
