#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2.3.4d Observation Report — 研究系统观察日报（每日生成，只读统计不改模型）
观察期 5 个指标：
  ① RS 分层稳定性（T+5/T+10/T+20 三周期）
  ② RS 四维贡献（上涨样本主要来自事件/模型/技术/资金哪一维）
  ③ Graph 增益（同 RS 档内 GS高 vs GS低 对比——正确看法）
  ④ Confidence 修正价值（同 RS 档内 Confidence高 vs 低 对比）
  ⑤ 十大模型真实贡献（样本/T+5/T+20/最大回撤）
日报保存 /root/workspace/observation_reports/，供 v2.4 三轨实验直接引用。
"""
import json, os, sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

DB = "/root/workspace/research_archive.db"
KLINE = "/root/vip1_reports/kline_data.json"
OUT_DIR = "/root/workspace/observation_reports"
WEB_DIR = "/root/vip1_reports"          # 报告站静态根（reports.wmsora.vip → :8080）
TZ = ZoneInfo("Asia/Shanghai")
VERSION = "v2.3.4c"


def load_kline():
    try:
        d = json.load(open(KLINE))
        out = {}
        for code, info in (d.get("kline_data") or {}).items():
            bars = {}
            for b in (info.get("kline_history") or []):
                bars[b["trade_date"]] = b.get("close")
            out[code] = bars
        return out
    except Exception:
        return {}


def tN(bars, trigger_date, n):
    """trigger_date 后第 n 个交易日收盘涨跌幅（%），n=5/10/20"""
    if not bars or trigger_date not in bars or not bars[trigger_date]:
        return None
    base = bars[trigger_date]
    if not base:
        return None
    after = [d for d in sorted(bars.keys()) if d > trigger_date]
    if len(after) < n:
        return None
    c = bars[after[n - 1]]
    return round((c / base - 1) * 100, 2) if c else None


def market_regime(kline):
    """v2.3.4e 市场环境标签（无指数，用研究池等权代理）：
    强势/震荡/弱势 —— 依据：当日涨跌家数比例 + 近5日 vs 前20日趋势 + 涨停近似(≥9.8%)"""
    # 每个股票按日期取 close 与 pct_chg
    daily = {}   # date -> {"up": n, "down": n, "flat": n, "limit_up": n, "total": n, "pct": [..]}
    for code, bars in (kline or {}).items():
        if not bars:
            continue
        dates = sorted(bars.keys())
        for i, d in enumerate(dates):
            c = bars[d]
            if not c:
                continue
            prev = bars[dates[i - 1]] if i > 0 else None
            if prev:
                pct = (c / prev - 1) * 100
            else:
                pct = 0.0
            rec = daily.setdefault(d, {"up": 0, "down": 0, "flat": 0, "limit_up": 0, "pct": []})
            rec["pct"].append(pct)
            if pct >= 1.0:
                rec["up"] += 1
            elif pct <= -1.0:
                rec["down"] += 1
            else:
                rec["flat"] += 1
            if pct >= 9.5:
                rec["limit_up"] += 1
    if not daily:
        return {"label": "未知", "detail": "无行情数据", "date": ""}
    last_date = max(daily.keys())
    rec = daily[last_date]
    total = max(rec["up"] + rec["down"] + rec["flat"], 1)
    up_ratio = rec["up"] / total
    limit_up = rec["limit_up"]
    # 趋势：近5日 vs 前20日 等权平均涨跌幅
    dates = sorted(daily.keys())
    idx = dates.index(last_date)
    def avg_pct(day_range):
        vals = []
        for d in day_range:
            r = daily.get(d)
            if r and r["pct"]:
                vals.append(sum(r["pct"]) / len(r["pct"]))
        return sum(vals) / len(vals) if vals else 0.0
    recent5 = avg_pct(dates[max(0, idx - 4):idx + 1])
    prior20 = avg_pct(dates[max(0, idx - 19):idx + 1])
    trend = recent5 - prior20
    # 判定
    if up_ratio >= 0.6 and trend >= 0.3:
        label = "强势"
    elif up_ratio <= 0.4 and trend <= -0.3:
        label = "弱势"
    else:
        label = "震荡"
    detail = f"上涨{rec['up']}/{total} ({up_ratio*100:.0f}%) 涨停≈{limit_up} · 近5日均幅{recent5:+.2f}% vs 前20日{prior20:+.2f}% · 趋势{trend:+.2f}pp"
    return {"label": label, "detail": detail, "date": last_date}


def main():
    now = datetime.now(TZ)
    today = now.strftime("%Y-%m-%d")
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    kline = load_kline()
    regime = market_regime(kline)

    L = []
    L.append("=" * 64)
    L.append(f"🧭 研究系统观察日报 · {today}（Observation Report v2.3.4d）")
    L.append(f"   版本: System {VERSION} / RS v1.9.1 / Graph v2.3.4 / Validation v2.1 · Mode: Observation")
    L.append(f"   📈 市场环境: {regime['label']}（{regime['detail']}）")
    L.append("=" * 64)

    # ── ① 样本总览 ──
    val_total = con.execute("SELECT COUNT(*) FROM research_validation").fetchone()[0]
    t1_done = con.execute("SELECT COUNT(*) FROM research_validation WHERE t1_pct IS NOT NULL").fetchone()[0]
    t3_done = con.execute("SELECT COUNT(*) FROM research_validation WHERE t3_pct IS NOT NULL").fetchone()[0]
    t5_done = con.execute("SELECT COUNT(*) FROM research_validation WHERE t5_pct IS NOT NULL").fetchone()[0]
    # T+10/T+20 现算
    t10_done = t20_done = 0
    for r in con.execute("SELECT stock_code, trigger_date FROM research_validation"):
        bars = kline.get(str(r["stock_code"]))
        if tN(bars, r["trigger_date"], 10) is not None:
            t10_done += 1
        if tN(bars, r["trigger_date"], 20) is not None:
            t20_done += 1
    L.append("")
    L.append("📊 样本总览")
    L.append(f"  验证样本 {val_total} · T+1 {t1_done} · T+3 {t3_done} · T+5 {t5_done} · T+10 {t10_done} · T+20 {t20_done}")
    L.append(f"  v2.4 目标: T+5≥100 ({t5_done}/100) · 交易日≥20 · 市场环境覆盖(强/震荡/弱)")
    if t10_done == 0:
        L.append(f"  ⏳ T+10/T+20 待积累：kline 行情仅覆盖至最近交易日（触发日最早的样本也 <10 个后续交易日）")

    # ── ② RS 分层（T+1/3/5/10/20 平均 + 命中率）──
    def layer_stats(min_s, max_s):
        rows = con.execute("SELECT stock_code, trigger_date, t1_pct, t3_pct, t5_pct, result FROM research_validation WHERE research_score>=? AND research_score<?", (min_s, max_s)).fetchall()
        n = len(rows)
        if not n:
            return None
        def avg(field):
            vs = [r[field] for r in rows if r[field] is not None]
            return round(sum(vs) / len(vs), 2) if vs else None
        hits = sum(1 for r in rows if r["result"] == "hit")
        done = sum(1 for r in rows if r["result"] in ("hit", "miss", "flat"))
        # T+10/T+20 现算
        t10s, t20s = [], []
        for r in rows:
            bars = kline.get(str(r["stock_code"]))
            v10 = tN(bars, r["trigger_date"], 10)
            v20 = tN(bars, r["trigger_date"], 20)
            if v10 is not None: t10s.append(v10)
            if v20 is not None: t20s.append(v20)
        return {"n": n, "t1": avg("t1_pct"), "t3": avg("t3_pct"), "t5": avg("t5_pct"),
                "t10": round(sum(t10s) / len(t10s), 2) if t10s else None,
                "t20": round(sum(t20s) / len(t20s), 2) if t20s else None,
                "hit_rate": round(hits / done * 100, 1) if done else None}
    layers = {"80+": layer_stats(80, 101), "70-79": layer_stats(70, 80),
              "60-69": layer_stats(60, 70), "<60": layer_stats(0, 60)}
    L.append("")
    L.append("🎯 ① RS 分层稳定性（三周期）")
    L.append(f"  {'区间':<8}{'样本':>6}{'T+1':>8}{'T+3':>8}{'T+5':>8}{'T+10':>8}{'T+20':>8}{'命中率':>8}")
    for k, v in layers.items():
        if not v:
            L.append(f"  {k:<10}{0:>6}")
            continue
        L.append(f"  {k:<10}{v['n']:>6}{str(v['t1']):>8}{str(v['t3']):>8}{str(v['t5']):>8}{str(v['t10']):>8}{str(v['t20']):>8}{str(v['hit_rate']):>8}")

    # ── ③ RS 四维贡献（explanation_json.dims，同日最后一条 = 当日最终状态）──
    dim_hits = {"event": {"hit": 0, "done": 0}, "model": {"hit": 0, "done": 0},
                "technical": {"hit": 0, "done": 0}, "capital": {"hit": 0, "done": 0}}
    dim_avg_score = {"event": [], "model": [], "technical": [], "capital": []}
    rs_by_day = {}
    for r in con.execute("SELECT stock_code, explanation_json, created_at, id FROM research_scores WHERE explanation_json IS NOT NULL AND explanation_json != '{}'"):
        key = (r["stock_code"], (r["created_at"] or "")[:10])
        # 覆盖式：保留当日 id 最大的（最后评分 = 当日最终状态）
        prev = rs_by_day.get(key)
        if prev is None or r["id"] > prev[1]:
            rs_by_day[key] = (r["explanation_json"], r["id"])
    for r in con.execute("SELECT stock_code, trigger_date, result FROM research_validation"):
        hit = rs_by_day.get((r["stock_code"], r["trigger_date"]))
        exp = hit[0] if hit else None
        if not exp or r["result"] not in ("hit", "miss", "flat"):
            continue
        try:
            dims = json.loads(exp).get("dims") or {}
        except Exception:
            dims = {}
        if not dims:
            continue
        for dim in ("event", "model", "technical", "capital"):
            s = (dims.get(dim) or {}).get("score") or 0
            dim_avg_score[dim].append(s)
            dim_hits[dim]["done"] += 1
            if r["result"] == "hit":
                dim_hits[dim]["hit"] += 1
    dim_covered = sum(1 for r in con.execute("""SELECT DISTINCT v.stock_code||v.trigger_date FROM research_validation v
        JOIN research_scores rs ON rs.stock_code=v.stock_code AND substr(rs.created_at,1,10)=v.trigger_date
        WHERE v.result IN ('hit','miss','flat')"""))
    L.append("")
    L.append("🧩 ② RS 四维贡献（上涨样本的维度构成）")
    L.append(f"  ⚠️ research_scores 仅保留最近 2 日快照（researscore_v19 清理），当前可回溯样本集中在 08-12/13；08-10 已完结样本的四维历史已不可恢复（v2.3.4c 快照机制将随积累补齐）")
    for dim, label in (("event", "事件"), ("model", "模型"), ("technical", "技术"), ("capital", "资金")):
        d = dim_hits[dim]
        avg = round(sum(dim_avg_score[dim]) / len(dim_avg_score[dim]), 1) if dim_avg_score[dim] else None
        hr = round(d["hit"] / d["done"] * 100, 1) if d["done"] else None
        L.append(f"  {label:<6} 平均分 {str(avg):<6} 样本 {d['done']:<5} 命中率 {hr}")

    # ── ④ GS 增益（同 RS 档内 GS高 vs GS低）──
    def stock_gs(code):
        c = str(code)
        evs = con.execute("SELECT COUNT(*) FROM research_graph_relation WHERE source_type='event' AND target_type='stock' AND target_id=?", (c,)).fetchone()[0]
        inds = con.execute("SELECT COUNT(*) FROM research_graph_relation WHERE source_type='stock' AND target_type='industry' AND source_id=?", (c,)).fetchone()[0]
        return min(100, evs * 5 + inds * 2)
    L.append("")
    L.append("🔥 ③ Graph 增益（同 RS 档内 GS 高 vs 低）")
    L.append(f"  {'RS档':<10}{'GS组':<8}{'样本':>6}{'T+5':>8}{'T+10':>8}{'T+20':>8}{'命中率':>8}")
    for rk in ("70-79", "60-69"):
        lo = int(rk[:2]); hi = lo + 10
        rows = con.execute("SELECT stock_code, trigger_date, t5_pct, result FROM research_validation WHERE research_score>=? AND research_score<?", (lo, hi)).fetchall()
        groups = {"GS高(≥40)": [], "GS低(<40)": []}
        for r in rows:
            g = stock_gs(r["stock_code"])
            key = "GS高(≥40)" if g >= 40 else "GS低(<40)"
            groups[key].append(r)
        for gk, gr in groups.items():
            if not gr:
                continue
            t5s = [r["t5_pct"] for r in gr if r["t5_pct"] is not None]
            hits = sum(1 for r in gr if r["result"] == "hit")
            done = sum(1 for r in gr if r["result"] in ("hit", "miss", "flat"))
            t10s, t20s = [], []
            for r in gr:
                bars = kline.get(str(r["stock_code"]))
                v10 = tN(bars, r["trigger_date"], 10)
                v20 = tN(bars, r["trigger_date"], 20)
                if v10 is not None: t10s.append(v10)
                if v20 is not None: t20s.append(v20)
            L.append(f"  {rk:<10}{gk:<8}{len(gr):>6}"
                     f"{str(round(sum(t5s)/len(t5s),2) if t5s else None):>8}"
                     f"{str(round(sum(t10s)/len(t10s),2) if t10s else None):>8}"
                     f"{str(round(sum(t20s)/len(t20s),2) if t20s else None):>8}"
                     f"{str(round(hits/done*100,1) if done else None):>8}")

    # ── ⑤ Confidence 修正价值（同 RS 档内高/低）──
    def stock_conf(code):
        c = str(code)
        insts = con.execute("SELECT COUNT(*) FROM research_graph_relation WHERE source_type='stock' AND relation_type='followed_by' AND source_id=?", (c,)).fetchone()[0]
        evs = con.execute("SELECT COUNT(*) FROM research_graph_relation WHERE source_type='event' AND target_type='stock' AND target_id=?", (c,)).fetchone()[0]
        return min(100, insts * 20 + evs * 10)
    L.append("")
    L.append("✅ ④ Confidence 修正价值（同 RS 档内 高认可 vs 低认可）")
    L.append(f"  {'RS档':<10}{'Conf组':<12}{'样本':>6}{'T+5':>8}{'命中率':>8}")
    for rk in ("80+", "70-79", "60-69"):
        lo, hi = (80, 101) if rk == "80+" else (int(rk[:2]), int(rk[:2]) + 10)
        rows = con.execute("SELECT stock_code, trigger_date, t5_pct, result FROM research_validation WHERE research_score>=? AND research_score<?", (lo, hi)).fetchall()
        groups = {"高(≥40)": [], "低(<40)": []}
        for r in rows:
            c = stock_conf(r["stock_code"])
            groups["高(≥40)" if c >= 40 else "低(<40)"].append(r)
        for gk, gr in groups.items():
            if not gr:
                continue
            t5s = [r["t5_pct"] for r in gr if r["t5_pct"] is not None]
            hits = sum(1 for r in gr if r["result"] == "hit")
            done = sum(1 for r in gr if r["result"] in ("hit", "miss", "flat"))
            L.append(f"  {rk:<10}{gk:<12}{len(gr):>6}"
                     f"{str(round(sum(t5s)/len(t5s),2) if t5s else None):>8}"
                     f"{str(round(hits/done*100,1) if done else None):>8}")

    # ── ⑥ 十大模型真实贡献 ──
    model_stats = {}
    for r in con.execute("SELECT stock_code, model_detail FROM research_scores WHERE model_detail IS NOT NULL AND model_detail != '{}'"):
        try:
            md = json.loads(r["model_detail"] or "{}")
            m = md.get("model") if isinstance(md, dict) else None
        except Exception:
            m = None
        if not m:
            continue
        c = model_stats.setdefault(m, {"n": 0, "hit": 0, "done": 0, "t5": [], "t20": [], "dd": []})
        v = con.execute("SELECT stock_code, trigger_date, t5_pct, result, max_drawdown FROM research_validation WHERE stock_code=? ORDER BY id DESC LIMIT 1", (r["stock_code"],)).fetchone()
        if not v:
            continue
        c["n"] += 1
        if v["t5_pct"] is not None:
            c["t5"].append(v["t5_pct"])
        if v["result"] in ("hit", "miss", "flat"):
            c["done"] += 1
            if v["result"] == "hit":
                c["hit"] += 1
        if v["max_drawdown"] is not None:
            c["dd"].append(v["max_drawdown"])
        bars = kline.get(str(v["stock_code"]))
        v20 = tN(bars, v["trigger_date"], 20)
        if v20 is not None:
            c["t20"].append(v20)
    L.append("")
    L.append("🧮 ⑤ 十大模型真实贡献（样本/T+5/T+20/最大回撤）")
    L.append(f"  {'模型':<12}{'样本':>6}{'T+5':>8}{'T+20':>8}{'maxDD':>8}{'命中率':>8}")
    for m, v in sorted(model_stats.items(), key=lambda x: -x[1]["n"])[:10]:
        if not v["n"]:
            continue
        t5avg = round(sum(v["t5"]) / len(v["t5"]), 2) if v["t5"] else None
        t20avg = round(sum(v["t20"]) / len(v["t20"]), 2) if v["t20"] else None
        ddavg = round(sum(v["dd"]) / len(v["dd"]), 2) if v["dd"] else None
        hr = round(v["hit"] / v["done"] * 100, 1) if v["done"] else None
        L.append(f"  {m:<14}{v['n']:>6}{str(t5avg):>8}{str(t20avg):>8}{str(ddavg):>8}{str(hr):>8}")

    L.append("")
    L.append("📌 冻结基线: RS v1.9.1 公式 / Momentum 算法 / 十大模型权重 / Graph Score / 状态机 / 验证口径")
    L.append("   仅统计不改模型。T+5≥100 且市场环境覆盖后进入 v2.4 三轨实验。")
    L.append("=" * 64)

    report = "\n".join(L)
    print(report)

    os.makedirs(OUT_DIR, exist_ok=True)
    md_path = f"{OUT_DIR}/observation_report_{today}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    with open("/var/log/research-obs.log", "a", encoding="utf-8") as f:
        f.write(report + "\n\n")
    # 市场环境写入快照表（供 v2.4 按市场环境分组分析）
    try:
        con.execute("INSERT OR REPLACE INTO research_system_snapshot (snap_date, market_regime, system_version, created_at) VALUES (?,?,?,?)",
                    (today, json.dumps({"label": regime["label"], "detail": regime["detail"]}, ensure_ascii=False), VERSION, now.strftime("%Y-%m-%d %H:%M:%S")))
        con.commit()
    except Exception:
        pass

    # ── v2.3.4e 报告站 HTML 版（reports.wmsora.vip 浏览器可看，零依赖 <pre> 渲染）──
    html = f"""<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>研究系统观察日报 · {today}</title>
