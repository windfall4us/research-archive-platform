#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
theme_mention_extract_v1.py — P2.0C Theme Mention Ingest (DIRECT mentions 第一版)
=================================================================================
输入：analyst_daily_views.view_type='core_theme'（每天每分析师 1 行核心主题原文）
输出：analyst_theme_mentions 表（mention_type='core_theme', mention_source='DIRECT'）

设计（用户 2026-08-30 锁定，第一版克制）：
  * 只做 DIRECT theme mentions —— 原文直接命中的概念/板块词；个股名不属于 DIRECT（Phase 2.2 才做 INFERRED_FROM_STOCK）
  * L1 大方向 / L2 主题 两级归一化；L3 保留扩展位
  * raw_theme 永远保留原文命中词（theme_name 列）；normalized_theme 存 L2 名
  * stance 判定：命中词上下文窗口 ±18 字情感词打分（POS/NEG 计数差）—— 宁 NEUTRAL 勿反转
  * source lineage = source_record_id(→daily_view.view_id) + source_snapshot_id
  * 幂等：INSERT ... ON CONFLICT DO NOTHING，UNIQUE(analyst_id, mention_date, theme_name, source_record_id) 防重跑

用法：
  python3 theme_mention_extract_v1.py --dry-run    # 预览，不写库
  python3 theme_mention_extract_v1.py --fill       # 正式填库
