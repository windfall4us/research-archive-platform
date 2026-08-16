#!/usr/bin/env python3
"""资讯研究档案库 v1.7 - Event Momentum 计算器
六维加权（小时级）：新增消息速度25% + 新增独立来源20% + 新增机构20%
                      + 新增股票映射15% + 机构响应速度10% + 持续时间衰减10%
生成 event_momentum 小时快照 + 动态状态迁移 + 事件触发点。
不影响 event_score / stock_relation / 持仓逻辑。
2026-08-12
"""
import json, sqlite3, sys
from datetime import datetime, timedelta
from collections import defaultdict

DB = "/root/workspace/research_archive.db"

# 触发点阈值
TRIGGER = {
    "FIRST_INSTITUTION": {"label": "机构首次确认", "desc": "事件首次出现机构观点"},
    "STOCK_EXPANSION": {"label": "股票映射扩展", "desc": "关联股票显著增加"},
    "CONSENSUS_BUILD": {"label": "机构共识形成", "desc": "多家机构观点一致"},
    "HEAT_BREAKOUT": {"label": "热度突破", "desc": "Momentum 突破 70 且加速"},
}


def hour_bucket(ts):
    """2026-08-12 08:45:30 → 2026-08-12 08:00"""
    try:
        return (ts or "")[:13] + ":00"
    except Exception:
        return ""


