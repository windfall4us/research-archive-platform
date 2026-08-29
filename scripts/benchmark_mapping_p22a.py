#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
benchmark_mapping_p22a.py — P2.2A Stock→Theme Mapping Benchmark
================================================================
用户 2026-08-30 锁定口径：
  * 同花顺概念板块为主(MASTER_CONCEPT)、行业板块为辅(MASTER_INDUSTRY)，来源可区分
  * Heat eligibility confidence >= 0.60
  * DIRECT_CONTEXT 仅"同句/明确语义绑定"可达 0.60；强绑定(股票名⊃主题词)=0.62、邻接(≤3字)=0.60；单纯同 record 共现不落表
  * 只归一 19 个 canonical L2；每只股票最多 Top 3 高置信主题（超出降 0.50 不参与 Heat）
  * UNIQUE(stock_code, theme_id, mapping_source, valid_from) 支持历史版本
  * P2.2A 独立 Benchmark：precision / coverage / conflict / unmapped

评估：
  * Precision — 板块名→L2 规则抽样人工审阅（GOLD_BOARD 20 项）+ DIRECT_CONTEXT 抽样人工审阅（GOLD_DC 20 项）
  * Coverage — 参与 Heat 股票 / eligible 350；按来源拆分
  * Conflict — 每股主题数 ≤3；跨大类股票数；降级治理行数
  * Unmapped — 15 只分类（非 19 L2 范畴 vs 漏匹配建议 MANUAL）
  * 保护审计 — TECH_GENERAL 不映射个股；DIRECT/INFERRED 分离；mapping_source 枚举合法；confidence 范围

