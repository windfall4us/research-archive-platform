#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_consensus_snapshot_html.py — 每日静态 HTML Snapshot（审计副产物，非主入口）
====================================================================================
用途：历史快照 / 审计 / Telegram·Hermes 推送 / 出问题对比 / 不依赖前端应用即可查看。
定位：主产品=研判台交互看板；本文件=每日只读快照。

输入：data/consensus/consensus_daily_snapshot.json（build_consensus_snapshot.py 产物）
输出：reports/consensus/<latest_date>.html（自包含单文件，无外部依赖）

用法：python3 scripts/render_consensus_snapshot_html.py [--out-dir reports/consensus]
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STATE_ORDER = ["CONFIRMED", "REVERSING", "DIVERGING", "DISCOVERY", "WEAKENING", "CONFIRMING", "NEUTRAL", "UNMAPPED"]
STATE_LABEL = {"CONFIRMED": "确认", "REVERSING": "反转", "DIVERGING": "分歧", "DISCOVERY": "发现",
               "WEAKENING": "走弱", "CONFIRMING": "确认中", "NEUTRAL": "中性", "UNMAPPED": "未映射"}
STATE_COLOR = {"CONFIRMED": "#15803d", "REVERSING": "#b91c1c", "DIVERGING": "#b45309", "DISCOVERY": "#1d4ed8",
               "WEAKENING": "#64748b", "CONFIRMING": "#0284c7", "NEUTRAL": "#94a3b8", "UNMAPPED": "#c0c9d4"}
MOM_LABEL = {"HEATING": "升温", "EMERGING": "新现", "STABLE": "平稳", "COOLING": "降温", "FADING": "退潮",
             "DISCOVERY": "发现", "UNCLASSIFIED_BASELINE": "基线", "BASELINE_ONLY": "基线"}
CONS_LABEL = {"STRONG_POSITIVE": "强看多", "POSITIVE": "看多", "NEUTRAL": "中性", "NEGATIVE": "看空", "STRONG_NEGATIVE": "强看空"}


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def f2(v):
    try:
        n = float(v)
        return f"{n:.2f}" if n == n and abs(n) != float("inf") else "--"
    except (TypeError, ValueError):
        return "--"


