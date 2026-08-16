#!/usr/bin/env python3
"""v2.0 迁移：research_summary 表（2026-08-12）
研究结论（Research Summary）历史保存：优势/风险/建议
"""
import sqlite3, sys

DB = "/root/workspace/research_archive.db"

def main():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS research_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        stock_code TEXT NOT NULL,
        stock_name TEXT,
        summary TEXT,              -- 研究判断（自然语言）
        positive_factors TEXT,     -- 优势因素 JSON
        risk_factors TEXT,         -- 风险因素 JSON
        missing_conditions TEXT,   -- 缺失条件 JSON
        research_score INTEGER DEFAULT 0,
        research_state TEXT,
        suggestion TEXT,           -- 建议（非买入）
        parameter_version TEXT,
        created_at TEXT
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_rsum_stock ON research_summary(stock_code)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_rsum_created ON research_summary(created_at)")
    con.commit()
    print("✅ research_summary 表就绪")
    con.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
