#!/usr/bin/env python3
"""0B.3 步骤③: 校验 raw_a_share_full.json → 写入 security_master.db stock_master。

校验项（用户首轮要求）: 总记录数/代码唯一性/名称空值/重复代码/重复名称/交易所识别/证券类型/A股数/非A股数/异常代码
通过标准: 无重复代码、无名称空值、A股占绝大多数 → 写入 master
"""
import json, sqlite3, re
from pathlib import Path

RAW = Path("/home/windfall/workspace/research-archive-platform/data/security_staging/raw_a_share_full.json")
DB = Path("/home/windfall/workspace/research-archive-platform/data/security_master.db")

rows = json.loads(RAW.read_text(encoding="utf-8"))
report = {}
report["total"] = len(rows)

# 字段完整性
codes = [r.get("ticker") for r in rows]
names = [r.get("name") for r in rows]
report["empty_code"] = sum(1 for c in codes if not c)
report["empty_name"] = sum(1 for n in names if not n)

# 唯一性
from collections import Counter
code_dup = [c for c, n in Counter(codes).items() if n > 1]
name_dup = [n for n, cnt in Counter(names).items() if cnt > 1]
report["dup_code_count"] = len(code_dup)
report["dup_code_samples"] = code_dup[:10]
report["dup_name_count"] = len(name_dup)
report["dup_name_samples"] = name_dup[:10]

# 交易所
report["exchange_dist"] = dict(Counter(r.get("exchange") for r in rows))

# 证券类型
report["asset_type_dist"] = dict(Counter(r.get("asset_type") for r in rows))

# 代码格式异常（A股: 6位数字）
bad_code = [c for c in codes if c and not re.fullmatch(r"\d{6}", str(c))]
report["bad_code_count"] = len(bad_code)
report["bad_code_samples"] = bad_code[:10]

# A股数量 = 6位代码 + exchange in SH/SZ/BJ
a_share = [r for r in rows if re.fullmatch(r"\d{6}", str(r.get("ticker", ""))) and r.get("exchange") in ("SH", "SZ", "BJ")]
report["a_share_count"] = len(a_share)
report["non_a_share_count"] = len(rows) - len(a_share)

print(json.dumps(report, ensure_ascii=False, indent=1))

# 通过标准
pass_ = (report["empty_code"] == 0 and report["empty_name"] == 0
         and report["dup_code_count"] == 0 and report["bad_code_count"] == 0)
print("\n校验:", "✅ PASS" if pass_ else "❌ FAIL")

if pass_:
    con = sqlite3.connect(DB)
    for r in a_share:
        code = r["ticker"]
        name = r["name"]
        exch = r["exchange"]
        full = r.get("thscode") or f"{code}.{'SH' if exch=='SH' else 'SZ' if exch=='SZ' else 'BJ'}"
        con.execute("""INSERT OR REPLACE INTO stock_master
            (stock_code, stock_name, exchange, full_code, security_type, list_status, source, source_updated_at, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,NULL,datetime('now'),datetime('now'))""",
            (code, name, exch, full, "STOCK", "LISTED", "hithink"))
    con.commit()
    n = con.execute("select count(*) from stock_master").fetchone()[0]
    con.execute("INSERT INTO security_master_meta (source, source_version, imported_at, record_count, content_hash) VALUES (?,?,datetime('now'),?,?)",
                ("hithink", "a-share-v1", n, "pending"))
    con.commit()
    con.close()
    print(f"已写入 stock_master: {n} 条 A 股")
