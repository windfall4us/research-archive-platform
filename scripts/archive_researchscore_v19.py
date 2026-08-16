#!/usr/bin/env python3
"""资讯研究档案库 v1.9 - Research Score（研究综合分）引擎
Research Score = 事件强度30 + 十大模型35 + 技术状态20 + 资金状态15
  值不值得重点研究（非买入评分），含解释层 + 缺失条件 + 状态映射。
安全边界：只写 research_scores，不接交易状态机。
2026-08-12
"""
import json, sqlite3, sys, urllib.request
from datetime import datetime

DB = "/root/workspace/research_archive.db"
STOCKS_DB = "/root/stock-kanban/backend/stocks.db"
MODELS_API = "http://127.0.0.1:3100/api/models"
PARAM_VERSION = "v1.9.0"

# 状态映射
def score_status(s):
    if s >= 90: return "重点研究"
    if s >= 80: return "优先跟踪"
    if s >= 70: return "观察"
    if s >= 60: return "普通"
    return "忽略"

# 强模型加权（龙头接力/一柱擎天/N式倍量双涨停 权重高）
STRONG_MODELS = {"龙头接力", "一柱擎天", "N式倍量双涨停", "极值反转"}


def load_models():
    """{code: {final_score, model, matched[], missing[]}}"""
    try:
        req = urllib.request.Request(MODELS_API)
        data = json.loads(urllib.request.urlopen(req, timeout=6).read().decode())
        out = {}
        for c in (data.get("candidates") or []):
            out[str(c.get("code", ""))] = {
                "final_score": c.get("final_score") or 0,
                "model": c.get("model") or "",
                "matched": c.get("matched") or [],
                "missing": c.get("missing") or [],
            }
        return out
    except Exception as e:
        print("  模型接口失败:", e)
        return {}


def score_technical(price, ma8, ma60, status):
    """技术状态 20：趋势8 + 均线5 + 乖离4 + 位置3"""
    expl = []
    missing = []
    s = 0
    # 趋势 8
    if status == "多头主升":
        s += 8; expl.append(("趋势多头主升", 8))
    elif status == "震荡回踩":
        s += 5; expl.append(("趋势震荡回踩", 5))
    elif status == "空头规避":
        expl.append(("趋势空头规避", -6))
        s -= 6
    else:
        s += 3; expl.append(("趋势不明", 3))
    # 均线 5：price > ma8 > ma60 → 多头排列
    if price and ma8 and ma60:
        if price > ma8 > ma60:
            s += 5; expl.append(("短中长期均线多头排列", 5))
        elif price > ma8:
            s += 3; expl.append(("站上 MA8", 3))
        else:
            s += 1; expl.append(("价格低于 MA8", 1))
            missing.append("价格未站上 MA8")
    # 乖离 4：BIAS8 = (price-ma8)/ma8
    if price and ma8:
        bias = (price - ma8) / ma8
        if -0.05 <= bias <= 0.15:
            s += 4; expl.append(("BIAS8 乖离适中", 4))
        elif bias > 0.25:
            s += 1; expl.append(("BIAS8 乖离偏高", 1))
            missing.append("BIAS8 乖离偏高，短期回调风险")
        else:
            s += 2; expl.append(("乖离偏低", 2))
    # 位置 3：相对 MA60
    if price and ma60:
        if price > ma60:
            s += 3; expl.append(("价格在 MA60 上方", 3))
        else:
            s += 1; expl.append(("价格在 MA60 下方", 1))
            missing.append("价格未站上 MA60")
    return max(0, min(20, s)), expl, missing


def score_capital(pct_chg, mention_count):
    """资金状态 15：当日强度5 + 市场关注5 + 量能参考3 + 风险-3"""
    expl = []
    missing = []
    s = 0
    # 当日强度 5
    if pct_chg is not None:
        if pct_chg >= 3:
            s += 5; expl.append(("当日强势(+{:.1f}%)".format(pct_chg), 5))
        elif pct_chg >= 0:
            s += 3; expl.append(("当日平稳(+{:.1f}%)".format(pct_chg), 3))
        else:
            s += 1; expl.append(("当日回调({:.1f}%)".format(pct_chg), 1))
    # 市场关注 5（mention_count 资讯提及）
    if mention_count:
        if mention_count >= 100:
            s += 5; expl.append((f"高关注(提及{mention_count})", 5))
        elif mention_count >= 30:
            s += 3; expl.append((f"关注度中(提及{mention_count})", 3))
        else:
            s += 2; expl.append((f"关注度低(提及{mention_count})", 2))
    # 量能参考 3：暂无换手数据，用 pct_chg 幅度近似
    if pct_chg is not None and abs(pct_chg) >= 5:
        s += 3; expl.append(("大幅波动(活跃)", 3))
    else:
        s += 2; expl.append(("波动平稳", 2))
    # 异常风险 -3：空头规避
    return max(0, min(15, s)), expl, missing


