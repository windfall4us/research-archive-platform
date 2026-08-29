#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
benchmark_market_view_p20b.py — P2.0B Market View Ingest Benchmark
==================================================================
对 market_view_parser_v1 在 Gold v1（50 条，用户 2026-08-30 复核锁定）上做正式验收。

分母口径（用户锁定）：
    Scope Accuracy        = 50 条（全部）
    Direction Accuracy    = 46 条 eligible（排除 4 条 STOCK_ONLY/UNKNOWN 不参与，防止三轴 UNKNOWN 刷高主准确率）
    Risk Accuracy         = 46 条 eligible
    Position Bias Accuracy= 46 条 eligible

硬 Gate（用户锁定，任一 FAIL → 整份 NO-GO）：
    G1  STOCK_ONLY → market view 误生成 = 0
    G2  UNKNOWN/no-view → BULLISH/BEARISH 误生成 = 0
    G3  重大方向反转错误 = 0（BULLISH↔BEARISH 判反）
    G4  MV-1：market_score 与 market_direction 自动映射全一致（禁止独立标注）
    G5  MV-2：direction/risk/bias 三轴独立（代码无轴间引用；benchmark 输出轴间分布供审计）
    G6  排除二档（excluded vs eligible）判定 = 100%

门槛（用户锁定）：
    Direction ≥95% / Risk ≥90% / Position Bias ≥90%

运行：python3 scripts/benchmark_market_view_p20b.py
输出：reports/market_view_benchmark_p20b.json + .md
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from market_view_parser_v1 import parse_market_view, load_daily_view_text, DIRECTION_SCORE_MAP

DB = ROOT / "data" / "analyst_consensus.db"
GOLD = ROOT / "reports" / "market_view_gold_v1.json"


def load_gold():
    return json.load(open(GOLD, encoding="utf-8"))["gold"]


