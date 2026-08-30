#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cross_layer_readiness_p40.py — P4.0 Cross-Layer Readiness（个股×主题联动盘点）
===============================================================================
回答 Phase 4 的第一个问题：Phase 2 主题层（heat/momentum）与 Phase 3 个股层
（consensus/action flow）之间能否可靠连接，连接后的覆盖与空白。

连接键：stock_theme_mapping（P2.2A，conf>=0.60 为 heat 映射）
  - 350 只 eligible 股票中多少能映射到 19 L2 主题
  - 每股映射主题数（P2.2A Top3 治理，≤3）
  - 每主题覆盖多少只有 consensus 的 eligible 股票
  - 个股能否拿到其主题的 heat + momentum（日期对齐：主题 8 天 × 19 L2 = 152 行）
  - 缺主题映射的股票清单（P2.2A unmapped 13 只）

输出：data/p40/cross_layer_readiness.json + reports/cross_layer_readiness_p40.md
用法：python3 scripts/cross_layer_readiness_p40.py
"""
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "analyst_consensus.db"
HEAT_JSON = ROOT / "data" / "p22c" / "theme_heat_scores.json"
MOM_JSON = ROOT / "data" / "p23" / "theme_momentum.json"
P33_JSON = ROOT / "data" / "p33" / "stock_consensus_score.json"
P30_JSON = ROOT / "data" / "p30" / "stock_consensus_readiness.json"
OUT_JSON = ROOT / "data" / "p40" / "cross_layer_readiness.json"
OUT_MD = ROOT / "reports" / "cross_layer_readiness_p40.md"
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

HEAT_MIN = 0.60

db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row
c = db.cursor()

# ---------- 1. 个股层（P3.3 全 350 只） ----------
p33 = json.loads(P33_JSON.read_text(encoding="utf-8"))["per_stock"]
p30 = json.loads(P30_JSON.read_text(encoding="utf-8"))
eligible_stocks = set(p30["events"]["stocks"]) if False else set(p33.keys())
all_stocks = set(p33.keys())  # 350

# ---------- 2. 主题层 ----------
heat = json.loads(HEAT_JSON.read_text(encoding="utf-8"))   # 152 行 list
mom = json.loads(MOM_JSON.read_text(encoding="utf-8"))     # 152 行 list
theme_ids_heat = {r["theme_id"] for r in heat}
theme_ids_mom = {r["theme_id"] for r in mom}
theme_dates = sorted({r["date"] for r in heat})
theme_ids = sorted(theme_ids_heat & theme_ids_mom)
print(f"主题层: {len(theme_dates)} 天 × {len(theme_ids)} 主题（heat+momentum 均有）= {len(heat)} 行")

# ---------- 3. stock_theme_mapping（conf>=0.6 heat 映射，按 distinct theme 去重） ----------
mappings = [dict(r) for r in c.execute(
    """SELECT stock_code, theme_id, mapping_source, confidence FROM stock_theme_mapping
       WHERE confidence >= ?""", (HEAT_MIN,))]
map_by_stock = defaultdict(list)
map_by_theme = defaultdict(list)
# 同股同主题多 source 行 → 保留 confidence 最高一条（P2.2A Top3 治理按 distinct theme）
for m in sorted(mappings, key=lambda x: -x["confidence"]):
    existing = {mm["theme_id"] for mm in map_by_stock[m["stock_code"]]}
    if m["theme_id"] in existing:
        continue
    map_by_stock[m["stock_code"]].append(m)
    map_by_theme[m["theme_id"]].append(m)

mapped_stocks = set(map_by_stock.keys())          # 337
unmapped_stocks = sorted(all_stocks - mapped_stocks)  # 13
print(f"映射: {len(mapped_stocks)}/{len(all_stocks)} 股票有 heat 映射; unmapped {len(unmapped_stocks)}")

# 主题是否在 19 L2 内（p22b 定义的 canonical）
CANONICAL_L2 = [
    "TECH_SEMI", "TECH_OPTICS", "TECH_AI_COMPUTE", "TECH_COMPONENT", "TECH_PCB",
    "TECH_ELEC", "TECH_SOFTWARE", "TECH_GENERAL",
    "MED_INNOVATIVE_DRUG",
    "CYCL_NONFERROUS", "CYCL_CHEMICAL",
    "NEW_ENERGY_SOLID_BATTERY", "NEW_ENERGY_ELECTROLYTE", "NEW_ENERGY_UHV",
    "OTHER_BROKER", "OTHER_AGRICULTURE", "OTHER_ROBOTICS", "OTHER_SPACE", "OTHER_CONSUMER",
]
canonical_set = set(CANONICAL_L2)
mapped_theme_ids = set(map_by_theme.keys())
missing_canonical = sorted(canonical_set - mapped_theme_ids)  # 无股票映射的 canonical L2
print(f"映射涉及 {len(mapped_theme_ids)} 主题; canonical 19 中缺 {missing_canonical}")

# ---------- 4. 每股 → 主题链接 + 主题可得的 heat/momentum ----------
# heat/momentum 按 (date, theme) 索引
heat_index = {(r["date"], r["theme_id"]): r for r in heat}
mom_index = {(r["date"], r["theme_id"]): r for r in mom}
latest_heat_by_theme = {}
latest_mom_by_theme = {}
for tid in theme_ids:
    # 取该主题最后一天的 heat/momentum（最新状态）
    tdates = sorted({r["date"] for r in heat if r["theme_id"] == tid})
    if tdates:
        ld = tdates[-1]
        latest_heat_by_theme[tid] = heat_index.get((ld, tid))
        latest_mom_by_theme[tid] = mom_index.get((ld, tid))

per_stock_link = {}
for code in sorted(all_stocks):
    links = []
    for m in map_by_stock.get(code, []):
        tid = m["theme_id"]
        h = latest_heat_by_theme.get(tid)
        mm = latest_mom_by_theme.get(tid)
        links.append({
            "theme_id": tid,
            "mapping_source": m["mapping_source"],
            "confidence": m["confidence"],
            "theme_heat_available": h is not None,
            "theme_momentum_available": mm is not None,
            "theme_heat": h["heat_score"] if h else None,
            "theme_heat_status": h["heat_status"] if h else None,
            "theme_momentum": mm["effective_momentum_state"] if mm else None,
        })
    per_stock_link[code] = {
        "stock_code": code,
        "n_themes": len(links),
        "mapped": len(links) > 0,
        "links": links,
    }

# ---------- 5. 每主题覆盖 ----------
per_theme = {}
for tid in sorted(theme_ids):
    stocks = sorted({m["stock_code"] for m in map_by_theme.get(tid, [])})
    # 这些股票里多少在 eligible 350 内（有 consensus）
    with_consensus = [s for s in stocks if s in all_stocks]
    # 每股 consensus state 分布
    states = Counter(p33[s]["consensus_state"] for s in with_consensus)
    per_theme[tid] = {
        "theme_id": tid,
        "n_mapped_stocks": len(stocks),
        "n_eligible_with_consensus": len(with_consensus),
        "consensus_state_dist": dict(states),
        "stocks": with_consensus,
    }

# ---------- 6. 跨层 joinability ----------
n_linked = sum(1 for v in per_stock_link.values() if v["mapped"])
n_linked_with_heat = sum(1 for v in per_stock_link.values()
                         if v["mapped"] and any(l["theme_heat_available"] for l in v["links"]))
n_linked_with_mom = sum(1 for v in per_stock_link.values()
                        if v["mapped"] and any(l["theme_momentum_available"] for l in v["links"]))

# 每股主题数分布
n_themes_dist = Counter(v["n_themes"] for v in per_stock_link.values())

result = {
    "generated_at": "P4.0 v1",
    "connect_key": "stock_theme_mapping (conf>=0.60 heat 映射)",
    "theme_layer": {
        "n_dates": len(theme_dates),
        "dates": theme_dates,
        "n_themes": len(theme_ids),
        "theme_ids": theme_ids,
        "heat_rows": len(heat),
        "momentum_rows": len(mom),
    },
    "stock_layer": {"n_eligible": len(all_stocks)},
    "mapping": {
        "n_mapped_stocks": len(mapped_stocks),
        "n_unmapped_stocks": len(unmapped_stocks),
        "unmapped_stocks": unmapped_stocks,
        "n_mapping_rows": sum(len(v) for v in map_by_stock.values()),
        "n_themes_with_stocks": len(mapped_theme_ids),
        "missing_canonical_L2": missing_canonical,
        "mapping_source_dist": dict(Counter(mm["mapping_source"] for v in map_by_stock.values() for mm in v)),
    },
    "cross_layer_joinability": {
        "n_stocks_with_theme_link": n_linked,
        "n_stocks_with_theme_heat": n_linked_with_heat,
        "n_stocks_with_theme_momentum": n_linked_with_mom,
        "n_themes_distribution": dict(sorted(n_themes_dist.items())),
        "coverage_rate": round(n_linked / len(all_stocks) * 100, 2) if all_stocks else 0,
    },
    "per_theme": per_theme,
    "per_stock_link": per_stock_link,
}
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

# ---------- 报告 ----------
md = f"""# P4.0 Cross-Layer Readiness — 个股×主题联动盘点

