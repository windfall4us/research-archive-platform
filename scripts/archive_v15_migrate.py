#!/usr/bin/env python3
"""v1.5 事件语义层迁移：event_clusters 新列（2026-08-12）"""
import sqlite3, sys

DB = "/root/workspace/research_archive.db"

NEW_COLS = [
    ("event_score", "INTEGER DEFAULT 0"),        # 六维加权评分
    ("status", "TEXT DEFAULT 'emerging'"),       # emerging/heating/stable/fading/closed
    ("cluster_confidence", "REAL DEFAULT 0.9"),  # 聚类置信度
    ("update_count", "INTEGER DEFAULT 1"),       # 更新次数（消息数）
    ("merge_status", "TEXT DEFAULT 'auto'"),     # auto/confirmed/manual_merged/manual_split
]

def main():
    con = sqlite3.connect(DB)
    cols = [r[1] for r in con.execute("PRAGMA table_info(event_clusters)")]
    for name, decl in NEW_COLS:
        if name not in cols:
            con.execute(f"ALTER TABLE event_clusters ADD COLUMN {name} {decl}")
            print(f"  + event_clusters.{name} {decl}")
    # event_messages 已有 message_role 列（v1.4 建的），确认
    em_cols = [r[1] for r in con.execute("PRAGMA table_info(event_messages)")]
    print("  event_messages 列:", em_cols)
    con.commit()
    print("✅ v1.5 迁移完成")
    con.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
