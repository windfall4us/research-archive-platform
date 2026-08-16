#!/usr/bin/env python3
"""资讯研究档案库 v1.8 - Event Watch Pool 候选生成器
事件 → 候选股票（研究层，非交易层）：
  规则：Momentum≥60 + 机构确认(research/trigger) + 直接受益/产业链 + 质量过滤(非空头规避)
  十模型评分融合：调 watchlist /api/models，命中候选股记 model_score
安全边界：只写 event_watch_pool，绝不写 positions / 交易状态。
2026-08-12
"""
import json, sqlite3, sys, urllib.request
from datetime import datetime

DB = "/root/workspace/research_archive.db"
MODELS_API = "http://127.0.0.1:3100/api/models"

# 状态机
STATUS_FLOW = ["EVENT_FOUND", "RESEARCH", "WATCH", "MODEL_CHECK", "TRIAL_READY"]

# 触发点 → 初始状态
TRIGGER_INIT = {
    "FIRST_INSTITUTION": "RESEARCH",   # 机构确认 → 至少研究态
    "CONSENSUS_BUILD": "RESEARCH",
    "HEAT_BREAKOUT": "EVENT_FOUND",
    "STOCK_EXPANSION": "EVENT_FOUND",
}

# 质量过滤：空头规避 / ST / 退市
BAD_STATUS = {"空头规避"}
BAD_NAME = ["ST", "*ST", "退市"]


def load_model_scores():
    """十模型候选评分：{code: {final_score, model, ...}}"""
    try:
        req = urllib.request.Request(MODELS_API)
        data = json.loads(urllib.request.urlopen(req, timeout=6).read().decode())
        out = {}
        for c in (data.get("candidates") or []):
            code = str(c.get("code", ""))
            out[code] = {
                "final_score": c.get("final_score") or 0,
                "model": c.get("model") or "",
                "resonance": c.get("model_resonance") or 0,
                "completeness": c.get("model_completeness") or 0,
                "matched": (c.get("matched") or [])[:4],
            }
        return out
    except Exception as e:
        print("  模型接口读取失败:", e)
        return {}


