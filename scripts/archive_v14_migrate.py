#!/usr/bin/env python3
"""资讯研究档案库 v1.4 - 数据库迁移
message_classification 加 v1.4 维度列；新建 event_clusters / event_messages 表。
保留旧列（primary_category 等）兼容现有 UI/API，新维度叠加。
2026-08-12
"""
import sqlite3, sys

DB = "/root/workspace/research_archive.db"

NEW_COLS = [
    # 8 主类型（互斥）: research_report|institution_view|research_activity|news|announcement|market|digest|attachment
    ("content_type", "TEXT"),
    ("content_subtype", "TEXT"),          # 二级：公司点评/行业观点/宏观策略/行业深度/业绩预告/传闻求证...
    ("ingest_source", "TEXT"),            # fs2tg / 群转发账户
    ("original_source", "TEXT"),          # 财联社/上交所/巨潮...
    ("institution", "TEXT"),              # 天风证券（标准化）
    ("research_team", "TEXT"),            # 通信/电子（【天风通信】→ 通信）
    ("industry", "TEXT"),                 # 一级行业：电子/通信/计算机/电力设备...
    ("themes_json", "TEXT"),              # 二级主题: ["存储","HBM","AI算力"]
    ("message_role", "TEXT"),             # headline|body|attachment|stock_mapping|continuation
    ("research_value", "INTEGER DEFAULT 0"),   # 0-100 六维评分
    ("confidence_score", "REAL DEFAULT 0.5"),  # 0-1
    ("review_reason_detail", "TEXT"),     # 拆分后的复核原因
]

def main():
    con = sqlite3.connect(DB)
    cols = [r[1] for r in con.execute("PRAGMA table_info(message_classification)")]
    for name, decl in NEW_COLS:
        if name not in cols:
            con.execute(f"ALTER TABLE message_classification ADD COLUMN {name} {decl}")
            print(f"  + message_classification.{name} {decl}")
    # 索引
    con.execute("CREATE INDEX IF NOT EXISTS idx_mc_content_type ON message_classification(content_type)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_mc_date ON message_classification(classified_at)")
    # 事件表
    con.execute("""CREATE TABLE IF NOT EXISTS event_clusters (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_title TEXT,
        event_type TEXT,          -- 海外公司业绩|行业事件|传闻求证|政策|公司事件|板块行情
        industry TEXT,
        themes_json TEXT,
        occurred_date TEXT,
        stock_codes_json TEXT,
        source_count INTEGER DEFAULT 0,
        institution_count INTEGER DEFAULT 0,
        importance_score INTEGER DEFAULT 0,
        first_seen_at TEXT,
        last_seen_at TEXT,
        entity_key TEXT UNIQUE,   -- 聚类键：实体名|日期
        created_at TEXT
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS event_messages (
        event_id INTEGER,
        message_id TEXT,
        message_role TEXT,
        PRIMARY KEY (event_id, message_id)
    )""")
    con.commit()
    print("✅ v1.4 迁移完成: content_type/event_clusters/event_messages 就绪")
    con.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
