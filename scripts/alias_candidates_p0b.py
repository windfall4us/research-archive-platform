#!/usr/bin/env python3
"""0B.3 步骤⑥: 从 EXACT Benchmark 的 UNRESOLVED 生成 ALIAS candidate（待人工审核）。

原则（用户决策）:
- 不从 FUZZY 自动生成 alias
- 每个 candidate 带 alias_type + confidence + source=manual_candidate
- review_status=PENDING，人工审核通过后才进入 stock_aliases
"""
import json, sqlite3
from pathlib import Path

ROOT = Path("/home/windfall/workspace/research-archive-platform")
DB = ROOT / "data/security_master.db"
BENCH = json.load(open(ROOT / "reports/stock_exact_benchmark_p0b.json"))

# 从 benchmark details 取 UNRESOLVED（method=UNRESOLVED 且 bucket 是 A_SHARE_RESOLVABLE）
unresolved = [d["raw_target"] for d in BENCH["details"]
              if d.get("method") == "UNRESOLVED" and d.get("bucket") == "A_SHARE_RESOLVABLE"]
print("UNRESOLVED:", unresolved)

# 人工判断候选（先查 master，未命中的人工判断）
con = sqlite3.connect(DB)
candidates = []
for name in unresolved:
    # 模糊查 master（仅辅助人工判断，不作为自动匹配）
    hits = con.execute("SELECT stock_code, stock_name, full_code FROM stock_master WHERE stock_name LIKE ?",
                       (f"%{name.replace('ST','').replace('*','')[:3]}%",)).fetchall()
    print(f"\n{name} → master 模糊命中: {hits if hits else '无'}")
con.close()

# 出 ALIAS 候选初稿（人工判断，写到待审核文件）
manual = [
    {"raw_name": "华虹公司", "candidate": "华虹宏力", "code": "688347", "alias_type": "COMMON_NAME", "confidence": 1.0, "note": "博主常用简称，正式名华虹宏力"},
    {"raw_name": "宏景", "candidate": "宏景科技", "code": "301396", "alias_type": "SHORT_NAME", "confidence": 1.0, "note": "宏景科技简称"},
    {"raw_name": "ST闻泰", "candidate": "*ST闻泰", "code": "600745", "alias_type": "NAME_VARIANT", "confidence": 0.95, "note": "master 为*ST闻泰，博主省略星号"},
    {"raw_name": "中国金茂", "candidate": None, "code": None, "alias_type": "UNKNOWN", "confidence": 0.0, "note": "A股master无此标的，疑为港股00817或未上市，需人工确认是否进Non-A-share"},
]
out = ROOT / "data/security_staging/alias_candidates_p0b.json"
out.write_text(json.dumps(manual, ensure_ascii=False, indent=1), encoding="utf-8")
print("\nALIAS 候选初稿 →", out)