def main():
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM event_momentum")

    # 2026-08-13 修复：消息时间存北京时间(CST)，now 用同一时区（否则 idle_h 异常）
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)

    # ── 1. 每个事件的消息（按时间） ──
    rows = con.execute("""
        SELECT em.event_id, r.date, c.institution, c.content_type, c.message_role,
               n.stock_codes_json
        FROM event_messages em
        JOIN raw_messages r ON r.chat_id || ':' || r.message_id = em.message_id
        LEFT JOIN message_classification c ON c.message_id = em.message_id
        LEFT JOIN normalized_messages n ON n.message_id = em.message_id
        ORDER BY r.date
    """).fetchall()

    # event_id -> {bucket -> {msg, srcs, insts, stocks}}
    events = defaultdict(lambda: defaultdict(lambda: {"msg": 0, "srcs": set(), "insts": set(), "stocks": set()}))
    for eid, date, inst, ct, role, codes_json in rows:
        b = hour_bucket(date)
        if not b:
            continue
        ev = events[eid][b]
        ev["msg"] += 1
        src = inst or "社群"
        ev["srcs"].add(src)
        if inst:
            ev["insts"].add(inst)
        try:
            codes = json.loads(codes_json or "[]")
            for c in codes:
                ev["stocks"].add(c)
        except Exception:
            pass

    # ── 2. 每事件累计 + momentum 计算 ──
    total_events = 0
    for eid, buckets in events.items():
        sorted_buckets = sorted(buckets.keys())
        cum_msg = cum_inst = cum_stock = 0
        prev_inst = 0
        prev_score = 0
        peak = 0
        triggers = []  # (trigger_type, bucket, 描述)
        first_inst_bucket = None
        for i, b in enumerate(sorted_buckets):
            d = buckets[b]
            cum_msg += d["msg"]
            cum_inst = max(cum_inst, len(d["insts"]))  # 累计机构 = 该桶及以前 union？用全局累计
            cum_stock = max(cum_stock, len(d["stocks"]))
            # 更精确累计：需要从第一桶到现在 union —— 简化：逐桶累加新机构/新股票
        # 重新按顺序累计（上面简化有误，重来）
        seen_insts, seen_stocks, seen_srcs = set(), set(), set()
        for i, b in enumerate(sorted_buckets):
            d = buckets[b]
            new_insts = d["insts"] - seen_insts
            new_stocks = d["stocks"] - seen_stocks
            new_srcs = d["srcs"] - seen_srcs
            seen_insts |= d["insts"]
            seen_stocks |= d["stocks"]
            seen_srcs |= d["srcs"]
            # ── 六维计算 ──
            # ① 新增消息速度 25%（该小时消息数，4+ 满分）
            v1 = min(25, int(d["msg"] / 4 * 25))
            # ② 新增独立来源 20%（新增 3+ 满分）
            v2 = min(20, int(len(new_srcs) / 3 * 20))
            # ③ 新增机构 20%（新增 2+ 满分）
            v3 = min(20, int(len(new_insts) / 2 * 20))
            # ④ 新增股票映射 15%（新增 4+ 满分）
            v4 = min(15, int(len(new_stocks) / 4 * 15))
            # ⑤ 机构响应速度 10%：首个机构出现早 → 满分；每延迟 2h 减 2 分
            v5 = 10
            if new_insts and first_inst_bucket is None:
                first_inst_bucket = b
                # 距第一桶小时差
                try:
                    f = datetime.strptime(sorted_buckets[0], "%Y-%m-%d %H:%M")
                    fi = datetime.strptime(b, "%Y-%m-%d %H:%M")
                    lag_h = (fi - f).total_seconds() / 3600
                    v5 = max(0, int(10 - lag_h * 2))
                except Exception:
                    v5 = 8
            elif first_inst_bucket is None:
                v5 = 10 if i == 0 else 6  # 机构还没出现，响应分保守
            # ⑥ 持续时间衰减 10%：事件 <6h 满分，每 6h 减 2 分（最低 2）
            try:
                span_h = (datetime.strptime(b, "%Y-%m-%d %H:%M") - datetime.strptime(sorted_buckets[0], "%Y-%m-%d %H:%M")).total_seconds() / 3600
            except Exception:
                span_h = 0
            v6 = max(2, int(10 - span_h / 6 * 2))
            score = min(100, v1 + v2 + v3 + v4 + v5 + v6)
            peak = max(peak, score)
            con.execute("""INSERT OR REPLACE INTO event_momentum
                (event_id, bucket_hour, momentum_score, msg_count, src_count, inst_count, stock_count,
                 cum_msg, cum_inst, cum_stock)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (eid, b, score, d["msg"], len(new_srcs), len(new_insts), len(new_stocks),
                 len(seen_srcs), len(seen_insts), len(seen_stocks)))
            # ── 触发点检测 ──
            if new_insts and first_inst_bucket == b:
                triggers.append(("FIRST_INSTITUTION", b, f"机构首次确认：{'/'.join(list(new_insts)[:3])}"))
            if len(new_stocks) >= 3:
                triggers.append(("STOCK_EXPANSION", b, f"新增 {len(new_stocks)} 只股票映射"))
            if len(seen_insts) >= 3 and len(new_insts) >= 1:
                triggers.append(("CONSENSUS_BUILD", b, f"{len(seen_insts)} 家机构持续关注"))
            if score >= 70 and score > prev_score + 10:
                triggers.append(("HEAT_BREAKOUT", b, f"Momentum {prev_score}→{score}"))
            prev_score = score
        # 当前 momentum = 最后一个桶的分数；状态动态判定
        last_b = sorted_buckets[-1]
        row = con.execute("SELECT momentum_score FROM event_momentum WHERE event_id=? AND bucket_hour=?",
                          (eid, last_b)).fetchone()
        last_score = row[0] if row else 0
        last_msg = buckets[last_b]["msg"]
        # 距最后一条消息多久
        last_msg_time = con.execute("""SELECT MAX(r.date) FROM event_messages em
            JOIN raw_messages r ON r.chat_id||':'||r.message_id=em.message_id WHERE em.event_id=?""", (eid,)).fetchone()[0]
        idle_h = 999
        try:
            idle_h = (now - datetime.strptime(last_msg_time[:19], "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600
        except Exception:
            pass
        # 状态：closed(>120h) / fading(>12h无新增) / heating(近期增速) / emerging(新) / stable
        status = "stable"
        if idle_h >= 120:
            status = "closed"
        elif idle_h >= 12:
            status = "fading"
        elif idle_h <= 4 and last_score >= 60 and last_msg >= 2:
            status = "heating"
        elif len(sorted_buckets) <= 2 and last_score < 50:
            status = "emerging"
        # 触发点：取最早那个作为主触发；无机构时降级到股票扩展/热度突破
        trigger_type = ""
        trigger_at = ""
        if triggers:
            # 优先机构首次确认 > 热度突破 > 共识 > 股票扩展
            prio = {"FIRST_INSTITUTION": 0, "HEAT_BREAKOUT": 1, "CONSENSUS_BUILD": 2, "STOCK_EXPANSION": 3}
            triggers.sort(key=lambda t: (prio.get(t[0], 9), t[1]))
            trigger_type = triggers[0][0]
            trigger_at = triggers[0][1]
        elif seen_stocks:
            # 无机构但有股票映射 → STOCK_EXPANSION
            trigger_type = "STOCK_EXPANSION"
            trigger_at = sorted_buckets[0]
        elif peak >= 50:
            trigger_type = "HEAT_BREAKOUT"
            trigger_at = sorted_buckets[0]
        con.execute("""UPDATE event_clusters SET momentum_score=?, momentum_peak=?, status=?, trigger_type=?, trigger_at=?
            WHERE event_id=?""", (last_score, peak, status, trigger_type, trigger_at, eid))
        total_events += 1
    con.commit()

    print(f"✅ v1.7 Momentum: {total_events} 事件")
    print("  状态分布:", dict(con.execute("SELECT status, COUNT(*) FROM event_clusters GROUP BY 1").fetchall()))
    print("  触发点分布:", dict(con.execute("SELECT COALESCE(trigger_type,'(无)'), COUNT(*) FROM event_clusters GROUP BY 1 ORDER BY 2 DESC").fetchall()))
    top = con.execute("""SELECT event_title, momentum_score, momentum_peak, status, trigger_type, trigger_at
        FROM event_clusters ORDER BY momentum_score DESC LIMIT 8""").fetchall()
    print("  当前热度 Top8:")
    for r in top:
        print(f"    [{r[1]}分|{r[3]}] {r[0][:30]} | 峰值{r[2]} | 触发:{r[4] or '-'} {r[5] or ''}")
    # 小时曲线样本
    print("  AI服务器事件(1474) 小时曲线:")
    for r in con.execute("""SELECT bucket_hour, momentum_score, msg_count, inst_count, stock_count
        FROM event_momentum WHERE event_id=1474 ORDER BY bucket_hour""").fetchall():
        bar = "█" * max(1, int(r[1] / 10))
        print(f"    {r[0][11:16]} {bar:<10} {r[1]}分 消息{r[2]} 机构{r[3]} 股票{r[4]}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
