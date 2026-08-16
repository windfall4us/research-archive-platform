#!/usr/bin/env python3
"""资讯研究档案库 · 数据库初始化（完整建库脚本）
创建全部 19 张基础表（含各版本迁移列），幂等可重复执行。
复刻时第一步运行：python3 archive_schema_init.py
"""
import sqlite3, sys

DB = "/tmp/v14/replica/research_archive.db"  # 复刻时改为你的路径


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    # ═══ 原始层 ═══
    cur.execute("""CREATE TABLE IF NOT EXISTS raw_messages (
        chat_id TEXT NOT NULL,
        message_id INTEGER NOT NULL,
        date TEXT,
        from_user TEXT,
        reply_to_message_id INTEGER,
        source_topic TEXT,
        msg_type TEXT,
        raw_text TEXT,
        relative_image_path TEXT,
        raw_json TEXT,
        imported_at TEXT,
        PRIMARY KEY (chat_id, message_id)
    )""")

    # ═══ 归一化层 ═══
    cur.execute("""CREATE TABLE IF NOT EXISTS normalized_messages (
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
        normalized_at TEXT,
        normalized_hash TEXT
    )""")

    # ═══ 分类层（含 v1.4 迁移列）═══
    cur.execute("""CREATE TABLE IF NOT EXISTS message_classification (
        message_id TEXT PRIMARY KEY,
        source_topic TEXT,
        primary_category TEXT,
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
        classified_at TEXT,
        vision_summary TEXT,
        detected_category TEXT,
        vision_entities TEXT,
        importance_score INTEGER DEFAULT 1,
        action_value TEXT DEFAULT '忽略',
        impact_scope TEXT DEFAULT '行业',
        content_type TEXT,
        content_subtype TEXT,
        ingest_source TEXT,
        original_source TEXT,
        institution TEXT,
        research_team TEXT,
        industry TEXT,
        themes_json TEXT,
        message_role TEXT,
        research_value INTEGER DEFAULT 0,
        confidence_score REAL DEFAULT 0.5,
        review_reason_detail TEXT
    )""")

    # ═══ 研报归并层 ═══
    cur.execute("""CREATE TABLE IF NOT EXISTS report_series (
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
        status TEXT DEFAULT 'active'
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS report_versions (
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
        created_at TEXT,
        extraction_model_version TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS report_occurrences (
        occurrence_id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id INTEGER,
        message_id TEXT,
        appeared_at TEXT,
        is_primary INTEGER DEFAULT 0,
        is_duplicate INTEGER DEFAULT 0,
        duplicate_type TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS report_messages (
        report_id INTEGER,
        message_id TEXT,
        sequence_no INTEGER,
        is_first INTEGER DEFAULT 0,
        is_last INTEGER DEFAULT 0,
        PRIMARY KEY (report_id, message_id)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS report_entities (
        report_id INTEGER,
        entity_type TEXT,
        entity_id TEXT,
        entity_name TEXT,
        relation_type TEXT DEFAULT '重点关注',
        entity_source TEXT DEFAULT 'llm',
        entity_confidence TEXT DEFAULT 'high',
        PRIMARY KEY (report_id, entity_type, entity_id)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS report_verifications (
        verification_id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id INTEGER,
        event_date TEXT,
        event_type TEXT,
        event_text TEXT,
        verification_status TEXT DEFAULT '待验证',
        evidence_source TEXT,
        created_at TEXT
    )""")

    # ═══ 事件层 ═══
    cur.execute("""CREATE TABLE IF NOT EXISTS event_clusters (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_title TEXT,
        event_type TEXT,
        industry TEXT,
        themes_json TEXT,
        occurred_date TEXT,
        stock_codes_json TEXT,
        source_count INTEGER DEFAULT 0,
        institution_count INTEGER DEFAULT 0,
        importance_score INTEGER DEFAULT 0,
        first_seen_at TEXT,
        last_seen_at TEXT,
        entity_key TEXT UNIQUE,
        created_at TEXT,
        event_score INTEGER DEFAULT 0,
        status TEXT DEFAULT 'emerging',
        cluster_confidence REAL DEFAULT 0.9,
        update_count INTEGER DEFAULT 1,
        merge_status TEXT DEFAULT 'auto',
        momentum_score INTEGER DEFAULT 0,
        momentum_peak INTEGER DEFAULT 0,
        trigger_type TEXT,
        trigger_at TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS event_messages (
        event_id INTEGER,
        message_id TEXT,
        message_role TEXT,
        PRIMARY KEY (event_id, message_id)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS event_momentum (
        event_id INTEGER NOT NULL,
        bucket_hour TEXT NOT NULL,
        momentum_score INTEGER DEFAULT 0,
        msg_count INTEGER DEFAULT 0,
        src_count INTEGER DEFAULT 0,
        inst_count INTEGER DEFAULT 0,
        stock_count INTEGER DEFAULT 0,
        cum_msg INTEGER DEFAULT 0,
        cum_inst INTEGER DEFAULT 0,
        cum_stock INTEGER DEFAULT 0,
        PRIMARY KEY (event_id, bucket_hour)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS event_stock_relation (
        event_id INTEGER NOT NULL,
        stock_code TEXT NOT NULL,
        stock_name TEXT,
        relation_type TEXT DEFAULT '产业链',
        source TEXT DEFAULT 'auto',
        confidence REAL DEFAULT 0.6,
        impact_score INTEGER DEFAULT 0,
        logic TEXT,
        mention_count INTEGER DEFAULT 1,
        updated_at TEXT,
        PRIMARY KEY (event_id, stock_code)
    )""")

    # ═══ 研究队列 ═══
    cur.execute("""CREATE TABLE IF NOT EXISTS event_watch_pool (
        pool_id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        stock_code TEXT NOT NULL,
        stock_name TEXT,
        status TEXT DEFAULT 'EVENT_FOUND',
        trigger_source TEXT,
        momentum_score INTEGER DEFAULT 0,
        event_score INTEGER DEFAULT 0,
        model_score REAL DEFAULT 0,
        model_detail TEXT,
        confidence REAL DEFAULT 0.5,
        event_title TEXT,
        relation_type TEXT,
        impact_score INTEGER DEFAULT 0,
        logic TEXT,
        review_note TEXT,
        created_at TEXT,
        updated_at TEXT,
        UNIQUE (event_id, stock_code)
    )""")

    # ═══ 评分/结论/验证 ═══
    cur.execute("""CREATE TABLE IF NOT EXISTS research_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        stock_code TEXT NOT NULL,
        stock_name TEXT,
        event_id INTEGER,
        event_score INTEGER DEFAULT 0,
        model_score INTEGER DEFAULT 0,
        technical_score INTEGER DEFAULT 0,
        capital_score INTEGER DEFAULT 0,
        research_score INTEGER DEFAULT 0,
        score_status TEXT,
        explanation_json TEXT,
        missing_conditions TEXT,
        model_detail TEXT,
        event_title TEXT,
        momentum_score INTEGER DEFAULT 0,
        parameter_version TEXT,
        created_at TEXT,
        updated_at TEXT,
        score_change INTEGER DEFAULT 0,
        change_reason TEXT,
        research_state TEXT DEFAULT 'cold'
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS research_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        stock_code TEXT NOT NULL,
        stock_name TEXT,
        summary TEXT,
        positive_factors TEXT,
        risk_factors TEXT,
        missing_conditions TEXT,
        research_score INTEGER DEFAULT 0,
        research_state TEXT,
        suggestion TEXT,
        parameter_version TEXT,
        created_at TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS research_validation (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        stock_code TEXT NOT NULL,
        stock_name TEXT,
        research_score INTEGER DEFAULT 0,
        score_status TEXT,
        research_state TEXT,
        event_id INTEGER,
        event_title TEXT,
        trigger_date TEXT NOT NULL,
        base_price REAL,
        t1_date TEXT, t1_pct REAL,
        t3_date TEXT, t3_pct REAL,
        t5_date TEXT, t5_pct REAL,
        max_up REAL,
        max_drawdown REAL,
        result TEXT DEFAULT 'pending',
        validation_note TEXT,
        system_version TEXT,
        parameter_version TEXT,
        created_at TEXT,
        updated_at TEXT,
        UNIQUE (stock_code, trigger_date, parameter_version)
    )""")

    # ═══ 每日报告（预留）═══
    cur.execute("""CREATE TABLE IF NOT EXISTS daily_reports (
        daily_report_id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_date TEXT UNIQUE,
        summary TEXT,
        market_view TEXT,
        main_topics TEXT,
        risk_notes TEXT,
        source_message_count INTEGER DEFAULT 0,
        created_at TEXT
    )""")

    # 索引
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_mc_content_type ON message_classification(content_type)",
        "CREATE INDEX IF NOT EXISTS idx_esr_stock ON event_stock_relation(stock_code)",
        "CREATE INDEX IF NOT EXISTS idx_mom_event ON event_momentum(event_id)",
        "CREATE INDEX IF NOT EXISTS idx_wp_status ON event_watch_pool(status)",
        "CREATE INDEX IF NOT EXISTS idx_rv_stock ON research_validation(stock_code)",
        "CREATE INDEX IF NOT EXISTS idx_rs_stock ON research_scores(stock_code)",
    ]:
        cur.execute(idx)

    con.commit()
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%' ORDER BY name").fetchall()]
    print(f"✅ 数据库初始化完成：{len(tables)} 张表")
    for t in tables:
        print(f"  - {t}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
