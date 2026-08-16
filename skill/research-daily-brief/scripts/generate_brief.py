#!/usr/bin/env python3
"""每日研究简报生成器（v2.2）
读取 VPS2 资讯研究档案库 API → 固定格式 Markdown（Telegram 友好）
只读研究数据，绝不输出买卖建议。
"""
import json, re, sys, urllib.request
from datetime import datetime, timedelta

API = "https://reports.wmsora.vip/archive/api"

STATE_CN = {"cold": "❄️冷启动", "warming": "🌡️升温", "focused": "🎯聚焦", "confirmed": "✅确认", "fading": "📉降温"}
RS_STATE_CN = {"重点研究": "🔴重点", "优先跟踪": "🟠优先", "观察": "🔵观察", "普通": "⚪普通", "忽略": "⚪忽略"}
TRIGGER_CN = {"FIRST_INSTITUTION": "🎯机构首次确认", "STOCK_EXPANSION": "📈股票映射扩展",
              "CONSENSUS_BUILD": "🤝机构共识", "HEAT_BREAKOUT": "🔥热度突破"}


def fetch(path):
    try:
        req = urllib.request.Request(API + path, headers={"User-Agent": "Mozilla/5.0 research-daily-brief/2.2"})
        return json.loads(urllib.request.urlopen(req, timeout=15).read().decode())
    except Exception as e:
        print(f"[WARN] {path} 失败: {e}", file=sys.stderr)
        return None


def fetch_positions():
    """持仓（只读，用于持仓相关研究信息）"""
    try:
        req = urllib.request.Request("https://vip2.wmsora.vip/api/positions",
                                     headers={"User-Agent": "Mozilla/5.0 research-daily-brief/2.2"})
        d = json.loads(urllib.request.urlopen(req, timeout=10).read().decode())
        return d.get("positions") or []
    except Exception as e:
        print(f"[WARN] positions 失败: {e}", file=sys.stderr)
        return []


def clean_title(t, n=46):
    t = re.sub(r'^\s*(?:\d{1,2}:\d{2}|:\d{2}|：\d{2})\s*', '', t or "")
    t = re.sub(r'^【[^】]{0,12}】\s*', '', t)
    t = re.sub(r'^[#＃]\s*', '', t)
    return (t or "")[:n]