def score_event(stock_events):
    """事件强度 30：事件评分10 + Momentum8 + 机构确认7 + 关联强度5
    综合多个事件（event_score 最高为主，momentum 加权），避免单事件偏差"""
    if not stock_events:
        return 0, [], ["暂无关联事件"]
    expl = []
    missing = []
    s = 0
    # 主事件：event_score 最高（研究价值优先于即时热度）
    top = max(stock_events, key=lambda e: (e.get("event_score") or 0, e.get("momentum_score") or 0))
    # 事件评分 10（用最佳事件分）
    es = top.get("event_score") or 0
    ev_pts = int(es / 100 * 10)
    s += ev_pts; expl.append((f"事件评分{es}", ev_pts))
    # Momentum 8（用最高热度）
    mom = max(e.get("momentum_score") or 0 for e in stock_events)
    mom_pts = int(mom / 100 * 8)
    s += mom_pts; expl.append((f"Momentum热度{mom}", mom_pts))
    # 机构确认 7（多事件机构并集）
    inst_n = top.get("inst_count") or 0
    s += min(7, inst_n * 2); expl.append((f"{inst_n}家机构确认", min(7, inst_n * 2)))
    if inst_n == 0:
        missing.append("暂无机构确认")
    # 关联强度 5（多事件取最强的直接受益关系）
    rels = [e.get("relation_type") or "" for e in stock_events]
    if "直接受益" in rels:
        s += 5; expl.append(("直接受益", 5))
    elif "产业链" in rels:
        s += 3; expl.append(("产业链受益", 3))
    else:
        s += 1
    return min(30, s), expl, missing


def research_state_of(research, change, momentum, model_score, status_label, has_prev):
    """研究状态（v1.9.1）：cold/warming/focused/confirmed/fading
    基于评分 + 变化趋势 + 热度 + 模型（非交易状态）
    has_prev=False（首次快照）时按当前绝对水平判定"""
    if not has_prev:
        # 首次评分：按当前水平
        if research >= 80:
            return "confirmed"
        if research >= 70:
            return "focused"
        if research >= 60:
            return "warming"
        return "cold"
    if status_label == "忽略" and change <= 0:
        return "cold"
    if change >= 15:
        return "confirmed" if (momentum >= 60 and model_score >= 20) else "warming"
    if research >= 80:
        return "confirmed"
    if change >= 5:
        return "warming"
    if change <= -8:
        return "fading"
    return "focused" if research >= 70 else ("warming" if change > 0 else "cold")


def build_change_reason(prev, cur):
    """评分变化原因（v1.9.1）：比较各维度生成解释"""
    reasons = []
    if prev is None:
        return [{"label": "首次评分", "delta": cur.get("research_score") or 0}]
    d_ev = (cur.get("event_score") or 0) - (prev.get("event_score") or 0)
    d_md = (cur.get("model_score") or 0) - (prev.get("model_score") or 0)
    d_te = (cur.get("technical_score") or 0) - (prev.get("technical_score") or 0)
    d_ca = (cur.get("capital_score") or 0) - (prev.get("capital_score") or 0)
    d_total = (cur.get("research_score") or 0) - (prev.get("research_score") or 0)
    if d_ev > 0:
        reasons.append({"label": f"事件强度提升 +{d_ev}（事件热度/机构增加）", "delta": d_ev})
    elif d_ev < 0:
        reasons.append({"label": f"事件强度回落 {d_ev}（热度/机构减少）", "delta": d_ev})
    if d_md > 0:
        reasons.append({"label": f"十大模型提升 +{d_md}（新增命中/完整度提高）", "delta": d_md})
    elif d_md < 0:
        reasons.append({"label": f"十大模型回落 {d_md}（模型条件变化）", "delta": d_md})
    if d_te > 0:
        reasons.append({"label": f"技术状态改善 +{d_te}（均线/趋势转好）", "delta": d_te})
    elif d_te < 0:
        reasons.append({"label": f"技术状态转弱 {d_te}（乖离/均线变化）", "delta": d_te})
    if d_ca > 0:
        reasons.append({"label": f"资金状态增强 +{d_ca}（量能/关注度提升）", "delta": d_ca})
    elif d_ca < 0:
        reasons.append({"label": f"资金状态减弱 {d_ca}（量能/关注度下降）", "delta": d_ca})
    if not reasons:
        reasons.append({"label": f"评分持平（{d_total >= 0 and '+' or ''}{d_total}）", "delta": d_total or 0})
    return reasons