日期：2026-08-30　连接键：stock_theme_mapping（conf>=0.60 heat 映射）

## 主题层（Phase 2）
- {len(theme_dates)} 个交易日 × {len(theme_ids)} 个主题（heat+momentum 均有）= {len(heat)} 行
- 日期：{theme_dates[0]} ~ {theme_dates[-1]}

## 个股层（Phase 3）
- eligible 股票：{len(all_stocks)}（全有 consensus）

## 映射
- 有 heat 映射：**{len(mapped_stocks)}/{len(all_stocks)}**（{result['cross_layer_joinability']['coverage_rate']}%）
- 无映射：{len(unmapped_stocks)} 只 → {unmapped_stocks}
- 映射涉及主题数：{len(mapped_theme_ids)}；canonical 19 中缺（无股票映射）：{missing_canonical}
- 映射源分布：{json.dumps(result['mapping']['mapping_source_dist'], ensure_ascii=False)}

## 跨层可连接性
| 指标 | 值 |
| --- | --- |
| 有主题链接的股票 | {n_linked} |
| 链接主题有 heat 的股票 | {n_linked_with_heat} |
| 链接主题有 momentum 的股票 | {n_linked_with_mom} |
| 每股主题数分布 | {json.dumps(dict(sorted(n_themes_dist.items())), ensure_ascii=False)} |

