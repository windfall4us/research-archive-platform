#!/usr/bin/env python3
"""0B.5 Parser v1.1 正式 Benchmark（对冻结 Gold Sample v1 FINAL 盲测）。

指标（用户 2026-08-28 设计）:
- 输入 = CORE events（从冻结 Gold FINAL 程序化计算，不硬编码 112）
- 事件匹配 = multiset/Counter matching（非普通集合交集，避免同三元组去重失真）
- Event Precision / Recall / F1
- Event-count accuracy（行级：pred 事件数与 gold 一致）
- Action exact / Action-family
- Status accuracy / Temporal accuracy（按 action 对齐后判定）
- 高风险错误矩阵（WATCH→BUY、持仓→今日BUY、INTENDED→EXECUTED、CONDITIONAL→EXECUTED、
  PAST BUY→TODAY BUY、推荐→BUY、false executed buy/sell）

Gold v1 FINAL 冻结：本脚本只读不写，Parser 有出入只改 Parser。
"""
import csv
import json
import sys
from collections import Counter, defaultdict

sys.path.insert(0, "scripts")
from action_temporal_parser_v11_p0b import parse

GOLD = "data/analyst_snapshots/gold_sample_100_final.json"
OUT_CSV = "reports/benchmark_v11_mismatches.csv"

FAMILY = {"BUY": "buy", "LOW_BUY": "buy", "ADD": "buy", "TRIAL": "buy",
          "REDUCE": "sell", "SELL": "sell", "CLEAR": "sell",
          "HOLD": "hold", "WATCH": "watch", "DO_T": "dot", "UNKNOWN": "unk"}
BUYFAM = {"BUY", "LOW_BUY", "ADD", "TRIAL"}
SELLFAM = {"REDUCE", "SELL", "CLEAR"}


def core_rows(d):
    return [r for r in d if not r["ambig"] and not r["exclude_from_core_benchmark"]]


def triples(r):
    return [(e["action"], e["action_status"], e["temporal_type"]) for e in r["events"]]


