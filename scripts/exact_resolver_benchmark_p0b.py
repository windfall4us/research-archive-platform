#!/usr/bin/env python3
"""0B.3 步骤④⑤⑦: EXACT + ALIAS Resolver + Gold Sample Benchmark（分层版）。

规则（用户决策）:
- EXACT: 仅 标准证券名称 == raw_target（strip/全角→半角/空白压缩，禁删-U/股份/科技/模糊）
- ALIAS: 名称精确命中 stock_aliases（人工审核维护，CONFIRMED）
- OUT_OF_SCOPE: 已识别对象但不属A股解析范围（非A股，如中国金茂/阿里巴巴）
- UNRESOLVED: 理论上属A股但无法解析 → 不计算、不猜测
- WRONG_MATCH: 解析到错误标的（Precision 首则）

指标口径（用户修正 2026-08-28）:
- Precision = 正确命中 / (正确命中 + 错误命中)，分母不含 UNRESOLVED/OUT_OF_SCOPE
- Recall = 正确命中 / A_SHARE_RESOLVABLE
- 分层输出: Exact / Exact+Alias / Overall（含 CONTEXT/FUZZY，当前关闭为0）

输出: reports/stock_exact_benchmark_p0b.json + .md
"""
import csv, json, re, sqlite3
from pathlib import Path

ROOT = Path("/home/windfall/workspace/research-archive-platform")
DB = ROOT / "data/security_master.db"
GS = ROOT / "data/analyst_snapshots/gold_sample_100.csv"
REPORT_DIR = ROOT / "reports"
REPORT_DIR.mkdir(exist_ok=True)


def normalize(s):
    if not s: return ""
    s = s.replace("\u3000", " ")          # 全角空格→半角
    s = re.sub(r"\s+", " ", s).strip()    # 连续空白压缩
    return s