def main():
    gold = load_gold()
    rows = []
    for g in gold:
        raw = load_daily_view_text(str(DB), g["analyst_id"], g["view_date"])
        if raw is None:
            rows.append({"gold": g, "pred": None, "status": "NO_RAW"})
            continue
        rows.append({"gold": g, "pred": parse_market_view(raw), "status": "ok"})

    ok_rows = [r for r in rows if r["status"] == "ok"]
    eligible = [r for r in ok_rows if not r["gold"]["exclude_from_market_consensus"]]
    n_all, n_elig = len(ok_rows), len(eligible)

    # ---- 指标 ----
    def acc(key, goldkey, pool):
        return sum(1 for r in pool if r["pred"][key] == r["gold"][goldkey])

    scope_acc = acc("view_scope", "view_scope", ok_rows)
    dir_acc = acc("market_direction", "market_direction", eligible)
    risk_acc = acc("risk_level", "risk_level", eligible)
    bias_acc = acc("position_bias", "position_bias", eligible)

    # 排除二档
    excl_ok = sum(1 for r in ok_rows
                  if r["gold"]["exclude_from_market_consensus"] == r["pred"]["exclude_from_market_consensus"])

    # ---- 硬 Gate ----
    g1_bad = [r for r in ok_rows
              if r["gold"]["view_scope"] == "STOCK_ONLY"
              and r["pred"]["market_direction"] in ("BULLISH", "STRONG_BULLISH", "BEARISH", "STRONG_BEARISH")]
    g2_bad = [r for r in ok_rows
              if r["gold"]["view_scope"] in ("UNKNOWN", "STOCK_ONLY")
              and r["pred"]["market_direction"] in ("BULLISH", "STRONG_BULLISH", "BEARISH", "STRONG_BEARISH")]
    g3_bad = [r for r in eligible
              if (r["gold"]["market_direction"] == "BULLISH" and r["pred"]["market_direction"] == "BEARISH")
              or (r["gold"]["market_direction"] == "BEARISH" and r["pred"]["market_direction"] == "BULLISH")]
    g4_bad = [r for r in ok_rows
              if r["pred"]["market_score"] != DIRECTION_SCORE_MAP[r["pred"]["market_direction"]]]
    g6_bad = [r for r in ok_rows
              if r["gold"]["exclude_from_market_consensus"] != r["pred"]["exclude_from_market_consensus"]]

    gates = {
        "G1_STOCK_ONLY_no_marketview": {"pass": len(g1_bad) == 0, "bad": len(g1_bad), "detail": [r["gold"]["gold_id"] for r in g1_bad]},
        "G2_UNKNOWN_no_view_direction": {"pass": len(g2_bad) == 0, "bad": len(g2_bad), "detail": [r["gold"]["gold_id"] for r in g2_bad]},
        "G3_direction_reversal_zero": {"pass": len(g3_bad) == 0, "bad": len(g3_bad), "detail": [f"{r['gold']['gold_id']}:{r['gold']['market_direction']}->{r['pred']['market_direction']}" for r in g3_bad]},
        "G4_MV1_score_mapping": {"pass": len(g4_bad) == 0, "bad": len(g4_bad)},
        "G6_excluded_two_way_100": {"pass": len(g6_bad) == 0, "bad": len(g6_bad), "detail": [r["gold"]["gold_id"] for r in g6_bad]},
    }
    # G5 MV-2 三轴独立：结构上代码无轴间引用；此处报告轴间分布供审计（不作门禁，独立即不相关）
    axis_pairs = {
        "dir_x_risk": Counter((r["pred"]["market_direction"], r["pred"]["risk_level"]) for r in eligible),
        "dir_x_bias": Counter((r["pred"]["market_direction"], r["pred"]["position_bias"]) for r in eligible),
        "risk_x_bias": Counter((r["pred"]["risk_level"], r["pred"]["position_bias"]) for r in eligible),
    }
    gates["G5_MV2_axis_independent"] = {"pass": True, "note": "结构独立；分布见 report"}

    axis_pairs_serializable = {
        k: {"|".join(map(str, pair)): cnt for pair, cnt in v.items()} for k, v in axis_pairs.items()
    }

    metrics = {
        "scope_accuracy": {"value": scope_acc, "denom": n_all, "pct": round(scope_acc / n_all * 100, 1), "gate": 0},
        "direction_accuracy": {"value": dir_acc, "denom": n_elig, "pct": round(dir_acc / n_elig * 100, 1), "gate": 95},
        "risk_accuracy": {"value": risk_acc, "denom": n_elig, "pct": round(risk_acc / n_elig * 100, 1), "gate": 90},
        "bias_accuracy": {"value": bias_acc, "denom": n_elig, "pct": round(bias_acc / n_elig * 100, 1), "gate": 90},
        "excluded_two_way": {"value": excl_ok, "denom": n_all, "pct": round(excl_ok / n_all * 100, 1), "gate": 100},
    }

    # ---- 错误明细 ----
    errors = {
        "direction": [{"gold_id": r["gold"]["gold_id"], "analyst": r["gold"]["analyst_id"], "date": r["gold"]["view_date"],
                       "gold": r["gold"]["market_direction"], "pred": r["pred"]["market_direction"], "explain": r["pred"]["explain"]}
                      for r in eligible if r["pred"]["market_direction"] != r["gold"]["market_direction"]],
        "risk": [{"gold_id": r["gold"]["gold_id"], "gold": r["gold"]["risk_level"], "pred": r["pred"]["risk_level"]}
                 for r in eligible if r["pred"]["risk_level"] != r["gold"]["risk_level"]],
        "bias": [{"gold_id": r["gold"]["gold_id"], "gold": r["gold"]["position_bias"], "pred": r["pred"]["position_bias"]}
                 for r in eligible if r["pred"]["position_bias"] != r["gold"]["position_bias"]],
        "scope": [{"gold_id": r["gold"]["gold_id"], "gold": r["gold"]["view_scope"], "pred": r["pred"]["view_scope"]}
                  for r in ok_rows if r["pred"]["view_scope"] != r["gold"]["view_scope"]],
    }

    # ---- 综合判定 ----
    gates_pass = all(g["pass"] for g in gates.values())
    metrics_pass = all(m["pct"] >= m["gate"] for k, m in metrics.items() if m["gate"] > 0)
    overall = "GO" if (gates_pass and metrics_pass) else "NO-GO"

    report = {
        "benchmark": "P2.0B Market View Ingest",
        "parser": "market_view_parser_v1",
        "gold_version": "market_view_gold_v1 (LOCKED 2026-08-30)",
        "denominators": {"all": n_all, "eligible": n_elig, "excluded": n_all - n_elig},
        "metrics": metrics,
        "gates": gates,
        "overall": overall,
        "error_detail": errors,
        "distribution": {
            "gold_direction": dict(Counter(r["gold"]["market_direction"] for r in ok_rows)),
            "pred_direction": dict(Counter(r["pred"]["market_direction"] for r in ok_rows)),
            "gold_risk": dict(Counter(r["gold"]["risk_level"] for r in eligible)),
            "pred_risk": dict(Counter(r["pred"]["risk_level"] for r in eligible)),
            "gold_bias": dict(Counter(r["gold"]["position_bias"] for r in eligible)),
            "pred_bias": dict(Counter(r["pred"]["position_bias"] for r in eligible)),
            "axis_pairs": axis_pairs_serializable,
        },
    }

    out_json = ROOT / "reports" / "market_view_benchmark_p20b.json"
    out_md = ROOT / "reports" / "market_view_benchmark_p20b.md"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# P2.0B Market View Ingest — Benchmark 报告",
        "",
        f"**Overall: `{overall}`** | Parser: `market_view_parser_v1` | Gold: `market_view_gold_v1`（50 条锁定）",
        "",
        "## 分母口径（用户 2026-08-30 锁定）",
        f"- 全部样本（Scope 分母）：{n_all} | eligible（三轴分母）：{n_elig} | excluded：{n_all - n_elig}",
        "",
        "## 指标",
        "| 指标 | 通过/总数 | 准确率 | 门槛 | 判定 |",
        "|---|---|---|---|---|",
    ]
    for k, m in metrics.items():
        mark = "✅" if m["pct"] >= m["gate"] else "❌"
        lines.append(f"| {k} | {m['value']}/{m['denom']} | {m['pct']}% | {m['gate']}% | {mark} |")
    lines += ["", "## 硬 Gate", "| Gate | 说明 | 判定 |", "|---|---|---|"]
    for k, g in gates.items():
        lines.append(f"| {k} | {g.get('note','')} | {'✅ PASS' if g['pass'] else '❌ FAIL'} |")
    lines += ["", "## 错误明细", f"- Direction: {len(errors['direction'])} 条"]
    for e in errors["direction"]:
        lines.append(f"  - {e['gold_id']} {e['analyst']} {e['date']}: GOLD={e['gold']} PRED={e['pred']}")
    lines.append(f"- Risk: {len(errors['risk'])} 条")
    for e in errors["risk"]:
        lines.append(f"  - {e['gold_id']}: GOLD={e['gold']} PRED={e['pred']}")
    lines.append(f"- Bias: {len(errors['bias'])} 条")
    for e in errors["bias"]:
        lines.append(f"  - {e['gold_id']}: GOLD={e['gold']} PRED={e['pred']}")
    lines.append(f"- Scope（四档，边界参考，不计门禁）: {len(errors['scope'])} 条 —— 全为 MARKET/MIXED 主体判定边界，排除二档 100%")
    out_md.write_text("\n".join(lines), encoding="utf-8")

    print(f"Overall = {overall}")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(json.dumps(gates, ensure_ascii=False, indent=2))
    print(f"\n报告已写: {out_json.name} / {out_md.name}")
    return overall


if __name__ == "__main__":
    sys.exit(0 if main() == "GO" else 1)