## 每主题覆盖（eligible 股票 consensus state 分布）
| 主题 | 映射股票数 | eligible 数 | consensus 分布 |
| --- | --- | --- | --- |
{chr(10).join(f"| {t} | {v['n_mapped_stocks']} | {v['n_eligible_with_consensus']} | {json.dumps(v['consensus_state_dist'], ensure_ascii=False)} |" for t, v in sorted(per_theme.items()))}

## P4.0 结论
- 跨层连接可用：{n_linked}/{len(all_stocks)} 股票可经主题链接到 heat+momentum（覆盖率 {result['cross_layer_joinability']['coverage_rate']}%）
- 空白：{len(unmapped_stocks)} 只无映射（P2.2A 保留 unmapped 的决策维持）；{missing_canonical or '无'} canonical L2 无股票映射（TECH_GENERAL 等无个股映射主题，靠 DIRECT mention 舆情通道）
"""
with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write(md)

print(f"主题层 {len(theme_dates)} 天 × {len(theme_ids)} 主题 = {len(heat)} 行")
print(f"映射 {len(mapped_stocks)}/{len(all_stocks)} ({result['cross_layer_joinability']['coverage_rate']}%)，unmapped {len(unmapped_stocks)}")
print(f"每股主题数分布: {dict(sorted(n_themes_dist.items()))}")
print(f"canonical 缺失: {missing_canonical}")
print("每主题覆盖(eligible):")
for t, v in sorted(per_theme.items()):
    print(f"  {t}: mapped={v['n_mapped_stocks']} eligible={v['n_eligible_with_consensus']} states={json.dumps(v['consensus_state_dist'], ensure_ascii=False)}")
print(f"输出: {OUT_JSON}")
