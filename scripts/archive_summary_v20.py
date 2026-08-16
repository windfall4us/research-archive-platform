#!/usr/bin/env python3
"""资讯研究档案库 v2.0 - Research Summary 研究结论生成器
基于 research_scores 生成自然语言研究判断：优势/风险/缺失/建议（非买入建议）
安全边界：只写 research_summary，不生成交易信号。
2026-08-12
"""
import json, sqlite3, sys
from datetime import datetime

DB = "/root/workspace/research_archive.db"
PARAM_VERSION = "v2.0.0"

# 研究状态 → 建议
STATE_SUGGEST = {
    "confirmed": "研究条件完整，保持重点关注，等待交易系统独立确认",
    "focused": "处于聚焦状态，跟踪事件与模型是否进一步确认",
    "warming": "研究热度上升中，等待模型/技术条件配合",
    "cold": "当前研究价值有限，暂不列入优先研究",
    "fading": "热度回落，关注是否出现新的催化",
}

# 状态 → 中文
STATE_CN = {"cold": "冷启动", "warming": "升温中", "focused": "聚焦", "confirmed": "确认", "fading": "降温"}


def build_summary(rs):
    """生成研究判断（v2.0）"""
    code = rs["stock_code"]
    name = rs["stock_name"] or code
    rscore = rs["research_score"]
    ev = rs["event_score"] or 0
    md = rs["model_score"] or 0
    te = rs["technical_score"] or 0
    ca = rs["capital_score"] or 0
    state = rs["research_state"] or "cold"
    expl = rs.get("explanation") or {}
    missing = rs.get("missing") or []
    event_title = rs.get("event_title") or ""
    mom = rs.get("momentum_score") or 0

    # 优势因素（贡献最大的 3 项）
    contribs = sorted(expl.get("contributions") or [], key=lambda x: -x.get("delta", 0))
    positives = [{"label": c.get("label", ""), "delta": c.get("delta", 0)} for c in contribs[:4]]
    # 风险因素（扣分项 + 明显短板维度）
    risks = [{"label": p.get("label", ""), "delta": p.get("delta", 0)} for p in (expl.get("penalties") or [])]
    if te < 10:
        risks.append({"label": "技术状态偏弱（未站稳均线/趋势未确认）", "delta": 0})
    if md < 15:
        risks.append({"label": "十大模型确认不足（未进候选或命中少）", "delta": 0})
    if ev < 15:
        risks.append({"label": "事件驱动强度不足", "delta": 0})

    # 自然语言摘要
    parts = []
    if event_title:
        parts.append(f"事件「{event_title[:30]}」")
        if mom >= 60:
            parts.append(f"当前热度 {mom}")
    if ev >= 20:
        parts.append("事件驱动强")
    if md >= 25:
        parts.append("十大模型高确认")
    if te >= 15:
        parts.append("技术形态良好")
    elif te < 10:
        parts.append("技术待确认")
    summary = "；".join(parts) if parts else "研究条件一般，缺乏明显催化"

    # 建议（非买入）
    suggestion = STATE_SUGGEST.get(state, "保持研究观察")
    if rscore >= 80:
        suggestion = "优先跟踪，等待交易系统（十模型/持仓）独立信号确认"
    elif rscore >= 70:
        suggestion = "列入观察，跟踪事件是否持续升温与模型确认"
    return {
        "stock_code": code, "stock_name": name,
        "summary": f"{name}：{summary}。",
        "positive_factors": positives,
        "risk_factors": risks,
        "missing_conditions": missing[:4],
        "research_score": rscore,
        "research_state": state,
        "state_cn": STATE_CN.get(state, state),
        "suggestion": suggestion,
        "dims": {"event": ev, "model": md, "technical": te, "capital": ca},
    }


def main():
    con = sqlite3.connect(DB)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = now[:10]

    # 每日快照：删当天重建（历史按天保留）
    con.execute("DELETE FROM research_summary WHERE created_at LIKE ?", (today + "%",))

    rows = con.execute("""SELECT stock_code, stock_name, research_score, event_score, model_score,
        technical_score, capital_score, research_state, event_title, momentum_score,
        explanation_json, missing_conditions
        FROM research_scores WHERE created_at LIKE ? ORDER BY research_score DESC""",
        (today + "%",)).fetchall()

    created = 0
    for code, name, rscore, ev, md, te, ca, state, etitle, mom, expl_json, miss_json in rows:
        try:
            expl = json.loads(expl_json or "{}")
        except Exception:
            expl = {}
        try:
            missing = json.loads(miss_json or "[]")
        except Exception:
            missing = []
        s = build_summary({
            "stock_code": code, "stock_name": name, "research_score": rscore,
            "event_score": ev, "model_score": md, "technical_score": te, "capital_score": ca,
            "research_state": state, "event_title": etitle, "momentum_score": mom,
            "explanation": expl, "missing": missing,
        })
        con.execute("""INSERT INTO research_summary
            (stock_code, stock_name, summary, positive_factors, risk_factors, missing_conditions,
             research_score, research_state, suggestion, parameter_version, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (code, name or "", s["summary"],
             json.dumps(s["positive_factors"], ensure_ascii=False),
             json.dumps(s["risk_factors"], ensure_ascii=False),
             json.dumps(s["missing_conditions"], ensure_ascii=False),
             rscore, state, s["suggestion"], PARAM_VERSION, now))
        created += 1
    con.commit()

    print(f"✅ v2.0 Research Summary: {created} 条研究结论（{PARAM_VERSION}）")
    # 样本（Top5 高分）
    top = con.execute("""SELECT stock_name, research_score, research_state, substr(summary,1,60), suggestion
        FROM research_summary WHERE created_at LIKE ? ORDER BY research_score DESC LIMIT 6""",
        (today + "%",)).fetchall()
    for r in top:
        print(f"  {r[0]} [{r[2]}] {r[1]}分 | {r[3]} | 建议: {r[4][:30]}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
