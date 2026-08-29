#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stock_theme_mapping_p22a.py — P2.2A Stock→Theme Mapping 正式管道（可重建、幂等）
===============================================================================
输入：
  * data/p22a/board_to_l2.json          —— 同花顺板块名 → 19 canonical L2（人工审阅过的规则产物）
  * data/p22a/constituents/concept/*.json —— 概念板块成分（MASTER_CONCEPT，主）
  * data/p22a/constituents/industry/*.json —— 行业板块成分（MASTER_INDUSTRY，辅）
  * scripts/theme_lexicon_p20c.json     —— 词典（theme_id / 关键词）
  * analyst_consensus.db                —— eligible 股票 + DIRECT theme mentions + 原文

输出：重建 stock_theme_mapping 表（DROP + CREATE + INSERT，幂等）

映射来源语义（用户 2026-08-30 锁定）：
  * MASTER_CONCEPT    同花顺概念板块（主）   confidence = min(0.60+0.05*(n-1), 0.85)
  * MASTER_INDUSTRY   同花顺行业板块（辅）   confidence = min(0.75+0.05*(n-1), 0.90)
  * DIRECT_CONTEXT    分析师话语同句语义绑定：强绑定(股票名⊃主题词)=0.62 / 邻接(≤3字)=0.60；同 record 共现不落表
  * MANUAL            人工确认（预留，seed 由用户确认后填写）

Top3 治理（排序语义优先，防概念板块倍增）：
  DIRECT_STRONG(100) > DIRECT_NEIGHBOR(95) > MASTER_INDUSTRY(90) > MASTER_CONCEPT(80)
  每只股票保留排序 top3 主题；其余行 confidence 置 0.50（<0.60 不参与 Heat）

用法：python3 scripts/stock_theme_mapping_p22a.py
"""

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "analyst_consensus.db"
P22 = ROOT / "data" / "p22a"
LEXICON = ROOT / "scripts" / "theme_lexicon_p20c.json"
VALID_FROM = "2026-08-30"

# 人工确认的 MANUAL 补充（用户确认后在此追加；当前留空待确认）
MANUAL_SEEDS = {}

SORT_PRIORITY = {"DIRECT_STRONG": 100.0, "DIRECT_NEIGHBOR": 95.0, "MASTER_INDUSTRY": 90.0, "MASTER_CONCEPT": 80.0}
HEAT_MIN = 0.60


def build_master(con, eligible):
    """从板块成分构建 MASTER_CONCEPT / MASTER_INDUSTRY 原始映射。"""
    board = json.load(open(P22 / "board_to_l2.json", encoding="utf-8"))
    by_tag = defaultdict(dict)  # tag -> board_code -> l2
    for k, v in board.items():
        tag, code = k.split("|")
        by_tag[tag][code] = v["l2"]
    tag_to_const = {
        "MASTER_CONCEPT": f"{P22}/constituents/concept",
        "MASTER_INDUSTRY": f"{P22}/constituents/industry",
    }
    out = defaultdict(lambda: {"MASTER_CONCEPT": 0, "MASTER_INDUSTRY": 0})
    for tag, l2map in by_tag.items():
        const_dir = tag_to_const.get(tag)
        if not const_dir:
            continue
        for code, l2 in l2map.items():
            fp = Path(const_dir) / f"{code}.json"
            if not fp.exists():
                continue
            d = json.load(open(fp, encoding="utf-8"))
            for it in d.get("data", {}).get("item", []):
                if it.get("ticker") in eligible:
                    out[(it["ticker"], l2)][tag] += 1
    return out


def master_conf(m):
    c = min(0.60 + 0.05 * (m["MASTER_CONCEPT"] - 1), 0.85) if m["MASTER_CONCEPT"] > 0 else 0
    i = min(0.75 + 0.05 * (m["MASTER_INDUSTRY"] - 1), 0.90) if m["MASTER_INDUSTRY"] > 0 else 0
    return {"MASTER_CONCEPT": round(c, 3), "MASTER_INDUSTRY": round(i, 3)}


def build_direct_context(con, eligible):
    """DIRECT_CONTEXT v2：同句语义绑定。强绑定=股票名⊃主题词(0.62)；邻接=≤3字且不在其他股票名内(0.60)。"""
    lex = json.load(open(LEXICON, encoding="utf-8"))
    tid_kw = {f"{l1k}_{l2k}": l2.get("keywords", []) for l1k, l1 in lex["l1"].items() for l2k, l2 in l1["l2"].items()}
    name2code = {n: c for c, n in con.execute(
        "SELECT DISTINCT stock_code, stock_name FROM analyst_stock_events WHERE event_id NOT IN (SELECT event_id FROM consensus_event_exclusions)").fetchall()
        if n and len(n) >= 3 and "*" not in n}
    sorted_names = sorted(name2code, key=len, reverse=True)
    mentions = con.execute("""
        SELECT t.theme_id, v.content FROM analyst_theme_mentions t
        LEFT JOIN analyst_daily_views v ON v.view_id = CAST(t.source_record_id AS INTEGER)
        WHERE t.mention_source='DIRECT' AND v.content IS NOT NULL""").fetchall()
    SENT_SPLIT = re.compile(r"[。！？；\n]|——")
    bindings = defaultdict(list)

    for tid, content in mentions:
        kws = [k for k in tid_kw.get(tid, []) if len(k) >= 2]
        if not kws:
            continue
        for sent in SENT_SPLIT.split(content):
            sent = sent.strip()
            if not sent:
                continue
            found = []
            for n in sorted_names:
                idx = sent.find(n)
                while idx != -1:
                    found.append((idx, n, name2code[n]))
                    idx = sent.find(n, idx + 1)
            if not found:
                continue
            kw_pos = [(m.start(), k) for k in kws for m in re.finditer(re.escape(k), sent)]
            for spos, sname, scode in found:
                strong = [k for k in kws if k in sname]
                if strong:
                    bindings[(scode, tid)].append((0.62, "STRONG", f"强绑定 {sname}⊃{strong[0]}"))
                    continue
                for kpos, k in kw_pos:
                    dist = kpos - spos if kpos > spos else spos - (kpos + len(k))
                    if dist <= 3:
                        other = [(p, n2) for p, n2, _ in found if n2 != sname]
                        if any(p <= kpos < p + len(n2) for p, n2 in other):
                            continue
                        bindings[(scode, tid)].append((0.60, "NEIGHBOR", f"邻接 {sname}~{k}"))
                        break
    out = []
    for (s, tid), entries in bindings.items():
        if tid == "TECH_GENERAL":
            continue
        conf, kind, note = max(entries, key=lambda x: x[0])
        out.append({"stock_code": s, "theme_id": tid, "mapping_source": "DIRECT_CONTEXT",
                    "confidence": conf, "note": note, "kind": kind})
    return out


def rebuild():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    eligible = {r[0] for r in cur.execute(
        "SELECT DISTINCT stock_code FROM analyst_stock_events WHERE event_id NOT IN (SELECT event_id FROM consensus_event_exclusions)")}

    # 1. MASTER 原始
    master = build_master(con, eligible)
    rows = []  # (stock, theme, source, conf, note)
    for (s, l2), m in master.items():
        confs = master_conf(m)
        if confs["MASTER_CONCEPT"] > 0:
            rows.append((s, l2, "MASTER_CONCEPT", confs["MASTER_CONCEPT"], "概念板块"))
        if confs["MASTER_INDUSTRY"] > 0:
            rows.append((s, l2, "MASTER_INDUSTRY", confs["MASTER_INDUSTRY"], "行业板块"))

    # 2. DIRECT_CONTEXT（内部 source 用 DIRECT_STRONG/DIRECT_NEIGHBOR 供排序；落库映射回枚举）
    dc = build_direct_context(con, eligible)
    for d in dc:
        rows.append((d["stock_code"], d["theme_id"], f"DIRECT_{d['kind']}", d["confidence"], d["note"]))

    # 3. MANUAL
    for (s, tid), conf in MANUAL_SEEDS.items():
        rows.append((s, tid, "MANUAL", conf, "人工确认"))

    # 4. Top3 治理（语义优先排序）
    by_stock = defaultdict(list)
    for s, tid, src, conf, note in rows:
        by_stock[s].append((tid, src, conf, note))
    final = []
    for s, items in by_stock.items():
        def sort_key(it):
            tid, src, conf, note = it
            pri = SORT_PRIORITY.get(src, 50)
            return -(pri + conf / 1000)
        items_sorted = sorted(items, key=sort_key)
        top3 = {t for t, _, _, _ in items_sorted[:3]}
        for tid, src, conf, note in items_sorted:
            if tid not in top3 and conf >= HEAT_MIN:
                conf = 0.50  # 超 Top3，不参与 Heat
            # 落库 source 映射回枚举
            db_src = {"DIRECT_STRONG": "DIRECT_CONTEXT", "DIRECT_NEIGHBOR": "DIRECT_CONTEXT"}.get(src, src)
            final.append((s, tid, db_src, conf, note))

    # 5. 重建表（幂等）
    cur.execute("DROP TABLE IF EXISTS stock_theme_mapping")
    cur.execute("""
        CREATE TABLE stock_theme_mapping (
            mapping_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code      TEXT NOT NULL,
            theme_id        TEXT NOT NULL,
            mapping_source  TEXT NOT NULL CHECK (mapping_source IN ('MANUAL','MASTER_CONCEPT','MASTER_INDUSTRY','DIRECT_CONTEXT')),
            confidence      REAL NOT NULL DEFAULT 0.6 CHECK (confidence >= 0 AND confidence <= 1),
            valid_from      TEXT NOT NULL,
            valid_to        TEXT,
            note            TEXT,
            UNIQUE(stock_code, theme_id, mapping_source, valid_from)
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_stm_stock ON stock_theme_mapping(stock_code)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_stm_theme ON stock_theme_mapping(theme_id)")
    cur.executemany("INSERT OR IGNORE INTO stock_theme_mapping (stock_code, theme_id, mapping_source, confidence, valid_from, note) VALUES (?,?,?,?,?,?)",
                    [(s, t, src, c, VALID_FROM, n) for s, t, src, c, n in final])
    con.commit()

    heat_stocks = {r[0] for r in cur.execute("SELECT DISTINCT stock_code FROM stock_theme_mapping WHERE confidence>=0.60")}
    tot = cur.execute("SELECT COUNT(*) FROM stock_theme_mapping").fetchone()[0]
    by_src = dict(cur.execute("SELECT mapping_source, COUNT(*) FROM stock_theme_mapping GROUP BY 1").fetchall())
    per = defaultdict(set)
    for r in cur.execute("SELECT stock_code, theme_id FROM stock_theme_mapping WHERE confidence>=0.60"):
        per[r[0]].add(r[1])
    from collections import Counter
    dist = Counter(len(v) for v in per.values())
    con.close()

    print(f"重建完成: 表 {tot} 行 | 按来源 {by_src}")
    print(f"参与 Heat 股票: {len(heat_stocks)}/{len(eligible)} = {len(heat_stocks)/len(eligible)*100:.1f}%")
    print(f"每股 Heat 主题分布: {dict(sorted(dist.items()))}")
    unmapped = sorted(eligible - heat_stocks)
    print(f"Unmapped {len(unmapped)}: {unmapped}")
    return 0 if len(heat_stocks) == len(eligible) - len(unmapped) else 1


if __name__ == "__main__":
    import sys
    sys.exit(rebuild())