def main():
    cockpit = fetch("/dashboard/cockpit")
    if not cockpit:
        print("❌ 无法获取驾驶舱数据，检查 VPS2 API 可用性")
        return 1
    date = cockpit.get("date") or datetime.now().strftime("%Y-%m-%d")
    lines = []
    lines.append("🔥 今日研究驾驶舱")
    lines.append(f"日期：{date}（数据截至 {date} 收盘 · 事件近24h）")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━")

    # ── 1. 今日升温事件 ──
    hot = cockpit.get("hot_events") or []
    if hot:
        lines.append("")
        lines.append("1️⃣ 今日升温事件")
        lines.append("")
        for e in hot[:4]:
            lines.append(f"🔥 {clean_title(e.get('event_title'))}")
            lines.append(f"Momentum {e.get('momentum_score', 0)} · 状态：{'升温中' if e.get('status') == 'heating' else '新出现'}")
            inst_n = e.get("institution_count") or 0
            if inst_n:
                lines.append(f"机构确认：{inst_n} 家")
            tops = (e.get("top_stocks") or [])[:2]
            for s in tops:
                rs = s.get("research_score")
                rel = "🎯直接受益" if s.get("relation_type") == "直接受益" else "产业链"
                lines.append(f"  {s.get('stock_code')} {s.get('stock_name') or ''} RS {rs} {rel}")
            lines.append("")
    else:
        lines.append("")
        lines.append("1️⃣ 今日升温事件")
        lines.append("（今日暂无升温事件）")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━")

    # ── 2. 今日重点研究股票 ──
    focus = cockpit.get("focus_stocks") or []
    if focus:
        lines.append("")
        lines.append("2️⃣ 今日重点研究股票")
        lines.append("")
        for i, f in enumerate(focus[:6]):
            lines.append(f"{'①②③④⑤⑥'[i]} {f.get('stock_name') or f.get('stock_code')} {f.get('stock_code')} · RS {f.get('research_score')} {STATE_CN.get(f.get('research_state'), '')}")
            summary = (f.get("summary") or "").replace(f.get("stock_name") or "", "").strip("：:，,")
            summary = re.sub(r'^\s*(?:\d{1,2}:\d{2}|:\d{2})\s*', '', summary)
            if summary:
                lines.append(f"  {summary[:50]}")
            risks = (f.get("risk_factors") or [])[:1]
            if risks:
                lines.append(f"  ⚠️ 风险：{risks[0].get('label', '')[:40]}")
            lines.append("")
    else:
        lines.append("")
        lines.append("2️⃣ 今日重点研究股票")
        lines.append("（暂无 RS≥70 重点研究）")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━")

    # ── 3. 研究变化（昨日关注 → 今日变化，连续追踪）──
    rising = cockpit.get("rising_stocks") or []
    lines.append("")
    lines.append("3️⃣ 研究变化")
    lines.append("")
    if rising:
        for r in rising[:3]:
            code = r.get("stock_code")
            name = r.get("stock_name") or code
            delta = r.get("score_change") or 0
            # 查历史取昨日 RS（如有）
            rsd = fetch(f"/research-score?code={code}") or {}
            hist = rsd.get("history") or []
            prev_rs = None
            if len(hist) >= 2:
                prev_rs = hist[1].get("research_score")
            reason = ""
            chg = (rsd.get("score") or {}).get("change_reason") or []
            if isinstance(chg, str):
                try:
                    chg = json.loads(chg)
                except Exception:
                    chg = []
            if chg:
                labels = []
                for c in chg[:2]:
                    lbl = re.sub(r'\s*[（(][^）)]*[）)]\s*$', '', c.get('label', ''))
                    lbl = re.sub(r'\s*[+-]?\d+\s*$', '', lbl)
                    labels.append(f"{c.get('delta', 0):+d}{lbl[:16]}")
                reason = "；".join(labels)
            if prev_rs is not None:
                lines.append(f"📈 变化：{name} RS {prev_rs}→{r.get('research_score')}（{delta:+d}）")
            else:
                lines.append(f"📈 关注：{name} RS {r.get('research_score')}（今日{delta:+d}，首日基线）")
            if reason:
                lines.append(f"  原因：{reason}")
            lines.append("")
    else:
        lines.append("（今日无显著评分变化）")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━")

    # ── 4. 持仓相关研究信息（只读，无买卖建议）──
    positions = fetch_positions()
    if positions:
        lines.append("")
        lines.append("4️⃣ 🔴 持仓相关")
        lines.append("")
        for p in positions[:5]:
            code = str(p.get("code", ""))
            pname = p.get("name") or code
            # 查该股 Research Score + 关联事件
            rsd = fetch(f"/research-score?code={code}") or {}
            s = rsd.get("score") or {}
            evd = fetch(f"/stocks/events?code={code}") or {}
            evs = (evd.get("events") or [])[:1]
            state_cn = STATE_CN.get(s.get("research_state"), "")
            lines.append(f"🔴 {pname} {code} · RS {s.get('research_score', '-')} {state_cn} · {p.get('state', '')}")
            if evs:
                ev = evs[0]
                rel = "🎯直接受益" if ev.get("relation_type") == "直接受益" else (ev.get("relation_type") or "")
                lines.append(f"  事件：{clean_title(ev.get('event_title'), 36)} {rel}")
                if ev.get("momentum_score"):
                    lines.append(f"  热度：🔥{ev.get('momentum_score')} · 机构{ev.get('inst_count', 0)}家")
            if (s.get("explanation") or {}).get("penalties"):
                pen = (s.get("explanation") or {}).get("penalties") or []
                lines.append(f"  ⚠️ 风险：{pen[0].get('label', '')[:36]}")
            lines.append("")
        lines.append("（仅研究信息 · 不含买卖/仓位建议）")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━")

    # ── 5. 风险观察（传闻/风险事件）──
    lines.append("")
    lines.append("5️⃣ 风险观察")
    events = fetch("/events?limit=50") or {}
    ev_list = events.get("events") or []
    rumor = [e for e in ev_list if e.get("event_type") == "传闻求证"][:2]
    if rumor:
        for e in rumor:
            lines.append(f"⚠️ {clean_title(e.get('event_title'), 40)}")
            lines.append(f"  类型：市场传闻 · 等待正式确认")
    else:
        lines.append("（今日暂无传闻/风险事件标记）")
    lines.append("")

    # ── 验证统计 ──
    stats = fetch("/validation/stats") or {}
    v_n = stats.get("validated") or 0
    v_rate = stats.get("hit_rate") or 0
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append("")
    if v_n:
        lines.append(f"📊 验证统计：{v_n} 样本 · 命中率 {v_rate}%")
    lines.append(f"数据时间：{date} 行情 · 事件近24h")
    lines.append("")
    lines.append("⚠️ 研究辅助 · 非投资建议")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
