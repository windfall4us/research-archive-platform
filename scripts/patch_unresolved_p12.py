#!/usr/bin/env python3
"""P1.2 收尾：UNRESOLVED 裁决补丁（用户 2026-08-28 裁决，hithink symbol.search 权威验证）。

分类：
  A. A 股名称变体（错别字/截断/旧简称/简称）→ stock_aliases（CONFIRMED，alias→master 已存在 code）
  B. ETF / 港美股 / 中概 / 新股申购 → out_of_scope（OOS，不进 A 股事件）
  C. 概念/组合词 → 由 ingest_consensus_p12.classify_entity 的 THEME/MARKET 规则扩展处理
     （代码层面：CONCEPTS / MARKET_EXTRA 集合，见 ingest_consensus_p12.py）
  D. 无法可靠识别（上海宜众/泰金科技/瑞图/玉衡药业/紫光[歧义]）→ 保留 UNRESOLVED，不猜测

禁 FUZZY：所有 alias 均有 hithink 权威标的命中 + master 已验证；无命中/歧义的一律不补。

用法: python3 scripts/patch_unresolved_p12.py
"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MASTER_DB = ROOT / "data/security_master.db"

# A. 名称变体 → 标准代码（hithink symbol.search --asset-type a-share 命中 + master 确认）
ALIASES = [
    # (alias原文, stock_code, 说明)
    ("盛科通信",   "688702", "简称（标准: 盛科通信-U）"),
    ("深中华",     "000017", "简称（标准: 深中华A）"),
    ("京东方A",    "000725", "半角A变体（标准: 京东方Ａ全角）"),
    ("京东方",     "000725", "简称"),
    ("杨杰科技",   "300373", "错别字（标准: 扬杰科技）"),
    ("矩光科技",   "688167", "错别字（标准: 炬光科技）"),
    ("茂来光学",   "688502", "错别字（标准: 茂莱光学）"),
    ("聚和股份",   "688503", "旧简称（标准: 聚和材料）"),
    ("金建米业",   "600127", "错别字（标准: 金健米业）"),
    ("贝瑞卡",     "000710", "错别字/缺字（标准: 贝瑞基因）"),
    ("富祥药业",   "300497", "旧简称（2026-05-15 更名富祥股份，公告确认）"),
    ("亨通光D",    "600487", "截断（标准: 亨通光电）"),
    ("华虹",       "688347", "简称（标准: 华虹宏力）"),
    ("长鑫",       "688825", "简称（标准: 长鑫科技，2026 上市）"),
    ("宇树科技",   "688836", "简称（标准: 宇树科技-W）"),
    ("铜管(海亮股份)", "002203", "主题(标的) 描述（海亮股份）"),
]

# B. 非 A 股个股 → out_of_scope
OUT_OF_SCOPE = [
    "513120",              # 港股通互联网 ETF（51 开头，ETF 非个股）
    "513120(ETF)",
    "沪深300ETF(510300)",  # ETF
    "科创50ETF(588000)",   # ETF
    "中芯H",               # 中芯国际 H 股（港股）
    "药明生物",            # 港股 2269
    "药明合联",            # 港股 2268
    "安踏",                # 港股 2020
    "阿里",                # 港股/中概 9988
    "天博申购(新股)",       # 新股申购（非 A 股标的）
]


def main() -> int:
    con = sqlite3.connect(MASTER_DB)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        con.execute("BEGIN")
        now = "2026-08-28T00:00:00"
        added_alias = 0
        for alias, code, note in ALIASES:
            # 防重（幂等）
            exists = con.execute("SELECT 1 FROM stock_aliases WHERE alias=?", (alias,)).fetchone()
            if exists:
                print(f"  alias 已存在跳过: {alias}")
                continue
            if not con.execute("SELECT 1 FROM stock_master WHERE stock_code=?", (code,)).fetchone():
                print(f"  !! master 缺 code {code}（{alias}），跳过")
                continue
            con.execute(
                "INSERT INTO stock_aliases (alias, stock_code, alias_type, confidence, source, review_status, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (alias, code, "NAME_VARIANT", 1.0, f"p12_unresolved_review|{note}", "CONFIRMED", now, now))
            added_alias += 1

        added_oos = 0
        for raw in OUT_OF_SCOPE:
            exists = con.execute("SELECT 1 FROM out_of_scope WHERE raw_name=?", (raw,)).fetchone()
            if exists:
                print(f"  oos 已存在跳过: {raw}")
                continue
            con.execute("INSERT INTO out_of_scope (raw_name) VALUES (?)", (raw,))
            added_oos += 1
        con.commit()
        print(f"alias 新增 {added_alias} 条；out_of_scope 新增 {added_oos} 条")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
