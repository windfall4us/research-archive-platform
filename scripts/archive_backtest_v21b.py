#!/usr/bin/env python3
"""v2.1b - 历史回填验证（backtest mode）
对历史事件（08-09~08-11）用当前 RS 近似回放到事件日期作为 T 日，
用 kline 验证后续表现 → 立即可得 hit/miss 样本。
注意：这是近似回测（用当前评分代理当时），真实前瞻验证从明日 T+1 开始累积。
"""
import json, sqlite3, sys
from datetime import datetime

DB = "/root/workspace/research_archive.db"
KLINE = "/root/vip1_reports/kline_data.json"
SYSTEM_VERSION = "v2.0.0-bt"

HIT = 5.0
MISS = -5.0


def load_kline():
    d = json.load(open(KLINE))
    out = {}
    for code, info in (d.get("kline_data") or {}).items():
        bars = {}
        for b in (info.get("kline_history") or []):
            bars[b["trade_date"]] = {"close": b.get("close"), "high": b.get("high"), "low": b.get("low")}
        out[code] = bars
    return out


def main():
    con = sqlite3.connect(DB)
    kline = load_kline()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 历史事件（08-09 ~ 08-11）+ 关联股票 + 当前 RS
    rows = con.execute("""
        SELECT e.event_id, e.event_title, e.occurred_date, r.stock_code, r.stock_name,
               rs.research_score, rs.score_status, rs.research_state
        FROM event_clusters e
        JOIN event_stock_relation r ON r.event_id = e.event_id
        LEFT JOIN research_scores rs ON rs.stock_code = r.stock_code
        WHERE e.occurred_date < '2026-08-12'
          AND e.merge_status != 'manual_merged'
          AND rs.research_score IS NOT NULL
        ORDER BY e.occurred_date, rs.research_score DESC
    """).fetchall()

    inserted = 0
    for eid, etitle, tdate, code, name, rscore, status, state in rows:
        bars = kline.get(code)
        if not bars:
            continue
        # T 日 = 事件日期后的第一个交易日（事件日可能为周末/休市）
        all_dates = sorted(bars.keys())
        tdates = [d for d in all_dates if d >= tdate]
        if not tdates:
            continue
        tdate = tdates[0]
        if tdate not in bars:
            continue
        base = bars[tdate]["close"]
        if not base:
            continue
        dates = all_dates
        after = [d for d in dates if d > tdate]
        if len(after) < 2:
            continue
        t1 = after[0]
        t3 = after[2] if len(after) >= 3 else None
        t5 = after[4] if len(after) >= 5 else None
        window = after[:5]
        highs = [bars[d]["high"] for d in window if bars[d].get("high")]
        lows = [bars[d]["low"] for d in window if bars[d].get("low")]
        max_up = round((max(highs) / base - 1) * 100, 2) if highs else 0
        max_dd = round((min(lows) / base - 1) * 100, 2) if lows else 0
        if t3 is None:
            result = "pending"
        elif max_up >= HIT:
            result = "hit"
        elif max_dd <= MISS:
            result = "miss"
        else:
            result = "flat"
        note = f"回测[{tdate}]"
        if t1:
            note += f" T+1:{t1} {((bars[t1]['close']/base)-1)*100:+.1f}%"
        if t3:
            note += f" T+3:{t3} {((bars[t3]['close']/base)-1)*100:+.1f}%"
        # 存在则更新，否则插入（unique: stock+trigger+param）
        cur = con.execute("""SELECT id FROM research_validation
            WHERE stock_code=? AND trigger_date=? AND parameter_version='v1.9.0-bt'""",
            (code, tdate)).fetchone()
        if cur:
            con.execute("""UPDATE research_validation SET
                research_score=?, score_status=?, research_state=?, event_id=?, event_title=?,
                t1_date=?, t1_pct=?, t3_date=?, t3_pct=?, t5_date=?, t5_pct=?,
                max_up=?, max_drawdown=?, result=?, validation_note=?, updated_at=?
                WHERE id=?""",
                (rscore, status or "", state or "", eid, etitle or "",
                 t1, round((bars[t1]["close"] / base - 1) * 100, 2),
                 t3, round((bars[t3]["close"] / base - 1) * 100, 2) if t3 else None,
                 t5, round((bars[t5]["close"] / base - 1) * 100, 2) if t5 else None,
                 max_up, max_dd, result, note, now, cur[0]))
        else:
            con.execute("""INSERT INTO research_validation
                (stock_code, stock_name, research_score, score_status, research_state,
                 event_id, event_title, trigger_date, base_price,
                 t1_date, t1_pct, t3_date, t3_pct, t5_date, t5_pct,
                 max_up, max_drawdown, result, validation_note,
                 system_version, parameter_version, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (code, name or "", rscore, status or "", state or "", eid, etitle or "", tdate,
                 round(base, 2), t1, round((bars[t1]["close"] / base - 1) * 100, 2),
                 t3, round((bars[t3]["close"] / base - 1) * 100, 2) if t3 else None,
                 t5, round((bars[t5]["close"] / base - 1) * 100, 2) if t5 else None,
                 max_up, max_dd, result, note, SYSTEM_VERSION, "v1.9.0-bt", now, now))
        inserted += 1
    con.commit()

    print(f"✅ v2.1b 历史回填: {inserted} 条")
    print("  结果分布:", dict(con.execute("SELECT result, COUNT(*) FROM research_validation GROUP BY 1").fetchall()))
    print("  命中率（RS≥70 已回测）:")
    for r in con.execute("""SELECT result, COUNT(*) FROM research_validation
        WHERE research_score >= 70 AND parameter_version='v1.9.0-bt' GROUP BY 1""").fetchall():
        print(f"    RS≥70 {r[0]}: {r[1]}")
    # 高分回测样本
    top = con.execute("""SELECT stock_code, stock_name, research_score, trigger_date, t1_pct, t3_pct,
        max_up, max_drawdown, result FROM research_validation
        WHERE research_score >= 70 AND parameter_version='v1.9.0-bt'
        ORDER BY research_score DESC LIMIT 12""").fetchall()
    print("  RS≥70 回测样本:")
    for r in top:
        print(f"    {r[0]} {r[1]:<6} RS{r[2]} @{r[3]} | T+1:{r[4]}% T+3:{r[5]}% | up:{r[6]}% dd:{r[7]}% [{r[8]}]")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
