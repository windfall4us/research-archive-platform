#!/usr/bin/env python3
"""P1.1: 创建 Consensus Data Layer 空库（data/analyst_consensus.db）—— 只建结构。

8 表 + 唯一键 + 普通索引 + CHECK 枚举约束 + 统一 created_at/updated_at。
schema_version 用 PRAGMA user_version = 1 管理（用户 2026-08-28）。

本脚本幂等可重放：库已存在时先 DROP 再 CREATE（空库验收 ⑥），
不含任何数据导入 / ingest 逻辑。P1.2 才写 ingest。

用法: python3 scripts/create_consensus_schema_p1.py
"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data/analyst_consensus.db"
SCHEMA_VERSION = 2
# v1→v2 (2026-08-28, P1.2 前用户决策): ingest_runs 去掉 UNIQUE(source_snapshot_id, parser_version, resolver_version)
# → run_id 唯一主键 + 普通索引 idx_runs_snapshot_versions，允许同版本重复运行留下独立 run history（幂等重跑审计）。

DDL = """
-- ============ 1. analyst_profiles 分析师档案 ============
CREATE TABLE IF NOT EXISTS analyst_profiles (
    analyst_id    TEXT PRIMARY KEY,
    analyst_name  TEXT NOT NULL UNIQUE,
    style         TEXT CHECK (style IN ('LONG_TERM','SWING','SHORT','ULTRA_SHORT') OR style IS NULL OR style = ''),
    time_horizon  TEXT,
    source        TEXT NOT NULL DEFAULT 'vip0',
    topic_id      INTEGER,
    enabled       INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- ============ 2. source_snapshots 源快照（输入留痕） ============
CREATE TABLE IF NOT EXISTS source_snapshots (
    snapshot_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    source            TEXT NOT NULL DEFAULT 'vip0',
    snapshot_date     TEXT NOT NULL,
    captured_at       TEXT,
    page_generated_at TEXT,
    page_sha256       TEXT,
    raw_json_path     TEXT,
    record_count      INTEGER,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    UNIQUE (source, snapshot_date)
);

-- ============ 3. analyst_daily_views 每日观点 ============
CREATE TABLE IF NOT EXISTS analyst_daily_views (
    view_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    analyst_id         TEXT NOT NULL REFERENCES analyst_profiles(analyst_id),
    view_date          TEXT NOT NULL,
    view_type          TEXT NOT NULL CHECK (view_type IN ('core_theme','trend','logic')),
    content            TEXT NOT NULL,
    source_snapshot_id INTEGER REFERENCES source_snapshots(snapshot_id),
    record_hash        TEXT NOT NULL,
    first_seen_at      TEXT,
    last_seen_at       TEXT,
    revision_no        INTEGER NOT NULL DEFAULT 1,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    UNIQUE (analyst_id, view_date, view_type)
);

-- ============ 4. analyst_stock_events 操作事件（双轨第一轨，全 11 类） ============
CREATE TABLE IF NOT EXISTS analyst_stock_events (
    event_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_record_id  TEXT NOT NULL,          -- vip0:{analyst}:{date}:{entity}:action:{NNN}（role 不在身份内）
    logical_record_id TEXT NOT NULL,          -- vip0:{analyst}:{date}:{entity}（=0B.6 logical_key）
    role              TEXT NOT NULL CHECK (role IN ('daily_action','position_summary')),
    event_index       INTEGER NOT NULL,       -- 同 source_record_id 下第几个事件
    analyst_id        TEXT NOT NULL REFERENCES analyst_profiles(analyst_id),
    event_date        TEXT NOT NULL,
    temporal_type     TEXT NOT NULL CHECK (temporal_type IN ('TODAY','PAST','CURRENT_STATE','FUTURE_PLAN','CONDITIONAL','UNKNOWN')),
    stock_code        TEXT,
    stock_name        TEXT,
    raw_target        TEXT NOT NULL,
    action_type       TEXT NOT NULL CHECK (action_type IN ('BUY','ADD','LOW_BUY','TRIAL','HOLD','WATCH','DO_T','REDUCE','SELL','CLEAR','STOP_LOSS','UNKNOWN')),
    event_category    TEXT NOT NULL CHECK (event_category IN ('TRADE','OBSERVATION','STATE','COMPOSITE_TACTICAL','UNKNOWN')),
    action_status     TEXT NOT NULL CHECK (action_status IN ('EXECUTED','INTENDED','CONDITIONAL','POSITION_STATE','UNKNOWN')),
    stance            TEXT CHECK (stance IS NULL OR stance IN ('FOLLOW','AVOID','WAIT','POSITIVE','NEGATIVE')),
    direction         TEXT,
    raw_action        TEXT,
    raw_logic         TEXT,
    resolve_method    TEXT NOT NULL CHECK (resolve_method IN ('EXACT','ALIAS','CONTEXT','FUZZY','UNRESOLVED','OUT_OF_SCOPE')),
    match_confidence  REAL,
    source_snapshot_id INTEGER REFERENCES source_snapshots(snapshot_id),
    record_hash       TEXT NOT NULL,
    first_seen_at     TEXT,
    last_seen_at      TEXT,
    revision_no       INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    UNIQUE (source_record_id, event_index)     -- 幂等锚点
);
CREATE INDEX IF NOT EXISTS idx_events_analyst_date  ON analyst_stock_events (analyst_id, event_date);
CREATE INDEX IF NOT EXISTS idx_events_code_date     ON analyst_stock_events (stock_code, event_date);
CREATE INDEX IF NOT EXISTS idx_events_action_date   ON analyst_stock_events (action_type, event_date);
CREATE INDEX IF NOT EXISTS idx_events_logical       ON analyst_stock_events (logical_record_id);

-- ============ 5. analyst_position_snapshots 持仓快照（双轨第二轨） ============
CREATE TABLE IF NOT EXISTS analyst_position_snapshots (
    snapshot_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    analyst_id        TEXT NOT NULL REFERENCES analyst_profiles(analyst_id),
    snapshot_date     TEXT NOT NULL,
    stock_code        TEXT,
    stock_name        TEXT,
    raw_target        TEXT NOT NULL,
    position_state    TEXT NOT NULL DEFAULT 'HOLDING' CHECK (position_state = 'HOLDING'),
    raw_action        TEXT,
    raw_logic         TEXT,
    source_record_id  TEXT NOT NULL,
    logical_record_id TEXT NOT NULL,
    resolve_method    TEXT NOT NULL CHECK (resolve_method IN ('EXACT','ALIAS','CONTEXT','FUZZY','UNRESOLVED','OUT_OF_SCOPE')),
    source_snapshot_id INTEGER REFERENCES source_snapshots(snapshot_id),
    record_hash       TEXT NOT NULL,
    first_seen_at     TEXT,
    last_seen_at      TEXT,
    revision_no       INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    UNIQUE (analyst_id, snapshot_date, source_record_id)
);
CREATE INDEX IF NOT EXISTS idx_pos_analyst_date ON analyst_position_snapshots (analyst_id, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_pos_code_date    ON analyst_position_snapshots (stock_code, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_pos_logical      ON analyst_position_snapshots (logical_record_id);

-- ============ 6. analyst_theme_mentions 主题提及（只落原始，热度 Phase 2） ============
CREATE TABLE IF NOT EXISTS analyst_theme_mentions (
    mention_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    analyst_id        TEXT NOT NULL REFERENCES analyst_profiles(analyst_id),
    mention_date      TEXT NOT NULL,
    theme_name        TEXT NOT NULL,
    theme_id          TEXT,                    -- Phase 2 归一化，本阶段 NULL
    mention_type      TEXT CHECK (mention_type IN ('core_theme','logic_inline','ops')),
    source_record_id  TEXT NOT NULL,
    raw_context       TEXT,
    source_snapshot_id INTEGER REFERENCES source_snapshots(snapshot_id),
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    UNIQUE (analyst_id, mention_date, theme_name, source_record_id)
);

-- ============ 7. record_revisions Revision 落库（历史不可物理覆盖） ============
CREATE TABLE IF NOT EXISTS record_revisions (
    revision_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    source_record_id  TEXT NOT NULL,           -- 细粒度锚点（ADDED/REMOVED/MODIFIED 作用对象）
    logical_record_id TEXT NOT NULL,           -- 粗粒度逻辑组（跨表共用）
    table_name        TEXT NOT NULL,
    snapshot_date     TEXT NOT NULL,
    detected_at       TEXT NOT NULL,
    revision_no       INTEGER NOT NULL,
    change_type       TEXT NOT NULL CHECK (change_type IN ('ADDED','REMOVED','UNCHANGED','MODIFIED')),
    severity          TEXT NOT NULL CHECK (severity IN ('ROLE','TEXT','SEVERE')),
    old_hash          TEXT,
    new_hash          TEXT,
    old_value         TEXT,                    -- JSON 快照（旧值永不删除）
    new_value         TEXT,                    -- JSON
    changed_fields_json TEXT,                  -- JSON 数组
    source_snapshot_id INTEGER REFERENCES source_snapshots(snapshot_id),
    created_at        TEXT NOT NULL,
    UNIQUE (source_record_id, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_rev_logical ON record_revisions (logical_record_id, snapshot_date);

-- ============ 8. ingest_runs 摄入批次（幂等 + 可重放；v2 允许同版本重跑独立留痕） ============
CREATE TABLE IF NOT EXISTS ingest_runs (
    run_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    source_snapshot_id     INTEGER NOT NULL REFERENCES source_snapshots(snapshot_id),
    parser_version         TEXT NOT NULL,
    resolver_version       TEXT NOT NULL,
    schema_version         TEXT NOT NULL,
    started_at             TEXT NOT NULL,
    finished_at            TEXT,
    status                 TEXT NOT NULL CHECK (status IN ('running','success','failed')),
    source_record_count    INTEGER,
    parsed_event_count     INTEGER,
    inserted_event_count   INTEGER,
    skipped_existing_count INTEGER,
    error_count            INTEGER,
    result_hash            TEXT,
    errors                 TEXT,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_snapshot_versions ON ingest_runs (source_snapshot_id, parser_version, resolver_version);
"""


def main() -> int:
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    try:
        con.executescript(DDL)
        con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        con.commit()

        # 汇总
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        n_views = con.execute("PRAGMA user_version").fetchone()[0]
        print(f"DB: {DB}")
        print(f"tables ({len(tables)}): {tables}")
        print(f"PRAGMA user_version = {n_views}")
        print("空库结构就绪（未导入任何数据）")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