def main():
    d = json.load(open(GOLD, encoding="utf-8"))
    rows = core_rows(d)
    gold_events = sum(len(r["events"]) for r in rows)
    print(f"Gold CORE rows {len(rows)} | CORE events {gold_events}（程序化计数）")

    # 收集指标
    n_rows = len(rows)
    row_count_ok = 0           # 事件数一致行
    row_perfect = 0            # 事件内容+数量完全一致行
    tot_gold, tot_pred, tot_matched = 0, 0, 0
    tot_matched_a, tot_matched_fam = 0, 0
    tot_status_hit, tot_temporal_hit = 0, 0
    gold_a = Counter(); pred_a = Counter(); gold_fam = Counter(); pred_fam = Counter()

    # 高风险矩阵
    hr = defaultdict(int)
    mismatches = []

    for r in rows:
        g = triples(r)
        p_res = parse(r["raw_action"], r.get("raw_logic") or "")
        p = [(e["action"], e["action_status"], e["temporal_type"]) for e in p_res["events"]]
        sid = r["sample_id"]
        raw = r["raw_action"]

        Gc, Pc = Counter(g), Counter(p)
        matched = sum((Gc & Pc).values())
        Ga, Pa = Counter(e[0] for e in g), Counter(e[0] for e in p)
        matched_a = sum((Ga & Pa).values())
        Gf = Counter(FAMILY[e[0]] for e in g); Pf = Counter(FAMILY[e[0]] for e in p)
        matched_fam = sum((Gf & Pf).values())

        # status/temporal 按 action 对齐
        PbyA = defaultdict(list)
        for e in p:
            PbyA[e[0]].append(e)
        used = defaultdict(int)
        status_hit = temporal_hit = 0
        for (a, s, t) in g:
            cands = PbyA[a]
            i = used[a]
            if i < len(cands):
                ps, pt = cands[i][1], cands[i][2]
                used[a] += 1
                status_hit += (s == ps)
                temporal_hit += (t == pt)

        tot_gold += len(g); tot_pred += len(p); tot_matched += matched
        tot_matched_a += matched_a; tot_matched_fam += matched_fam
        tot_status_hit += status_hit; tot_temporal_hit += temporal_hit
        gold_a.update(Ga); pred_a.update(Pa); gold_fam.update(Gf); pred_fam.update(Pf)
        if len(p) == len(g):
            row_count_ok += 1
        if matched == len(g) == len(p):
            row_perfect += 1

        # ---- 高风险判定 ----
        # 持仓→今日BUY: pred 凭空制造的已执行买入（双轨 HOLD+买入族合法并存不算）
        g_exec_buys = {x[0] for x in g if x[0] in BUYFAM and x[1] == "EXECUTED"}
        p_exec_buys = {x[0] for x in p if x[0] in BUYFAM and x[1] == "EXECUTED"}
        for ab in p_exec_buys - g_exec_buys:
            hr["持仓→今日BUY"] += 1
        for (a, s, t) in g:
            # gold 目标值
            pred_same = [e for e in p if e[0] == a]
            if not pred_same:
                continue
            ps, pt = pred_same[0][1], pred_same[0][2]
            # 低风险→危险
            if s == "WATCH" and any(e[0] in BUYFAM for e in p):
                hr["WATCH→BUY族"] += 1
            if s == "INTENDED" and ps == "EXECUTED":
                hr["INTENDED→EXECUTED"] += 1
            if s == "CONDITIONAL" and ps == "EXECUTED":
                hr["CONDITIONAL→EXECUTED"] += 1
            if a == "BUY" and t == "PAST" and pt == "TODAY" and ps == "EXECUTED":
                hr["PAST BUY→TODAY BUY"] += 1
        # false executed buy/sell（pred 判 EXECUTED 而 gold 非该完成态）
        for (a, s, t) in p:
            if a in BUYFAM and s == "EXECUTED":
                ok = any(x == (a, "EXECUTED", t) for x in g) or any(
                    x[0] == a and x[1] == "EXECUTED" for x in g)
                if not ok:
                    hr["false executed buy"] += 1
            if a in SELLFAM and s == "EXECUTED":
                ok = any(x[0] == a and x[1] == "EXECUTED" for x in g)
                if not ok:
                    hr["false executed sell"] += 1
        # 推荐→BUY
        if "推荐" in raw or "核心标的" in raw or "看好" in raw:
            if any(e[0] in BUYFAM and e[1] == "EXECUTED" for e in p):
                hr["推荐→BUY(executed)"] += 1

        # 记录 mismatch（供迭代）
        if matched != len(g) or len(p) != len(g):
            mismatches.append((sid, raw[:50], g, p))

    # ---- 汇总指标 ----
    ep = tot_matched / tot_pred if tot_pred else 0
    er = tot_matched / tot_gold if tot_gold else 0
    ef1 = 2 * ep * er / (ep + er) if (ep + er) else 0
    aa = tot_matched_a / tot_gold if tot_gold else 0
    fam = tot_matched_fam / tot_gold if tot_gold else 0
    sa = tot_status_hit / tot_gold if tot_gold else 0
    ta = tot_temporal_hit / tot_gold if tot_gold else 0

    print()
    print("=" * 62)
    print("Parser v1.1 正式 Benchmark（盲测于冻结 Gold CORE events）")
    print("=" * 62)
    print(f"Event Precision {ep:.4f}  Recall {er:.4f}  F1 {ef1:.4f}")
    print(f"  Gold events {tot_gold} | Pred events {tot_pred} | matched {tot_matched}"
          f" | Missing {tot_gold-tot_matched} | Extra {tot_pred-tot_matched}")
    print(f"Action exact     {aa:.4f}  (≥0.95 目标)")
    print(f"Action family    {fam:.4f}")
    print(f"Status accuracy  {sa:.4f}  (≥0.97 目标)")
    print(f"Temporal accuracy{ta:.4f}  (≥0.95 目标)")
    print(f"Event-count 行一致率 {row_count_ok}/{n_rows} = {row_count_ok/n_rows:.4f}")
    print(f"事件内容完全一致行    {row_perfect}/{n_rows} = {row_perfect/n_rows:.4f}")
    print()
    print("高风险错误矩阵:")
    for k in ["false executed buy", "false executed sell", "持仓→今日BUY", "WATCH→BUY族",
              "INTENDED→EXECUTED", "CONDITIONAL→EXECUTED", "PAST BUY→TODAY BUY",
              "推荐→BUY(executed)"]:
        print(f"  {k:<22} {hr.get(k, 0)}")
    print()

    # 写 mismatch CSV
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sample_id", "raw", "gold_events", "pred_events"])
        for sid, raw, g, p in mismatches:
            w.writerow([sid, raw, g, p])
    print(f"mismatch 明细 → {OUT_CSV}（{len(mismatches)} 行）")
    print()
    # 动作族分布对比
    print("Action 分布 gold vs pred:")
    for a in sorted(set(list(gold_a) + list(pred_a)), key=lambda x: -gold_a[x]):
        print(f"  {a:<7} gold {gold_a[a]:>3}  pred {pred_a[a]:>3}")


if __name__ == "__main__":
    main()