def render(snap: dict) -> str:
    m = snap["meta"]
    ov = snap["overview"]
    lm = ov.get("latest_market", {})
    latest = m.get("latest_date", "--")

    # 状态分布
    sd = ov.get("state_distribution", {})
    state_cells = "".join(
        f'<div class="stcell"><span class="badge" style="background:{STATE_COLOR[s]}22;color:{STATE_COLOR[s]}">{STATE_LABEL.get(s, s)}</span><b>{sd[s]}</b></div>'
        for s in STATE_ORDER if sd.get(s)
    )
    # 热主题
    hot = "".join(
        f'<tr><td class="tname">{esc(t["theme_name"])}</td><td class="num">{f2(t.get("heat_score"))}</td>'
        f'<td><span class="badge">{esc(t.get("heat_level") or "COLD")}</span></td>'
        f'<td>{esc(MOM_LABEL.get(t.get("momentum_state"), t.get("momentum_state") or "--"))}</td>'
        f'<td>{esc(t.get("signal_confidence") or "--")}</td></tr>'
        for t in ov.get("top_themes", [])
    )
    # 主题联动表
    theme_rows = ""
    for t in snap["themes"]["latest"]:
        cov = (t.get("factors") or {}).get("coverage") or {}
        trd = (t.get("factors") or {}).get("trade") or {}
        hold = (t.get("factors") or {}).get("holding") or {}
        mom = t.get("momentum") or {}
        ss = t.get("stock_stats") or {}
        theme_rows += (
            f'<tr><td class="tname">{esc(t["theme_name"])}<small>{esc(t["theme_id"])}</small></td>'
            f'<td class="num"><b>{f2(t.get("heat_score"))}</b><span class="badge">{esc(t.get("heat_level") or "COLD")}</span></td>'
            f'<td>{esc(MOM_LABEL.get(mom.get("state"), mom.get("state") or "--"))}</td>'
            f'<td class="num">{cov.get("analysts", 0)}/{cov.get("eligible", 0)}</td>'
            f'<td class="num">{f2(trd.get("analyst_capped_value", trd.get("directional_value")))}</td>'
            f'<td class="num">{f2(hold.get("weighted_support"))}</td>'
            f'<td class="num up">{ss.get("strong_consensus", 0)}</td>'
            f'<td class="num down">{ss.get("divergence", 0)}</td></tr>'
        )
    # 状态股票表
    stock_rows = ""
    for s in snap["stocks"]["latest"][:120]:
        st = s.get("cross_layer_state", "NEUTRAL")
        stock_rows += (
            f'<tr><td class="tname"><b>{esc(s["name"])}</b><small>{esc(s["code"])}</small></td>'
            f'<td>{esc(CONS_LABEL.get(s.get("consensus_state"), s.get("consensus_state") or "--"))}</td>'
            f'<td>{esc(s.get("theme_name") or "--")}</td>'
            f'<td>{esc(MOM_LABEL.get(s.get("theme_momentum"), s.get("theme_momentum") or "--"))}</td>'
            f'<td>{"→".join((s.get("recent_actions") or [])[-3:]) or "--"}</td>'
            f'<td class="num">{f2((s.get("divergence") or {}).get("divergence_score"))}</td>'
            f'<td><span class="badge" style="background:{STATE_COLOR.get(st, "#94a3b8")}22;color:{STATE_COLOR.get(st, "#94a3b8")}">{STATE_LABEL.get(st, st)}</span></td></tr>'
        )
    # 分歧雷达
    dv = snap["divergence"]
    rev_rows = "".join(
        f'<tr><td class="tname"><b>{esc(r["name"])}</b><small>{esc(r["code"])}</small></td>'
        f'<td>{esc(r.get("theme_name") or "--")}</td>'
        f'<td>{esc(MOM_LABEL.get(r.get("theme_momentum"), r.get("theme_momentum") or "--"))}</td>'
        f'<td class="num">{f2(r.get("divergence_score"))}</td>'
        f'<td>{esc(" · ".join(r.get("state_notes") or []))}</td></tr>'
        for r in dv.get("reversing", [])
    )
    cat_map = {
        "analyst_split": "分析师意见分裂", "theme_stock_mismatch": "主题 ↔ 个股不同步",
        "view_action_mismatch": "观点 ↔ 操作不一致", "holding_turning_negative": "持仓转负",
        "high_divergence": "综合 Divergence 高",
    }
    cat_sections = ""
    for key, label in cat_map.items():
        rows = dv.get("categories", {}).get(key, [])
        cat_sections += f'<h4>{label} <span class="cnt">{len(rows)}</span></h4><table class="dv">'
        cat_sections += "".join(
            f'<tr><td class="tname"><b>{esc(r["name"])}</b><small>{esc(r["code"])}</small></td>'
            f'<td class="num">{f2(r.get("divergence_score"))}</td><td>{esc(r.get("theme_name") or "--")}</td></tr>'
            for r in rows[:15]
        )
        cat_sections += "</table>"

    # 低样本警告
    warns = []
    for t in (m.get("signal_warnings") or {}).get("LOW_SIGNAL", []):
        warns.append(f'<span class="warn low">LOW_SIGNAL · {esc(t)}</span>')
    for t in (m.get("signal_warnings") or {}).get("INSUFFICIENT_DATA", []):
        warns.append(f'<span class="warn insuff">INSUFFICIENT_DATA · {esc(t)}</span>')
    warn_html = '<div class="warns">' + "".join(warns) + "</div>" if warns else ""

    dc = ov.get("divergence_counts", {})
    market_dir_cls = str(lm.get("direction", "")).lower()

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>市场共识雷达 · {latest}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:#f1f5f9;color:#102d49;padding:20px}}
  .wrap{{max-width:1200px;margin:0 auto}}
  h1{{font-size:20px;margin-bottom:4px}}
  .sub{{color:#64748b;font-size:12px;margin-bottom:16px}}
  .statusbar{{background:linear-gradient(135deg,#0d2440,#12395e);color:#dbeafe;border-radius:12px;padding:12px 16px;margin-bottom:16px;font-size:13px;display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center}}
  .statusbar b{{color:#fff}}
  .statusbar .sep{{color:#3b5f86}}
  .sys{{background:#065f46;color:#a7f3d0;padding:2px 8px;border-radius:10px;font-size:12px}}
  .warns{{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}}
  .warn{{font-size:11px;padding:2px 8px;border-radius:10px}}
  .warn.low{{background:#78350f;color:#fde68a}}
  .warn.insuff{{background:#7f1d1d;color:#fecaca}}
  .card{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin-bottom:16px}}
  h2{{font-size:15px;margin-bottom:12px}}
  h4{{font-size:13px;margin:14px 0 8px}}
  .cnt{{color:#8a97a8;font-weight:400;font-size:12px}}
  .mk{{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}}
  .mk b{{font-size:28px;font-weight:800}}
  .bullish{{color:#dc2626}}.bearish{{color:#16a34a}}.neutral{{color:#64748b}}
  .mkmeta{{display:flex;gap:14px;font-size:12px;color:#64748b;margin-top:8px;flex-wrap:wrap}}
  .mkmeta b{{font-size:13px;color:#102d49}}
  .mkhist{{display:flex;gap:6px;margin-top:10px;flex-wrap:wrap}}
  .mkday{{font-size:10px;padding:3px 8px;border-radius:9px;border:1px solid #e2e8f0;color:#64748b}}
  .mkday.bullish{{background:#fef2f2;color:#dc2626}}
  .mkday.bearish{{background:#f0fdf4;color:#16a34a}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{text-align:left;font-size:11px;color:#8a97a8;font-weight:600;padding:6px 8px;border-bottom:1px solid #e2e8f0}}
  td{{padding:7px 8px;border-bottom:1px solid #f1f5f9}}
  tr:hover td{{background:#f6f9fd}}
  .tname{{font-weight:600;display:flex;flex-direction:column}}
  .tname small{{font-size:10px;color:#8a97a8;font-weight:400}}
  .num{{text-align:right}}
  .up{{color:#dc2626}}.down{{color:#16a34a}}
  .badge{{display:inline-block;font-size:10px;padding:2px 8px;border-radius:9px;background:#f1f5f9;color:#64748b;font-weight:700;margin-left:4px}}
  .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
  @media(max-width:900px){{.grid2{{grid-template-columns:1fr}}}}
  .stgrid{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:8px}}
  .stcell{{border:1px solid #e2e8f0;border-radius:10px;padding:10px;display:flex;flex-direction:column;align-items:center;gap:4px}}
  .stcell b{{font-size:22px}}
  .dv tr td{{font-size:12px}}
  .foot{{color:#8a97a8;font-size:11px;text-align:center;margin:24px 0 8px}}
</style></head><body><div class="wrap">
  <h1>市场共识雷达 · 每日快照</h1>
  <div class="sub">数据日期 {latest} · 分析师覆盖 {m.get("analyst_coverage","--")} · 主题 {m.get("n_themes","--")} · 股票 {m.get("n_stocks","--")}（映射 {m.get("n_mapped","--")} / 未映射 {m.get("n_unmapped","--")}）· 事件 {m.get("n_stock_events","--")} · 快照生成 {m.get("generated_at","--")}</div>
  <div class="statusbar">
    <span>数据日期</span><b>{latest}</b><span class="sep">|</span>
    <span>分析师覆盖</span><b>{m.get("analyst_coverage","--")}</b><span class="sep">|</span>
    <span>Market Views</span><b>{len(ov.get("market_history", []))}</b><span class="sep">|</span>
    <span>Theme Mentions</span><b>{m.get("n_theme_mentions","--")}</b><span class="sep">|</span>
    <span>Stock Events</span><b>{m.get("n_stock_events","--")}</b><span class="sep">|</span>
    <span>系统状态</span><b class="sys">{m.get("system_status","--")}</b>
    {warn_html}
  </div>

  <div class="card">
    <h2>市场方向</h2>
    <div class="mk"><b class="{market_dir_cls}">{lm.get("direction","UNKNOWN")}</b>
      <span>Direction Score <b>{f2(lm.get("direction_score"))}</b></span>
      <span>共识 <b>{lm.get("consensus_level","--")}</b></span>
      <span>有效分析师 <b>{lm.get("eligible_analysts",0)}</b></span>
      <span>覆盖 <b>{lm.get("coverage_status","--")}</b></span>
    </div>
    <div class="mkmeta">
      <span>看多 <b class="up">{lm.get("bullish",0)}</b></span>
      <span>中性 <b>{lm.get("neutral",0)}</b></span>
      <span>看空 <b class="down">{lm.get("bearish",0)}</b></span>
      <span>dominant <b>{f2((lm.get("dominant_share") or 0)*100)}%</b></span>
      <span>Risk <b>{esc((lm.get("risk") or {}).get("dominant","--"))}</b></span>
      <span>Bias <b>{esc((lm.get("position_bias") or {}).get("dominant","--"))}</b></span>
    </div>
    <div class="mkhist">{"".join(f'<span class="mkday {str(d.get("direction","")).lower()}">{d["date"][5:]}·{d.get("direction","")[:4]}</span>' for d in ov.get("market_history",[]))}</div>
  </div>

  <div class="grid2">
    <div class="card"><h2>今日最热主题</h2><table><tr><th>主题</th><th class="num">Heat</th><th>状态</th><th>动量</th><th>置信</th></tr>{hot}</table></div>
    <div class="card">
      <h2>状态股票分布（P4.3）</h2>
      <div class="stgrid">{state_cells}</div>
      <h4>分歧计数（P4.2）<span class="cnt"> 高分歧 {dc.get("high_divergence",0)} · 分析师分裂 {dc.get("analyst_split",0)} · 主题↔个股 {dc.get("theme_stock_mismatch",0)} · 观点↔操作 {dc.get("view_action_mismatch",0)} · 持仓转负 {dc.get("holding_turning_negative",0)}</span></h4>
    </div>
  </div>

  <div class="card"><h2>主题联动</h2><table><tr><th>主题</th><th class="num">Heat</th><th>动量</th><th class="num">覆盖</th><th class="num">Trade</th><th class="num">Holding</th><th class="num">强共识</th><th class="num">分歧</th></tr>{theme_rows}</table></div>

  <div class="card"><h2>个股状态清单（前 120）</h2><table><tr><th>股票</th><th>Consensus</th><th>主题</th><th>动量</th><th>Action</th><th class="num">Div</th><th>State</th></tr>{stock_rows}</table></div>

  <div class="card">
    <h2>⚠️ REVERSING 反转信号（{len(dv.get("reversing",[]))} 只）</h2>
    <table><tr><th>股票</th><th>主题</th><th>动量</th><th class="num">Div</th><th>说明</th></tr>{rev_rows}</table>
  </div>

  <div class="grid2">{cat_sections}</div>

  <div class="foot">市场共识雷达 · daily snapshot · schema {m.get("schema_version","--")} · 由 build_consensus_snapshot.py + render_consensus_snapshot_html.py 生成 · 数据仅作决策参考</div>
</div></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(ROOT / "reports" / "consensus"))
    args = ap.parse_args()
    snap_path = ROOT / "data" / "consensus" / "consensus_daily_snapshot.json"
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    latest = snap["meta"]["latest_date"]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{latest}.html"
    out.write_text(render(snap), encoding="utf-8")
    print(f"OK  → {out} ({out.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