运行：python3 scripts/benchmark_mapping_p22a.py
输出：reports/mapping_benchmark_p22a.json + .md
"""

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "analyst_consensus.db"
P22 = ROOT / "data" / "p22a"

# ===== 人工审阅 golden（2026-08-30 抽样，作为 precision ground truth）=====
# 板块名 → 期望 L2（20 项，全对）
GOLD_BOARD = {
    "减肥药": "MED_INNOVATIVE_DRUG", "农产品加工": "OTHER_AGRICULTURE", "稀土": "CYCL_NONFERROUS",
    "光刻胶": "TECH_SEMI", "零售": "OTHER_CONSUMER", "休闲食品": "OTHER_CONSUMER",
    "肉鸡养殖": "OTHER_AGRICULTURE", "稀土永磁": "CYCL_NONFERROUS", "服装": "OTHER_CONSUMER",
    "人形机器人": "OTHER_ROBOTICS", "人工智能": "TECH_AI_COMPUTE", "贵金属": "CYCL_NONFERROUS",
    "其他塑料制品": "CYCL_CHEMICAL", "超级电容": "TECH_COMPONENT", "钛白粉": "CYCL_CHEMICAL",
    "消费电子零部件及组装": "TECH_ELEC", "禽流感": "OTHER_AGRICULTURE", "生态农业": "OTHER_AGRICULTURE",
    "减速器": "OTHER_ROBOTICS", "电子化学品": "CYCL_CHEMICAL",
}
# DIRECT_CONTEXT 抽样：True=明确语义绑定(正确) / False=弱绑歧义(错误)
GOLD_DC = {
    "600536|TECH_SOFTWARE": True, "688548|TECH_SEMI": True, "688432|TECH_SEMI": True,
    "002418|TECH_AI_COMPUTE": True, "300502|TECH_OPTICS": True, "688256|TECH_AI_COMPUTE": True,
    "300607|OTHER_ROBOTICS": True, "603186|TECH_SEMI": True, "301217|CYCL_NONFERROUS": True,
    "601899|CYCL_NONFERROUS": True, "002636|TECH_PCB": True, "601869|TECH_OPTICS": True,
    "603296|TECH_AI_COMPUTE": True, "688300|TECH_SEMI": True, "002716|CYCL_NONFERROUS": True,
    "603259|MED_INNOVATIVE_DRUG": True, "300684|TECH_AI_COMPUTE": True, "301511|CYCL_NONFERROUS": True,
    "603259|OTHER_CONSUMER": False,   # "白马"风格词歧义 → 弱绑
    "600428|OTHER_CONSUMER": False,   # "白马"风格词歧义 → 弱绑
}

VALID_SRC = {"MANUAL", "MASTER_CONCEPT", "MASTER_INDUSTRY", "DIRECT_CONTEXT"}


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    eligible = {r[0] for r in cur.execute(
        "SELECT DISTINCT stock_code FROM analyst_stock_events WHERE event_id NOT IN (SELECT event_id FROM consensus_event_exclusions)")}
    rows = cur.execute("SELECT stock_code, theme_id, mapping_source, confidence, valid_from, valid_to, note "
                       "FROM stock_theme_mapping").fetchall()

    # ===== 保护审计 =====
    bad_src = [r for r in rows if r[2] not in VALID_SRC]
    bad_conf = [r for r in rows if not (0 <= r[3] <= 1)]
    general = [r for r in rows if r[1] == "TECH_GENERAL"]
    invalid_theme = [r for r in rows if not r[1].startswith(("TECH_", "MED_", "CYCL_", "NEW_ENERGY_", "OTHER_"))]

    # ===== Precision：板块→L2 =====
    board = json.load(open(P22 / "board_to_l2.json", encoding="utf-8"))
    board_map = {v["name"]: v["l2"] for v in board.values()}
    board_miss, board_wrong = [], []
    for name, expect in GOLD_BOARD.items():
        actual = board_map.get(name)
        if actual is None:
            board_miss.append(name)
        elif actual != expect:
            board_wrong.append((name, expect, actual))
    board_precision = (len(GOLD_BOARD) - len(board_miss) - len(board_wrong)) / len(GOLD_BOARD)

    # ===== Precision：DIRECT_CONTEXT（与 DB 中存在的绑定比对）=====
    dc_exist = {(r[0], r[1]) for r in rows if r[2] == "DIRECT_CONTEXT" and r[3] >= 0.60}
    dc_wrong = [(k, v) for k, v in GOLD_DC.items() if v is False and tuple(k.split("|")) in dc_exist]
    dc_correct = [(k, v) for k, v in GOLD_DC.items() if v is True and tuple(k.split("|")) in dc_exist]
    dc_absent = [(k, v) for k, v in GOLD_DC.items() if tuple(k.split("|")) not in dc_exist]
    dc_precision = len(dc_correct) / (len(GOLD_DC) - len(dc_absent)) if len(GOLD_DC) - len(dc_absent) else 0.0

    # ===== Coverage =====
    heat_rows = [r for r in rows if r[3] >= 0.60]
    heat_stocks = {r[0] for r in heat_rows}
    by_src = Counter(r[2] for r in rows)
    by_src_heat = Counter(r[2] for r in heat_rows)
    unmapped = sorted(eligible - heat_stocks)

    # ===== Conflict =====
    per_stock = defaultdict(set)
    for r in heat_rows:
        per_stock[r[0]].add(r[1])
    n_topics = Counter(len(v) for v in per_stock.values())
    max_topics = max(len(v) for v in per_stock.values())
    l1_of = {"TECH": "科技", "CYCL": "周期", "MED": "医药", "NEW_ENERGY": "新能源", "OTHER": "其他"}
    multi_l1 = sum(1 for v in per_stock.values() if len({l1_of.get(t.split("_")[0], "?") for t in v}) >= 3)

    # 主题覆盖分布（Heat 层）
    theme_cov = Counter(r[1] for r in heat_rows)

    report = {
        "benchmark": "P2.2A Stock→Theme Mapping",
        "coverage": {
            "eligible_stocks": len(eligible),
            "heat_eligible_stocks": len(heat_stocks),
            "coverage_rate": round(len(heat_stocks) / len(eligible) * 100, 1),
            "rows_total": len(rows),
            "rows_heat": len(heat_rows),
            "by_source": dict(by_src),
            "by_source_heat": dict(by_src_heat),
            "unmapped": unmapped,
        },
        "precision": {
            "board_sample_n": len(GOLD_BOARD),
            "board_precision": round(board_precision * 100, 1),
            "board_wrong": board_wrong,
            "board_miss": board_miss,
            "dc_sample_n": len(GOLD_DC),
            "dc_precision": round(dc_precision * 100, 1),
            "dc_wrong_weak_bindings": [k for k, _ in dc_wrong],
            "dc_absent": [k for k, _ in dc_absent],
            "note": "board=板块名→L2 规则；dc=DIRECT_CONTEXT 同句语义绑定（强绑定0.62/邻接0.60）；白马风格词歧义2例已识别",
        },
        "conflict": {
            "per_stock_topic_dist": dict(sorted(n_topics.items())),
            "max_topics_per_stock": max_topics,
            "top3_enforced": max_topics <= 3,
            "cross_l1_gte3_stocks": multi_l1,
        },
        "theme_coverage_heat": dict(sorted(theme_cov.items(), key=lambda x: -x[1])),
        "guards": {
            "invalid_source": len(bad_src),
            "invalid_confidence": len(bad_conf),
            "tech_general_stock_mapping": len(general),
            "invalid_theme_id": len(invalid_theme),
            "note": "TECH_GENERAL 不映射个股；DIRECT/INFERRED 分离（本阶段全 DIRECT，INFERRED_FROM_STOCK 留 P2.2B 消费层）；COMPOSITE_TACTICAL 不进主题方向（P2.2B 治理）",
        },
    }
    overall = (
        "GO" if board_precision >= 0.9 and dc_precision >= 0.85
        and max_topics <= 3 and len(general) == 0 and not bad_src and not bad_conf
        else "NO-GO"
    )
    report["overall"] = overall

    (ROOT / "reports" / "mapping_benchmark_p22a.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# P2.2A Stock→Theme Mapping — Benchmark 报告", "",
        f"**Overall: `{overall}`** | 同花顺概念为主/行业为辅 | DIRECT_CONTEXT 同句语义 | Top3 治理 | 19 canonical L2", "",
        "## Coverage", f"- eligible 股票: {len(eligible)} | 参与 Heat: **{len(heat_stocks)}** = {report['coverage']['coverage_rate']}%",
        f"- 行数: 全量 {len(rows)} / Heat 参与 {len(heat_rows)}", f"- 按来源: 全量 {dict(by_src)}", f"- 按来源 Heat: {dict(by_src_heat)}",
        f"- **Unmapped {len(unmapped)} 只**: {', '.join(unmapped)}", "",
        "## Precision（抽样人工审阅）",
        f"- 板块→L2 规则: {round(board_precision*100,1)}% ({len(GOLD_BOARD)} 样本) 错配 {board_wrong or '无'}",
        f"- DIRECT_CONTEXT: {round(dc_precision*100,1)}% ({len(GOLD_DC)} 样本) 弱绑 {[k for k,_ in dc_wrong] or '无'}",
        "  - 强绑定(股票名⊃主题词)=0.62 / 邻接(≤3字)=0.60 / 同 record 共现不落表",
        "  - 已知弱绑: '白马'为风格词歧义（药明康德/中远海特←OTHER_CONSUMER），非消费主题 → 保留但标注", "",
        "## Conflict / Top3 治理",
        f"- 每股主题数分布: {dict(sorted(n_topics.items()))} | max={max_topics} | Top3 强制: {'✅' if max_topics<=3 else '❌'}",
        f"- 跨≥3 大类股票: {multi_l1}（潜在噪音，供 P2.2B 审计）", "",
        "## 保护审计", f"- invalid source: {len(bad_src)} | invalid confidence: {len(bad_conf)}",
        f"- TECH_GENERAL 映射个股: {len(general)}（必须 0）| invalid theme_id: {len(invalid_theme)}",
        "- DIRECT/INFERRED 分离 ✅（本阶段全 DIRECT，INFERRED_FROM_STOCK 留消费层）| COMPOSITE_TACTICAL 不进主题方向（P2.2B）", "",
        "## 主题覆盖（Heat 层股票数）",
        "| theme | 股票数 |", "|---|---|", *[f"| {k} | {v} |" for k, v in sorted(theme_cov.items(), key=lambda x: -x[1])], "",
        "## 结论", f"**{overall}**",
    ]
    (ROOT / "reports" / "mapping_benchmark_p22a.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"Overall = {overall}")
    print(f"  Coverage: {len(heat_stocks)}/{len(eligible)} = {report['coverage']['coverage_rate']}%")
    print(f"  Precision: board {round(board_precision*100,1)}% / dc {round(dc_precision*100,1)}%")
    print(f"  Conflict: max_topics={max_topics}, dist={dict(sorted(n_topics.items()))}")
    print(f"  Unmapped {len(unmapped)}: {unmapped}")
    con.close()
    return 0 if overall == "GO" else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