def main():
    con = sqlite3.connect(DB)
    model_scores = load_model_scores()
    print(f"  十模型候选 {len(model_scores)} 只")

    # 清空重建（幂等）
    con.execute("DELETE FROM event_watch_pool")

    # 2026-08-13 修复：消息时间存北京时间(CST)，now 必须用同一时区，
    # 否则 age 为负导致新老事件判定错误（方案B双门槛失效）
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    # 事件 × 股票关系 join（只取符合规则的）
    rows = con.execute("""
        SELECT e.event_id, e.event_title, e.momentum_score, e.momentum_peak, e.event_score,
               e.trigger_type, e.trigger_at, e.status,
               r.stock_code, r.stock_name, r.relation_type, r.impact_score, r.logic, r.mention_count,
               (SELECT MAX(m.date) FROM event_messages em
                JOIN raw_messages m ON m.chat_id||':'||m.message_id = em.message_id
                WHERE em.event_id = e.event_id) AS last_msg_date
        FROM event_clusters e
        JOIN event_stock_relation r ON r.event_id = e.event_id
        WHERE e.merge_status != 'manual_merged'
    """).fetchall()

    created = 0
    skipped = {"momentum": 0, "inst": 0, "relation": 0, "quality": 0}
    for eid, etitle, mom, peak, escore, trigger, trigger_at, estatus, \
        code, name, rel, impact, logic, mention, last_msg_date in rows:
        mom = mom or 0
        peak = peak or 0
        escore = escore or 0
        # ── 规则 1：热度门槛（2026-08-13 方案B：新老事件双门槛） ──
        # 新事件（首次出现 ≤48h）：当前 momentum ≥ 60（爆发窗口内看实时热度）
        # 老事件（>48h）：峰值 ≥ 60 且未 fading（曾热门、仍在研究窗口）
        # ⚠️ 用 first_seen 判断"新"，不用 last_msg（最后消息近≠新事件，可能是持续跟踪的 stable 事件）
        age_h = 999
        try:
            if trigger_at:
                age_h = (now - datetime.strptime(str(trigger_at)[:19], "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600
        except Exception:
            pass
        if age_h <= 48:
            heat_ok = mom >= 60
        else:
            heat_ok = peak >= 60 and estatus != "fading"
        if not heat_ok:
            skipped["momentum"] += 1
            continue
        # ── 规则 2：机构确认 ──
        inst_n = con.execute("""SELECT COUNT(DISTINCT c.institution) FROM event_messages em
            JOIN message_classification c ON c.message_id = em.message_id
            WHERE em.event_id=? AND c.institution != '' AND c.institution IS NOT NULL""",
            (eid,)).fetchone()[0]
        if inst_n < 1 and trigger != "FIRST_INSTITUTION":
            skipped["inst"] += 1
            continue
        # ── 规则 3：股票关系（排除 风险影响） ──
        if rel in ("风险影响", "竞争影响"):
            skipped["relation"] += 1
            continue
        # ── 规则 4：质量过滤 ──
        if (name and any(b in name for b in BAD_NAME)):
            skipped["quality"] += 1
            continue
        # stocks.db 状态检查 + 补名称（stocks.db 名称可能本身是代码，需从消息提取真实名）
        try:
            scon = sqlite3.connect("/root/stock-kanban/backend/stocks.db")
            st = scon.execute("SELECT status, name FROM stocks WHERE symbol=?", (code,)).fetchone()
            scon.close()
            if st:
                if st[0] in BAD_STATUS:
                    skipped["quality"] += 1
                    continue
                if not name and st[1] and st[1] != code:
                    name = st[1]
        except Exception:
            pass
        # 名称仍是代码或为空 → 从事件消息文本提取「XX（300491）」模式
        if not name or name == code:
            import re as _re
            mrow = con.execute("""SELECT r.raw_text FROM event_messages em
                JOIN raw_messages r ON r.chat_id||':'||r.message_id=em.message_id
                WHERE em.event_id=? AND r.raw_text LIKE ? LIMIT 1""",
                (eid, f"%（{code}）%")).fetchone()
            if mrow:
                m = _re.search(r'([\u4e00-\u9fa5]{2,8})（' + code + r'）', mrow[0] or "")
                if m:
                    name = m.group(1)
            if not name or name == code:
                mrow2 = con.execute("""SELECT r.raw_text FROM event_messages em
                    JOIN raw_messages r ON r.chat_id||':'||r.message_id=em.message_id
                    WHERE em.event_id=? AND r.raw_text LIKE ? LIMIT 1""",
                    (eid, f"%({code})%")).fetchone()
                if mrow2:
                    m = _re.search(r'([\u4e00-\u9fa5]{2,8})\(' + code + r'\)', mrow2[0] or "")
                    if m:
                        name = m.group(1)

        # ── 十模型评分融合 ──
        ms = model_scores.get(code, {})
        model_score = ms.get("final_score") or 0
        model_detail = json.dumps({"model": ms.get("model"), "resonance": ms.get("resonance"),
                                   "completeness": ms.get("completeness"), "matched": ms.get("matched")},
                                  ensure_ascii=False) if ms else ""
        # ── 状态：初始由触发点决定，模型通过 → MODEL_CHECK ──
        status = TRIGGER_INIT.get(trigger, "EVENT_FOUND")
        if ms:
            status = "MODEL_CHECK" if model_score >= 70 else "WATCH"
        # confidence：热度×关系×机构
        conf = round(min(0.95, 0.5 + mom / 200 + (0.1 if inst_n >= 2 else 0) + (0.1 if rel == "直接受益" else 0)), 2)
        con.execute("""INSERT OR REPLACE INTO event_watch_pool
            (event_id, stock_code, stock_name, status, trigger_source, momentum_score, event_score,
             model_score, model_detail, confidence, event_title, relation_type, impact_score, logic,
             created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (eid, code, name or "", status, trigger or "", mom, escore,
             model_score, model_detail, conf, etitle or "", rel, impact or 0, logic or "",
             now_str, now_str))
        created += 1

    # ── 2026-08-13 C1：队列上限 50（按模型分优先，超出剔除） ──
    POOL_LIMIT = 50
    total = con.execute("SELECT COUNT(*) FROM event_watch_pool").fetchone()[0]
    if total > POOL_LIMIT:
        con.execute("""DELETE FROM event_watch_pool WHERE pool_id IN (
            SELECT pool_id FROM event_watch_pool
            ORDER BY model_score DESC, momentum_score DESC, confidence DESC
            LIMIT -1 OFFSET ?
        )""", (POOL_LIMIT,))
        print(f"  ⚠️ 队列上限 {POOL_LIMIT}：剔除 {total - POOL_LIMIT} 条（保留模型分优先）")
    con.commit()

    print(f"✅ v1.8 观察池: {created} 条候选（跳过: {skipped}）")
    print("  状态分布:", dict(con.execute("SELECT status, COUNT(*) FROM event_watch_pool GROUP BY 1 ORDER BY 2 DESC").fetchall()))
    top = con.execute("""SELECT w.stock_code, w.stock_name, w.status, w.momentum_score, w.event_score,
        w.model_score, w.confidence, substr(w.event_title,1,24)
        FROM event_watch_pool w ORDER BY w.model_score DESC, w.momentum_score DESC LIMIT 10""").fetchall()
    print("  Top10 候选:")
    for r in top:
        ms = f"模型{r[5]:.0f}" if r[5] else "模型—"
        print(f"    {r[0]} {r[1]:<6} [{r[2]}] 热度{r[3]} 事件{r[4]} {ms} 置信{r[6]:.2f} ← {r[7]}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