def main():
    con = sqlite3.connect(DB)
    models = load_models()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = now[:10]

    # 要评分的股票：watch pool 候选 + 持仓 + 自选（从 stocks.db 全量 + 观察池）
    codes = set()
    try:
        scon = sqlite3.connect(STOCKS_DB)
        codes.update(str(r[0]) for r in scon.execute("SELECT symbol FROM stocks"))
        scon.close()
    except Exception:
        pass
    codes.update(str(r[0]) for r in con.execute("SELECT stock_code FROM event_watch_pool"))
    codes.update(str(r[0]) for r in con.execute("SELECT stock_code FROM event_stock_relation"))

    # 每日快照：只删除今天已算的（历史按天保留），再插入今天最新
    con.execute("DELETE FROM research_scores WHERE created_at LIKE ?", (today + "%",))

    created = 0
    for code in sorted(codes):
        # ── 个股信息 ──
        srow = None
        try:
            scon = sqlite3.connect(STOCKS_DB)
            srow = scon.execute("SELECT name, price, pct_chg, status, ma8, ma60, mention_count, relation_score FROM stocks WHERE symbol=?", (code,)).fetchone()
            scon.close()
        except Exception:
            pass
        name = srow[0] if srow else ""
        price = srow[1] if srow else None
        pct_chg = srow[2] if srow else None
        status = srow[3] if srow else ""
        ma8 = srow[4] if srow else None
        ma60 = srow[5] if srow else None
        mention = srow[6] if srow else 0
        relation_score = srow[7] if srow else None

        # ── 事件维度（该股关联事件按热度排序）──
        events = []
        for r in con.execute("""
            SELECT r.event_id, r.relation_type, r.impact_score, e.event_title,
                   e.event_score, e.momentum_score, e.status
            FROM event_stock_relation r JOIN event_clusters e ON e.event_id=r.event_id
            WHERE r.stock_code=? AND e.merge_status != 'manual_merged'
            ORDER BY e.momentum_score DESC LIMIT 3""", (code,)).fetchall():
            events.append({"event_id": r[0], "relation_type": r[1], "impact_score": r[2],
                           "event_title": r[3], "event_score": r[4], "momentum_score": r[5],
                           "status": r[6]})
        for ev in events:
            inst_n = con.execute("""SELECT COUNT(DISTINCT c.institution) FROM event_messages em
                JOIN message_classification c ON c.message_id=em.message_id
                WHERE em.event_id=? AND c.institution!='' AND c.institution IS NOT NULL""",
                (ev["event_id"],)).fetchone()[0]
            ev["inst_count"] = inst_n
        ev_score, ev_expl, ev_missing = score_event(events)

        # ── 十大模型维度（35）──
        md = models.get(code)
        m_expl, m_missing = [], []
        m_score = 0
        if md and md.get("final_score"):
            final = md["final_score"]
            matched = md.get("matched") or []
            # 模型命中数量：每命中1个 +5，最高25
            hit_base = min(25, len(matched) * 5)
            # 模型质量加权：强模型 +8
            strong_bonus = 8 if md.get("model") in STRONG_MODELS else 0
            # 完整度：completeness 近似（用 final_score 折算）
            completeness = min(5, int(final / 100 * 5))
            m_score = min(35, hit_base + strong_bonus + completeness)
            m_expl.append((f"命中{len(matched)}项模型条件", hit_base))
            if strong_bonus:
                m_expl.append((f"强模型{md['model']}", strong_bonus))
            m_expl.append((f"模型完整度{int(final)}%", completeness))
            if md.get("missing"):
                m_missing = [f"模型未满足: {x[:30]}" for x in md["missing"][:2]]
        else:
            # 未进候选：用 stocks.db relation_score/mention 折算基础市场强度分（0-10）
            base = 0
            if mention:
                base += min(6, int(mention / 40))
            if relation_score is not None:
                base += min(4, int((relation_score or 0) / 5))
            if base > 0:
                m_score = base
                m_expl.append((f"未进模型候选，市场强度基础分", base))
            else:
                m_expl.append(("未进十大模型候选", 0))
                m_missing.append("未进入十大模型候选扫描")

        # ── 技术维度（20）──
        t_score, t_expl, t_missing = score_technical(price, ma8, ma60, status)
        # ── 资金维度（15）──
        c_score, c_expl, c_missing = score_capital(pct_chg, mention)

        research = min(100, ev_score + m_score + t_score + c_score)
        status_label = score_status(research)

        # ── v1.9.1：与上一日快照比较（score_change + change_reason + research_state）──
        prev = con.execute("""SELECT research_score, event_score, model_score, technical_score, capital_score
            FROM research_scores WHERE stock_code=? AND created_at < ?
            ORDER BY created_at DESC, id DESC LIMIT 1""", (code, today + " 00:00:00")).fetchone()
        prev_dict = {"research_score": prev[0], "event_score": prev[1], "model_score": prev[2],
                     "technical_score": prev[3], "capital_score": prev[4]} if prev else None
        score_change = research - (prev_dict["research_score"] if prev_dict else 0)
        change_reasons = build_change_reason(prev_dict, {
            "research_score": research, "event_score": ev_score, "model_score": m_score,
            "technical_score": t_score, "capital_score": c_score})
        mom_now = events[0]["momentum_score"] if events else 0
        rstate = research_state_of(research, score_change, mom_now, m_score, status_label, prev_dict is not None)

        # ── 解释层 ──
        expl_all = ev_expl + m_expl + t_expl + c_expl
        missing_all = list(dict.fromkeys(ev_missing + m_missing + t_missing + c_missing))
        explanation = {
            "contributions": [{"label": x[0], "delta": x[1]} for x in expl_all if x[1] > 0],
            "penalties": [{"label": x[0], "delta": x[1]} for x in expl_all if x[1] < 0],
            "dims": {
                "event": {"score": ev_score, "max": 30},
                "model": {"score": m_score, "max": 35},
                "technical": {"score": t_score, "max": 20},
                "capital": {"score": c_score, "max": 15},
            },
        }
        con.execute("""INSERT INTO research_scores
            (stock_code, stock_name, event_id, event_score, model_score, technical_score,
             capital_score, research_score, score_status, explanation_json, missing_conditions,
             model_detail, event_title, momentum_score, parameter_version, created_at, updated_at,
             score_change, change_reason, research_state)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (code, name or "", events[0]["event_id"] if events else None,
             ev_score, m_score, t_score, c_score, research, status_label,
             json.dumps(explanation, ensure_ascii=False), json.dumps(missing_all, ensure_ascii=False),
             json.dumps(md or {}, ensure_ascii=False),
             events[0]["event_title"] if events else "",
             events[0]["momentum_score"] if events else 0,
             PARAM_VERSION, now, now,
             score_change, json.dumps(change_reasons, ensure_ascii=False), rstate))
        created += 1
    con.commit()

    print(f"✅ v1.9 Research Score: {created} 只股票（参数 {PARAM_VERSION}）")
    print("  状态分布:", dict(con.execute("SELECT score_status, COUNT(*) FROM research_scores WHERE created_at LIKE ? GROUP BY 1", (today + "%",)).fetchall()))
    print("  研究状态:", dict(con.execute("SELECT research_state, COUNT(*) FROM research_scores WHERE created_at LIKE ? GROUP BY 1", (today + "%",)).fetchall()))
    print("  变化分布:", dict(con.execute("""SELECT CASE WHEN score_change>=10 THEN '大涨≥10' WHEN score_change>=1 THEN '升1-9' WHEN score_change=0 THEN '持平' WHEN score_change>-10 THEN '降1-9' ELSE '大跌≤-10' END, COUNT(*) FROM research_scores WHERE created_at LIKE ? GROUP BY 1""", (today + "%",)).fetchall()))
    # Top 样本
    top = con.execute("""SELECT stock_code, stock_name, research_score, score_status,
        event_score, model_score, technical_score, capital_score, score_change, research_state
        FROM research_scores WHERE created_at LIKE ?
        ORDER BY research_score DESC LIMIT 10""", (today + "%",)).fetchall()
    print("  Top10:")
    for r in top:
        print(f"    {r[0]} {r[1]:<6} [{r[3]}] {r[2]}分({r[8]:+d}) [{r[9]}] = 事件{r[4]} + 模型{r[5]} + 技术{r[6]} + 资金{r[7]}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
