#!/usr/bin/env python3
"""资讯研究档案库 v1.0 - 统一版 Schema 初始化
按统一设计重建全部表（DROP 旧结构，测试数据可重灌）。
2026-08-09
"""
import sqlite3, sys

DB = "/root/workspace/research_archive.db"

SCHEMA = """
-- 1. 原始消息层（增量追加，永不覆盖）
CREATE TABLE IF NOT EXISTS raw_messages (
  chat_id TEXT NOT NULL,
  message_id INTEGER NOT NULL,
  date TEXT,
  from_user TEXT,
  reply_to_message_id INTEGER,
  source_topic TEXT,
  msg_type TEXT,                -- text | image
  raw_text TEXT,
  relative_image_path TEXT,
  raw_json TEXT,
  imported_at TEXT,
  PRIMARY KEY (chat_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_raw_topic ON raw_messages(source_topic);
CREATE INDEX IF NOT EXISTS idx_raw_date ON raw_messages(date);

-- 2. 标准化层（清洗 + 实体识别）
CREATE TABLE IF NOT EXISTS normalized_messages (
  message_id TEXT PRIMARY KEY,
  normalized_text TEXT,
  title TEXT,
  source TEXT,
  institution TEXT,
  analyst TEXT,
  stock_codes_json TEXT,
  stock_names_json TEXT,
  industries_json TEXT,
  topics_json TEXT,
  normalized_at TEXT
);

-- 3. 分类层（六源 topic + 内容类型并行，可重算）
CREATE TABLE IF NOT EXISTS message_classification (
  message_id TEXT PRIMARY KEY,
  source_topic TEXT,
  primary_category TEXT,        -- research|announcement|market|news|image|empty_invalid
  secondary_category TEXT,
  tags_json TEXT,
  entities_json TEXT,
  sentiment TEXT,
  confidence TEXT,
  continuation INTEGER DEFAULT 0,
  review_required INTEGER DEFAULT 0,
  review_reason TEXT,
  vision_status TEXT,
  classifier_version TEXT,
  classified_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_cls_type ON message_classification(primary_category);
CREATE INDEX IF NOT EXISTS idx_cls_topic ON message_classification(source_topic);
CREATE INDEX IF NOT EXISTS idx_cls_review ON message_classification(review_required);

-- 4. 每日聚合日报（六源合并日报归档）
CREATE TABLE IF NOT EXISTS daily_reports (
  daily_report_id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_date TEXT UNIQUE,
  summary TEXT,
  market_view TEXT,
  main_topics TEXT,
  risk_notes TEXT,
  source_message_count INTEGER DEFAULT 0,
  created_at TEXT
);

-- 5. 研报主体
CREATE TABLE IF NOT EXISTS report_series (
  series_id INTEGER PRIMARY KEY AUTOINCREMENT,
  norm_key TEXT UNIQUE,
  title TEXT,
  institution TEXT,
  analyst TEXT,
  report_type TEXT,
  first_seen_at TEXT,
  last_seen_at TEXT,
  current_version INTEGER DEFAULT 1,
  occurrence_count INTEGER DEFAULT 1,
  status TEXT DEFAULT 'active'  -- active|tracking|verified|expired|invalidated
);
CREATE INDEX IF NOT EXISTS idx_series_inst ON report_series(institution);
CREATE INDEX IF NOT EXISTS idx_series_seen ON report_series(last_seen_at);

-- 6. 研报版本（内容变化生成新版本）
CREATE TABLE IF NOT EXISTS report_versions (
  version_id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id INTEGER,
  version_no INTEGER,
  core_view TEXT,
  logic TEXT,
  catalysts TEXT,
  risks TEXT,
  valuation TEXT,
  stock_codes_json TEXT,
  industries_json TEXT,
  content_hash TEXT,
  structure_hash TEXT,
  changed_summary TEXT,
  created_at TEXT
);

-- 7. 报告-消息关联（研报被拆分多条）
CREATE TABLE IF NOT EXISTS report_messages (
  report_id INTEGER,
  message_id TEXT,
  sequence_no INTEGER,
  is_first INTEGER DEFAULT 0,
  is_last INTEGER DEFAULT 0,
  PRIMARY KEY (report_id, message_id)
);

-- 7b. 报告-实体关联（股票/行业/机构）
CREATE TABLE IF NOT EXISTS report_entities (
  report_id INTEGER,
  entity_type TEXT,     -- stock | industry | institution
  entity_id TEXT,
  entity_name TEXT,
  relation_type TEXT DEFAULT '重点关注'
);
CREATE INDEX IF NOT EXISTS idx_re_entity ON report_entities(entity_id);
CREATE INDEX IF NOT EXISTS idx_re_report ON report_entities(report_id);

-- 8. 重复出现记录
CREATE TABLE IF NOT EXISTS report_occurrences (
  occurrence_id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id INTEGER,
  message_id TEXT,
  appeared_at TEXT,
  is_primary INTEGER DEFAULT 0,
  is_duplicate INTEGER DEFAULT 0,
  duplicate_type TEXT  -- exact_duplicate|format_duplicate|updated_version|independent_report
);

-- 9. 长期验证
CREATE TABLE IF NOT EXISTS report_verifications (
  verification_id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id INTEGER,
  event_date TEXT,
  event_type TEXT,
  event_text TEXT,
  verification_status TEXT DEFAULT '待验证',
  evidence_source TEXT,
  created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ver_status ON report_verifications(verification_status);
"""


def main():
    con = sqlite3.connect(DB)
    # DROP 旧结构（测试数据可从缓存重灌）
    for t in ["report_versions", "report_messages", "report_occurrences", "report_verifications",
              "report_entities", "research_reports", "report_series", "message_classification",
              "normalized_messages", "daily_reports", "raw_messages"]:
        con.execute(f"DROP TABLE IF EXISTS {t}")
    con.executescript(SCHEMA)
    con.commit()
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
    con.close()
    print("✅ 统一版 Schema 重建完成")
    print("   表:", tables)


if __name__ == "__main__":
    sys.exit(main())
