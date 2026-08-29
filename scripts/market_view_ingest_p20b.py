#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
market_view_ingest_p20b.py — P2.0B Market View Ingest 落地
===========================================================
把 market_view_parser_v1 的全量输出写入 analyst_daily_views（view_type='market'）。

输入：analyst_daily_views 已有 193 行（core_theme/trend/logic，69 个 analyst×date 组合）
输出：每天每分析师 1 条 view_type='market' 综合行，带 6 结构化列：
      market_direction / market_score / risk_level / position_bias / summary / raw_text

语义（用户锁定）：
  * content = 聚合原文（当天 core_theme+trend+logic，保持 daily_views 内容语义）
  * raw_text = 聚合原文（输入原文，与 content 同值，明确标注）
  * summary   = parser explain（含 direction/risk/bias evidence 短句 → Phase 2.1 解释层）
  * exclude 判定（P2.0D G5）：market_direction='UNKNOWN' 即 excluded（MV-4：STOCK_ONLY/UNKNOWN → 三轴 UNKNOWN + 排除聚合）
  * 幂等：INSERT OR IGNORE，UNIQUE(analyst_id, view_date, view_type)

用法：python3 scripts/market_view_ingest_p20b.py [--dry-run]
"""

import argparse
import hashlib
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from market_view_parser_v1 import parse_market_view, load_daily_view_text

DB = ROOT / "data" / "analyst_consensus.db"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    cur = con.cursor()

    # 69 组合（core_theme 全集）
    combos = cur.execute(
        "SELECT DISTINCT analyst_id, view_date FROM analyst_daily_views WHERE view_type='core_theme' ORDER BY analyst_id, view_date"
    ).fetchall()
    print(f"analyst×date 组合: {len(combos)}")

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    inserted = 0
    skipped = 0
    stats = {"direction": {}, "risk": {}, "bias": {}, "excluded": 0}

    for analyst_id, view_date in combos:
        raw = load_daily_view_text(str(DB), analyst_id, view_date)
        if raw is None:
            skipped += 1
            continue
        p = parse_market_view(raw)
        d, r, b = p["market_direction"], p["risk_level"], p["position_bias"]
        excluded = 1 if d == "UNKNOWN" else 0
        stats["direction"][d] = stats["direction"].get(d, 0) + 1
        stats["risk"][r] = stats["risk"].get(r, 0) + 1
        stats["bias"][b] = stats["bias"].get(b, 0) + 1
        stats["excluded"] += excluded

        # 当天 core_theme 行的 snapshot（lineage 参考）
        snap = cur.execute(
            "SELECT source_snapshot_id FROM analyst_daily_views WHERE analyst_id=? AND view_date=? AND view_type='core_theme'",
            (analyst_id, view_date)).fetchone()
        snap_id = snap[0] if snap and snap[0] is not None else None

        hash_src = f"{raw}|{d}|{r}|{b}|{view_date}|{analyst_id}"
        rh = hashlib.sha256(hash_src.encode()).hexdigest()

        if not args.dry_run:
            cur.execute(
                """INSERT OR IGNORE INTO analyst_daily_views
                   (analyst_id, view_date, view_type, content, source_snapshot_id, record_hash,
                    first_seen_at, last_seen_at, revision_no, created_at, updated_at,
                    market_direction, market_score, risk_level, position_bias, summary, raw_text)
                   VALUES (?,?,?,?,?,?,?,?,1,?,?,
                           ?,?,?,?,?,?)""",
                (analyst_id, view_date, "market", raw, snap_id, rh, now, now, now, now,
                 d, p["market_score"], r, b, p["explain"], raw),
            )
            if cur.rowcount > 0:
                inserted += 1
        else:
            inserted += 1

    if not args.dry_run:
        con.commit()
    total = cur.execute("SELECT COUNT(*) FROM analyst_daily_views WHERE view_type='market'").fetchone()[0]
    print(f"新增/预览 market 行: {inserted} | skipped(无原文): {skipped} | DB 当前 market 行: {total}")
    print(f"direction 分布: {stats['direction']}")
    print(f"risk 分布: {stats['risk']}")
    print(f"bias 分布: {stats['bias']}")
    print(f"excluded(direction=UNKNOWN): {stats['excluded']} | eligible: {len(combos) - stats['excluded']}")
    if args.dry_run:
        print("(dry-run 未写库)")
    con.close()


if __name__ == "__main__":
    main()
