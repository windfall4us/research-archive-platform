#!/usr/bin/env python3
"""v1.8 迁移：event_watch_pool 表（2026-08-12）
事件驱动研究候选层 —— 非交易层（安全边界：不写 positions/不改交易状态）
"""
import sqlite3, sys

DB = "/root/workspace/research_archive.db"

def main():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS event_watch_pool (
        pool_id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        stock_code TEXT NOT NULL,
        stock_name TEXT,
        status TEXT DEFAULT 'EVENT_FOUND',   -- EVENT_FOUND→RESEARCH→WATCH→MODEL_CHECK→TRIAL_READY
        trigger_source TEXT,                  -- FIRST_INSTITUTION/STOCK_EXPANSION/HEAT_BREAKOUT
        momentum_score INTEGER DEFAULT 0,     -- 事件热度（快照）
        event_score INTEGER DEFAULT 0,        -- 事件综合评分
        model_score REAL DEFAULT 0,           -- 十模型综合分（0-100）
        model_detail TEXT,                    -- JSON：各模型通过情况
        confidence REAL DEFAULT 0.5,
        event_title TEXT,                     -- 冗余：事件标题（列表展示）
        relation_type TEXT,                   -- 直接受益/产业链
        impact_score INTEGER DEFAULT 0,       -- 个股影响强度
        logic TEXT,                           -- 关联逻辑
        review_note TEXT,                     -- 人工确认记录
        created_at TEXT,
        updated_at TEXT,
        UNIQUE (event_id, stock_code)
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_wp_status ON event_watch_pool(status)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_wp_stock ON event_watch_pool(stock_code)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_wp_momentum ON event_watch_pool(momentum_score)")
    con.commit()
    print("✅ event_watch_pool 表就绪")
    con.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
