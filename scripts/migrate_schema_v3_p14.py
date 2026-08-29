#!/usr/bin/env python3
"""P1.4 schema v3 迁移：record_revisions 升级 old_value/new_value → old_payload_json/new_payload_json。

前提：record_revisions 在 P1.4 前为空表（0 行，0B.6 仅单元测试未落库）→ DROP 重建无数据损失。
其余 7 表不动（P1.1-P1.3 已落库数据保留）。
user_version: 2 → 3

用法: python3 scripts/migrate_schema_v3_p14.py
"""
import sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from create_consensus_schema_p1 import DDL, SCHEMA_VERSION

DB = ROOT / "data/analyst_consensus.db"


def main() -> int:
    con = sqlite3.connect(DB)
    try:
        before = con.execute("PRAGMA user_version").fetchone()[0]
        n_rev = con.execute("SELECT COUNT(*) FROM record_revisions").fetchone()[0]
        print(f"迁移前 user_version={before}, record_revisions rows={n_rev}")
        if n_rev > 0:
            print("!! record_revisions 非空，禁止 DROP 重建（须先迁移数据）")
            return 1
        # DROP 空表 + 重建（schema v3：old_payload_json/new_payload_json）
        con.execute("DROP TABLE IF EXISTS record_revisions")
        con.executescript(DDL)
        con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        con.commit()
        after = con.execute("PRAGMA user_version").fetchone()[0]
        cols = [r[1] for r in con.execute("PRAGMA table_info(record_revisions)")]
        print(f"迁移后 user_version={after}")
        print("record_revisions 列:", cols)
        assert "old_payload_json" in cols and "new_payload_json" in cols
        print("✅ schema v3 迁移完成")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
