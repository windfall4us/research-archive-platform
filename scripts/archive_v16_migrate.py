#!/usr/bin/env python3
"""v1.6 迁移：event_stock_relation 表（2026-08-12）"""
import sqlite3, sys

DB = "/root/workspace/research_archive.db"

def main():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS event_stock_relation (
        event_id INTEGER NOT NULL,
        stock_code TEXT NOT NULL,
        stock_name TEXT,
        relation_type TEXT DEFAULT '产业链',  -- 直接受益|产业链|竞争影响|风险影响
        source TEXT DEFAULT 'auto',           -- auto|institution|manual
        confidence REAL DEFAULT 0.6,
        impact_score INTEGER DEFAULT 0,       -- 0-100 该股受事件影响强度
        logic TEXT,                           -- 关联逻辑（来自消息文本）
        mention_count INTEGER DEFAULT 1,      -- 事件内提及次数
        updated_at TEXT,
        PRIMARY KEY (event_id, stock_code)
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_esr_stock ON event_stock_relation(stock_code)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_esr_event ON event_stock_relation(event_id)")
    con.commit()
    print("✅ event_stock_relation 表就绪")
    con.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