"""

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEXICON = ROOT / "scripts" / "theme_lexicon_p20c.json"
DB = ROOT / "data" / "analyst_consensus.db"

WINDOW = 18  # stance 上下文窗口（命中词前后字符数）


def build_matcher(lex):
    """keyword -> (l1_id, l1_name, l2_id, l2_name)，长词优先"""
    kw_map = {}
    for l1_id, l1 in lex["l1"].items():
        for l2_id, l2 in l1["l2"].items():
            for kw in l2["keywords"]:
                if kw not in kw_map:  # 先到先得（TECH 先于 MED 等）
                    kw_map[kw] = (l1_id, l1["name"], l2_id, l2["name"])
    # 按长度降序：长词优先匹配
    ordered = sorted(kw_map.items(), key=lambda kv: (-len(kv[0]), kv[0]))
    return kw_map, ordered


def extract_mentions(content, kw_map, ordered):
    """对一条原文提取 DIRECT theme mentions（重叠取最长词，泛科技兜底）"""
    hits = []  # (start, end, kw, l1_id, l1_name, l2_id, l2_name)
    for kw, meta in ordered:
        for m in re.finditer(re.escape(kw), content):
            hits.append((m.start(), m.end(), kw, meta[0], meta[1], meta[2], meta[3]))
    if not hits:
        return []
    # 重叠区间贪心：按 start 升序、len 降序，取不重叠的最长覆盖
    hits.sort(key=lambda h: (h[0], -len(h[2])))
    chosen = []
    covered_until = -1
    for h in hits:
        if h[0] < covered_until:
            continue
        # 同位置更长的词已经在前面（len 降序），直接取
        chosen.append(h)
        covered_until = h[1]
    # 泛科技兜底：已有具体 L2 命中的 record 丢弃 GENERAL 命中
    specific = [c for c in chosen if c[5] != "GENERAL"]
    if specific:
        chosen = [c for c in chosen if c[5] != "GENERAL"]
    # 同 record 内同 theme_name 合并（保留首个命中，避免撞 UNIQUE 丢数据）
    seen, dedup = set(), []
    for c in chosen:
        if c[2] in seen:
            continue
        seen.add(c[2])
        dedup.append(c)
    return dedup


def stance_for(content, start, end, lex, cache):
    """上下文窗口情感打分（情感词不跨句读）：>0 POSITIVE / <0 NEGATIVE / =0 NEUTRAL"""
    lo, hi = max(0, start - WINDOW), min(len(content), end + WINDOW)
    # 截断到最近的句读，避免跨句情感污染
    sep = "。！？；\n"
    for i in range(start - 1, lo - 1, -1):
        if content[i] in sep:
            lo = i + 1
            break
    for i in range(end, hi):
        if content[i] in sep:
            hi = i
            break
    ctx = content[lo:hi]
    if ctx in cache:
        return cache[ctx][0], ctx
    pos = sum(1 for w in lex["stance_positive"] if w in ctx)
    neg = sum(1 for w in lex["stance_negative"] if w in ctx)
    s = "POSITIVE" if pos > neg else ("NEGATIVE" if neg > pos else "NEUTRAL")
    cache[ctx] = (s, ctx)
    return s, ctx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fill", action="store_true")
    args = ap.parse_args()

    lex = json.load(open(LEXICON, encoding="utf-8"))
    kw_map, ordered = build_matcher(lex)
    con = sqlite3.connect(DB)
    cur = con.cursor()

    rows = cur.execute(
        "SELECT view_id, analyst_id, view_date, content, source_snapshot_id FROM analyst_daily_views WHERE view_type='core_theme' ORDER BY analyst_id, view_date"
    ).fetchall()

    mentions = []
    ctx_cache = {}
    for view_id, analyst_id, view_date, content, snap_id in rows:
        for (start, end, kw, l1_id, l1_name, l2_id, l2_name) in extract_mentions(content, kw_map, ordered):
            stance, ctx = stance_for(content, start, end, lex, ctx_cache)
            mentions.append({
                "analyst_id": analyst_id,
                "mention_date": view_date,
                "theme_name": kw,               # raw_theme（原文命中词）
                "theme_id": f"{l1_id}_{l2_id}",  # 归一化 id
                "normalized_theme": l2_name,
                "l1": l1_name,
                "l2": l2_name,
                "stance": stance,
                "mention_type": "core_theme",
                "mention_source": "DIRECT",
                "source_record_id": str(view_id),  # lineage → analyst_daily_views.view_id
                "raw_context": ctx,
                "source_snapshot_id": snap_id,
            })

    # ---- 统计 ----
    print(f"core_theme 行数: {len(rows)} | 生成 DIRECT mentions: {len(mentions)}")
    print(f"  每行平均 mention: {len(mentions)/len(rows):.2f}")
    print(f"  L1 分布: {dict(Counter(m['l1'] for m in mentions))}")
    print(f"  L2 分布: {dict(Counter(m['l2'] for m in mentions))}")
    print(f"  stance 分布: {dict(Counter(m['stance'] for m in mentions))}")
    print(f"  每分析师 mention 数: {dict(sorted(Counter(m['analyst_id'] for m in mentions).items()))}")
    no_theme = [r for r in rows if not any(True for _ in extract_mentions(r[3], kw_map, ordered))]
    print(f"  无 DIRECT mention 的行: {len(no_theme)} / {len(rows)}")
    for r in no_theme:
        print(f"    {r[1]} {r[2]}: {r[3][:50]}")

    print("\n--- 代表性样本（每条含 stance/context）---")
    for m in mentions[:28]:
        print(f"[{m['analyst_id']} {m['mention_date']}] {m['theme_id']}({m['theme_name']}) stance={m['stance']}")
        print(f"    ctx: …{m['raw_context']}…")

    if args.fill:
        cur.executemany(
            """INSERT OR IGNORE INTO analyst_theme_mentions
               (analyst_id, mention_date, theme_name, theme_id, normalized_theme, l1, l2, stance,
                mention_type, mention_source, source_record_id, raw_context, source_snapshot_id, created_at, updated_at)
               VALUES (:analyst_id, :mention_date, :theme_name, :theme_id, :normalized_theme, :l1, :l2, :stance,
                       :mention_type, :mention_source, :source_record_id, :raw_context, :source_snapshot_id,
                       datetime('now'), datetime('now'))""",
            mentions,
        )
        con.commit()
        n = cur.execute("SELECT COUNT(*) FROM analyst_theme_mentions").fetchone()[0]
        print(f"\n✅ 已填库，analyst_theme_mentions 当前行数: {n}")
    con.close()


if __name__ == "__main__":
    main()
