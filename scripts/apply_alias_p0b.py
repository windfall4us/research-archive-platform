#!/usr/bin/env python3
"""0B.3 步骤⑥→⑦: 写入已审核 ALIAS + 建立 OUT_OF_SCOPE 注册表。

用户审核结论（2026-08-28）:
- 批准写入 stock_aliases: 华虹公司→688347 / 宏景→301396 / ST闻泰→600745（3条）
- 中国金茂 → 不写 stock_aliases，归 OUT_OF_SCOPE（entity_type=STOCK, market_scope=NON_A_SHARE）
- 解析状态枚举统一: EXACT/ALIAS/CONTEXT/FUZZY/UNRESOLVED/OUT_OF_SCOPE
- 原 foreign 集（阿里巴巴/腾讯等）迁入 out_of_scope 注册表，统一 OUT_OF_SCOPE 语义

原则: UNRESOLVED = 理论上属A股但无法解析；OUT_OF_SCOPE = 已识别对象但不属A股解析范围。
"""
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path("/home/windfall/workspace/research-archive-platform")
DB = ROOT / "data/security_master.db"
BEIJING_TZ = timezone(timedelta(hours=8))
now = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")

con = sqlite3.connect(DB)

# 1) 建 out_of_scope 注册表（统一 OUT_OF_SCOPE 状态）
con.execute("""
CREATE TABLE IF NOT EXISTS out_of_scope (
  raw_name       TEXT PRIMARY KEY,
  entity_type    TEXT NOT NULL DEFAULT 'STOCK',
  market_scope   TEXT NOT NULL DEFAULT 'NON_A_SHARE',
  resolve_status TEXT NOT NULL DEFAULT 'OUT_OF_SCOPE',
  review_status  TEXT NOT NULL DEFAULT 'EXCLUDE',
  note           TEXT,
  created_at     TEXT
)""")

# 2) 写入 3 条已审核 ALIAS（校验代码必须在 stock_master）
approved_aliases = [
    ("华虹公司", "688347", "COMMON_NAME", 1.00),
    ("宏景",     "301396", "SHORT_NAME",  0.98),
    ("ST闻泰",   "600745", "NAME_VARIANT", 0.99),
]
for alias, code, atype, conf in approved_aliases:
    ok = con.execute("SELECT 1 FROM stock_master WHERE stock_code=?", (code,)).fetchone()
    if not ok:
        raise SystemExit(f"错误: 代码 {code} 不在 stock_master，拒绝写入 alias '{alias}'")
    con.execute("""INSERT OR REPLACE INTO stock_aliases
                   (alias, stock_code, alias_type, confidence, source, review_status, created_at, updated_at)
                   VALUES (?,?,?,?,?, 'CONFIRMED', ?, ?)""",
                (alias, code, atype, conf, "用户审核批准 2026-08-28", now, now))
    print(f"ALIAS 写入: {alias} → {code} ({atype}, conf={conf}, CONFIRMED)")

# 3) OUT_OF_SCOPE 注册表（中国金茂 + 原 foreign 集迁移）
out_of_scope_names = [
    ("中国金茂", "非A股标的(疑港股00817.HK/未上市)，不进Phase 0B A股Resolver"),
    ("阿里巴巴", "港股/中概，非A股"),
    ("腾讯",     "港股，非A股"),
    ("美团",     "港股，非A股"),
    ("拼多多",   "美股/中概，非A股"),
    ("京东",     "港股/美股，非A股"),
    ("百度",     "港股/美股，非A股"),
    ("网易",     "港股/美股，非A股"),
    ("小米",     "港股(01810)，非A股"),
    ("快手",     "港股(01024)，非A股"),
    ("理想汽车", "港股/美股，非A股"),
    ("蔚来",     "港股/美股，非A股"),
    ("小鹏汽车", "港股/美股，非A股"),
]
for name, note in out_of_scope_names:
    con.execute("""INSERT OR REPLACE INTO out_of_scope (raw_name, note, created_at)
                   VALUES (?,?,?)""", (name, note, now))
print(f"OUT_OF_SCOPE 注册表写入: {len(out_of_scope_names)} 条")

con.commit()

# 4) 验证
print("\n=== stock_aliases ===")
for r in con.execute("SELECT alias, stock_code, alias_type, confidence, review_status FROM stock_aliases"):
    print("  ", r)
print("=== out_of_scope ===")
for r in con.execute("SELECT raw_name, entity_type, market_scope, resolve_status FROM out_of_scope"):
    print("  ", r)
con.close()
