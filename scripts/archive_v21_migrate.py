#!/usr/bin/env python3
"""v2.1 迁移：research_validation 表（2026-08-12）
研究后验验证：T+1/T+3/T+5 表现 + 最大涨幅/回撤 + 验证结果
"""
import sqlite3, sys

DB = "/root/workspace/research_archive.db"

def main():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS research_validation (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        stock_code TEXT NOT NULL,
        stock_name TEXT,
        research_score INTEGER DEFAULT 0,
        score_status TEXT,
        research_state TEXT,
        event_id INTEGER,
        event_title TEXT,
        trigger_date TEXT NOT NULL,       -- 评分快照日期（T 日）
        base_price REAL,                  -- T 日收盘价
        t1_date TEXT, t1_pct REAL,        -- T+1
        t3_date TEXT, t3_pct REAL,        -- T+3
        t5_date TEXT, t5_pct REAL,        -- T+5
        max_up REAL,                      -- 区间最大涨幅%
        max_drawdown REAL,                -- 区间最大回撤%
        result TEXT DEFAULT 'pending',    -- pending/hit/miss/insufficient
        validation_note TEXT,
        system_version TEXT,              -- v2.0.0
        parameter_version TEXT,           -- v1.9.0
        created_at TEXT,
        updated_at TEXT,
        UNIQUE (stock_code, trigger_date, parameter_version)
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_rv_stock ON research_validation(stock_code)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_rv_date ON research_validation(trigger_date)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_rv_result ON research_validation(result)")
    con.commit()
    print("✅ research_validation 表就绪")
    con.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