def main():
    con = sqlite3.connect(DB)
    name_to_code = {r[0]: r[1] for r in con.execute("SELECT stock_name, stock_code FROM stock_master")}
    code_set = set(r[0] for r in con.execute("SELECT stock_code FROM stock_master"))
    alias_to_code = {normalize(r[0]): r[1] for r in con.execute("SELECT alias, stock_code FROM stock_aliases")}
    out_of_scope = {normalize(r[0]) for r in con.execute("SELECT raw_name FROM out_of_scope")}
    con.close()

    # 载入 Gold Sample（entity_type_draft=STOCK）
    rows = list(csv.DictReader(open(GS, encoding="utf-8")))
    stock_rows = [r for r in rows if r["entity_type_draft"] == "STOCK"]
    non_stock = [r for r in rows if r["entity_type_draft"] != "STOCK"]

    # 题材/板块/描述性对象（已错标 STOCK，实为 THEME/描述）→ EXCLUDED（不进解析基准）
    theme_patterns = [r"材料$", r"硅片", r"资源", r"金属", r"折叠屏", r"冷液", r"液冷",
                      r"产业链", r"相关$", r"板块", r"方向", r"概念"]
    theme_re = re.compile("|".join(theme_patterns))

    stats = {"gold_total": len(stock_rows),
             "a_share_resolvable": 0, "out_of_scope": 0, "ambiguous": 0, "excluded": 0,
             "exact": 0, "alias": 0, "context": 0, "fuzzy": 0,
             "unresolved": 0, "wrong_match": 0}
    details = []
    unresolved_hist = {}

    for r in stock_rows:
        raw = r["raw_target"]
        name_part = re.sub(r"\((?:60|68|00|30|92|83|43)\d{4}\)", "", raw).strip()
        code_in = re.search(r"(60|68|00|30|92|83|43)\d{4}", raw)
        norm = normalize(name_part)

        # 1) OUT_OF_SCOPE: 已识别非A股对象（中国金茂/阿里巴巴/腾讯...）
        if norm in out_of_scope:
            stats["out_of_scope"] += 1
            details.append({"sample_id": r["sample_id"], "raw_target": raw,
                            "bucket": "OUT_OF_SCOPE", "method": "OUT_OF_SCOPE", "matched": None})
            continue
        # 2) EXCLUDED: 题材/板块类误标
        if theme_re.search(name_part):
            stats["excluded"] += 1
            details.append({"sample_id": r["sample_id"], "raw_target": raw,
                            "bucket": "EXCLUDED_THEME", "method": "EXCLUDED", "matched": None})
            continue
        # 进入 A_SHARE_RESOLVABLE
        stats["a_share_resolvable"] += 1

        # 3) 内联代码验证（EXACT）
        if code_in:
            code = code_in.group(0)
            if code in code_set:
                stats["exact"] += 1
                details.append({"sample_id": r["sample_id"], "raw_target": raw,
                                "bucket": "A_SHARE_RESOLVABLE", "method": "EXACT_INLINE_CODE",
                                "code": code, "matched": code})
            else:
                stats["wrong_match"] += 1
                details.append({"sample_id": r["sample_id"], "raw_target": raw,
                                "bucket": "A_SHARE_RESOLVABLE", "method": "EXACT_INLINE_CODE",
                                "code": code, "matched": None, "error": "code not in master"})
            continue

        # 4) EXACT: 标准名称精确命中
        if norm in name_to_code:
            stats["exact"] += 1
            details.append({"sample_id": r["sample_id"], "raw_target": raw,
                            "bucket": "A_SHARE_RESOLVABLE", "method": "EXACT",
                            "code": name_to_code[norm], "matched": name_to_code[norm]})
            continue

        # 5) ALIAS: 人工审核别名精确命中
        if norm in alias_to_code:
            code = alias_to_code[norm]
            if code in code_set:
                stats["alias"] += 1
                details.append({"sample_id": r["sample_id"], "raw_target": raw,
                                "bucket": "A_SHARE_RESOLVABLE", "method": "ALIAS",
                                "code": code, "matched": code})
            else:
                stats["wrong_match"] += 1
                details.append({"sample_id": r["sample_id"], "raw_target": raw,
                                "bucket": "A_SHARE_RESOLVABLE", "method": "ALIAS",
                                "code": code, "matched": None, "error": "alias code not in master"})
            continue

        # 6) UNRESOLVED: 不猜测，进下一阶段
        stats["unresolved"] += 1
        unresolved_hist[norm] = unresolved_hist.get(norm, 0) + 1
        details.append({"sample_id": r["sample_id"], "raw_target": raw,
                        "bucket": "A_SHARE_RESOLVABLE", "method": "UNRESOLVED", "matched": None})

    # ---- 指标（用户修正口径）----
    resolvable = stats["a_share_resolvable"]
    correct = stats["exact"] + stats["alias"]
    wrong = stats["wrong_match"]
    matched = correct + stats["context"] + stats["fuzzy"]

    def pct(num, den):
        return round(num / den, 4) if den else 0.0

    stats["exact_precision"] = pct(stats["exact"], stats["exact"] + wrong)
    stats["exact_recall"] = pct(stats["exact"], resolvable)
    stats["exact_alias_precision"] = pct(correct, correct + wrong)
    stats["exact_alias_recall"] = pct(correct, resolvable)
    stats["overall_precision"] = pct(matched, matched + wrong)
    stats["overall_recall"] = pct(matched, resolvable)
    stats["unresolved_top"] = sorted(unresolved_hist.items(), key=lambda x: -x[1])[:30]

    report = {"stats": stats, "details": details,
              "non_stock_buckets": {r["sample_id"]: r["entity_type_draft"] for r in non_stock}}
    out_json = REPORT_DIR / "stock_exact_benchmark_p0b.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    md = REPORT_DIR / "stock_exact_benchmark_p0b.md"
    md.write_text(f"""# Stock Resolver Benchmark (0B.3 EXACT+ALIAS 分层)

## 桶分布
- Gold Total (STOCK): {stats['gold_total']}
- A_SHARE_RESOLVABLE: {stats['a_share_resolvable']}
- OUT_OF_SCOPE: {stats['out_of_scope']}
- AMBIGUOUS: {stats['ambiguous']}
- EXCLUDED (题材类): {stats['excluded']}

## 各层命中
- EXACT matched: {stats['exact']}
- ALIAS matched: {stats['alias']}
- CONTEXT matched: {stats['context']} (未启用)
- FUZZY matched: {stats['fuzzy']} (未启用)
- UNRESOLVED: {stats['unresolved']}
- WRONG_MATCH: {stats['wrong_match']}

## 分层指标（A_SHARE_RESOLVABLE = {stats['a_share_resolvable']}）
| 层 | Precision | Recall |
|---|---|---|
| EXACT | {stats['exact_precision']:.1%} | {stats['exact_recall']:.1%} |
| EXACT+ALIAS | {stats['exact_alias_precision']:.1%} | {stats['exact_alias_recall']:.1%} |
| Overall (含CONTEXT/FUZZY) | {stats['overall_precision']:.1%} | {stats['overall_recall']:.1%} |

## UNRESOLVED TOP（下一阶段输入）
""", encoding="utf-8")
    with open(md, "a", encoding="utf-8") as f:
        if stats["unresolved_top"]:
            for name, cnt in stats["unresolved_top"]:
                f.write(f"- {name} ({cnt})\n")
        else:
            f.write("(无)\n")

    print(json.dumps(stats, ensure_ascii=False, indent=1))
    print("\n报告:", out_json, md)


if __name__ == "__main__":
    main()