<style>
:root{{--bg:#FAFAF7;--sf:#fff;--ink:#101418;--t2:#4B5563;--t3:#8A929E;--b:#111418;--bl:#E5E7EB;--r:#D9362B;--u:#2857F0;--g:#178A45;--o:#D28C3A;}}
*{{box-sizing:border-box}}body{{margin:0;color:var(--ink);font:15px/1.68 "Inter","PingFang SC","Noto Sans SC",sans-serif;background:var(--bg)}}
.wrap{{max-width:1100px;margin:0 auto;padding:30px 16px 60px}}
h1{{font-size:30px;letter-spacing:-.03em;margin:0 0 4px;border-bottom:3px solid var(--b);padding-bottom:14px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
h1 small{{font-size:14px;font-weight:400;color:var(--t2)}}
.top{{display:flex;justify-content:space-between;align-items:center;margin:14px 0 20px;gap:10px;flex-wrap:wrap}}
.back{{display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border:1.5px solid var(--b);background:var(--sf);text-decoration:none;color:var(--ink);font-size:13px;font-weight:600;box-shadow:2px 2px 0 var(--b)}}
.back:hover{{box-shadow:2px 2px 0 var(--u);border-color:var(--u)}}
pre{{background:var(--sf);border:1.5px solid var(--b);box-shadow:4px 4px 0 rgba(17,20,24,.9);padding:22px 24px;margin:0;overflow-x:auto;font:13px/1.62 "SF Mono","Consolas","PingFang SC",monospace;white-space:pre-wrap;word-break:break-all}}
@media(max-width:760px){{.wrap{{padding:16px 10px 40px}}h1{{font-size:22px}}pre{{padding:14px 12px;font-size:12px}}}}
</style></head><body>
<div class="wrap">
<h1>🧭 研究系统观察日报 <small>{today}</small></h1>
<div class="top"><a class="back" href="observation_index.html">← 全部日报</a><span style="font-size:12px;color:var(--t3)">Observation Report v2.3.4d · 每日 21:50 自动生成</span></div>
<pre>{report.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')}</pre>
</div></body></html>"""
    with open(f"{WEB_DIR}/observation_report_{today}.html", "w", encoding="utf-8") as f:
        f.write(html)

    # ── 索引页（列出全部日报）──
    import glob as _glob
    files = sorted(_glob.glob(f"{WEB_DIR}/observation_report_*.html"))
    links = []
    for fp in files:
        d = fp.split("observation_report_")[-1].replace(".html", "")
        links.append(f'<a href="observation_report_{d}.html">🧭 {d}</a>')
    idx_html = f"""<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>研究系统观察日报 · 索引</title>
<style>
:root{{--bg:#FAFAF7;--sf:#fff;--ink:#101418;--t2:#4B5563;--t3:#8A929E;--b:#111418;--bl:#E5E7EB;--u:#2857F0;}}
*{{box-sizing:border-box}}body{{margin:0;color:var(--ink);font:15px/1.68 "Inter","PingFang SC","Noto Sans SC",sans-serif;background:var(--bg);background-image:radial-gradient(rgba(17,20,24,.035) .7px,transparent .7px),linear-gradient(rgba(17,20,24,.025) 1px,transparent 1px);background-size:18px 18px,24px 24px}}
.wrap{{max-width:1000px;margin:0 auto;padding:30px 16px 60px}}
h1{{font-size:30px;letter-spacing:-.03em;border-bottom:3px solid var(--b);padding-bottom:14px;margin:0 0 6px}}
.desc{{color:var(--t2);font-size:14px;margin:0 0 24px}}
.links{{display:flex;flex-direction:column;gap:10px}}
.links a{{display:flex;align-items:center;gap:8px;padding:12px 16px;border:1.5px solid var(--b);background:var(--sf);text-decoration:none;color:var(--ink);font-weight:600;box-shadow:3px 3px 0 var(--b)}}
.links a:hover{{box-shadow:3px 3px 0 var(--u);border-color:var(--u)}}
.note{{margin-top:22px;font-size:12px;color:var(--t3)}}
</style></head><body>
<div class="wrap">
<h1>🧭 研究系统观察日报</h1>
<p class="desc">每日自动生成的观察报告（共 {len(links)} 份）· Observation Mode v2.3.4 · 冻结基线 RS v1.9.1 / Graph v2.3.4 / Validation v2.1</p>
<div class="links">
{chr(10).join(links) if links else '<div style="padding:20px;border:1.5px solid var(--bl);color:var(--t3)">暂无日报</div>'}
</div>
<p class="note">由 archive_obs_report_v234d.py 每日 21:50 自动生成 · 仅统计不改模型 · T+5≥100 且市场环境覆盖后进入 v2.4 三轨实验</p>
</div></body></html>"""
    with open(f"{WEB_DIR}/observation_index.html", "w", encoding="utf-8") as f:
        f.write(idx_html)

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
