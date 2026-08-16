#!/usr/bin/env python3
"""v1.9 迁移：research_scores 表（2026-08-12）
Research Score（研究综合分）历史保存 + parameter_version
安全边界：研究排序层，不接交易状态机
"""
import sqlite3, sys

DB = "/root/workspace/research_archive.db"

def main():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS research_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        stock_code TEXT NOT NULL,
        stock_name TEXT,
        event_id INTEGER,               -- 主关联事件
        event_score INTEGER DEFAULT 0,  -- 事件强度 0-30
        model_score INTEGER DEFAULT 0,  -- 十大模型 0-35
        technical_score INTEGER DEFAULT 0, -- 技术状态 0-20
        capital_score INTEGER DEFAULT 0,   -- 资金状态 0-15
        research_score INTEGER DEFAULT 0,  -- 综合 0-100
        score_status TEXT,              -- 重点研究/优先跟踪/观察/普通/忽略
        explanation_json TEXT,          -- 贡献/扣分解释
        missing_conditions TEXT,        -- 缺失条件 JSON
        model_detail TEXT,              -- 模型命中详情
        event_title TEXT,
        momentum_score INTEGER DEFAULT 0,
        parameter_version TEXT,         -- 参数版本 v1.9.0
        created_at TEXT,
        updated_at TEXT
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_rs_stock ON research_scores(stock_code)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_rs_updated ON research_scores(updated_at)")
    con.commit()
    print("✅ research_scores 表就绪")
    con.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
