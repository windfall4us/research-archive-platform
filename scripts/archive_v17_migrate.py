#!/usr/bin/env python3
"""v1.7 迁移：event_momentum 表 + event_clusters 新列（2026-08-12）"""
import sqlite3, sys

DB = "/root/workspace/research_archive.db"

def main():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS event_momentum (
        event_id INTEGER NOT NULL,
        bucket_hour TEXT NOT NULL,     -- 2026-08-12 08:00
        momentum_score INTEGER DEFAULT 0,
        msg_count INTEGER DEFAULT 0,          -- 该小时新增消息
        src_count INTEGER DEFAULT 0,          -- 该小时新增独立来源
        inst_count INTEGER DEFAULT 0,         -- 该小时新增机构
        stock_count INTEGER DEFAULT 0,        -- 该小时新增股票映射
        cum_msg INTEGER DEFAULT 0,            -- 累计消息
        cum_inst INTEGER DEFAULT 0,           -- 累计机构
        cum_stock INTEGER DEFAULT 0,          -- 累计股票
        PRIMARY KEY (event_id, bucket_hour)
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_mom_event ON event_momentum(event_id)")
    cols = [r[1] for r in con.execute("PRAGMA table_info(event_clusters)")]
    for name, decl in [
        ("momentum_score", "INTEGER DEFAULT 0"),     # 当前热度（最近小时桶）
        ("momentum_peak", "INTEGER DEFAULT 0"),      # 历史峰值
        ("trigger_type", "TEXT"),                    # FIRST_INSTITUTION/STOCK_EXPANSION/CONSENSUS_BUILD/HEAT_BREAKOUT
        ("trigger_at", "TEXT"),                      # 触发时间
    ]:
        if name not in cols:
            con.execute(f"ALTER TABLE event_clusters ADD COLUMN {name} {decl}")
            print(f"  + event_clusters.{name}")
    con.commit()
    print("✅ v1.7 迁移完成")
    con.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
