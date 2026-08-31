#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
benchmark_consensus_divergence_p42.py — P4.2 Gate 检查
================================================================
G1 覆盖 350 全 eligible
G2 divergence_score = 4 维均分（容差 0.001）
G3 consensus_strength 公式复算（same_rate × min(1, n/3)）
G4 analyst_divergence 复算（min(pos,neg)/max(pos,neg)，单边=0）
G5 theme_stock_divergence = |S−T|/2 复算
G6 view_action_divergence 复算（INTENDED vs EXECUTED 方向异号）
G7 holding_action_divergence 复算（has_holding 且最近3动作方向）
G8 幂等（重跑输出 hash 一致）
G9 excluded 3 治理事件隔离（events 层）

退出码：0=GO / 1=NO-GO
"""
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "analyst_consensus.db"
JSON_OUT = ROOT / "data" / "p42" / "consensus_divergence.json"
SCRIPT = ROOT / "scripts" / "consensus_divergence_p42.py"
P33 = ROOT / "data" / "p33" / "stock_consensus_score.json"
P41 = ROOT / "data" / "p41" / "stock_theme_linkage.json"
P30 = ROOT / "data" / "p30" / "stock_consensus_readiness.json"

ACTION_W = {"BUY": 1.0, "ADD": 0.8, "LOW_BUY": 0.7, "TRIAL": 0.4,
            "REDUCE": -0.5, "SELL": -0.8, "CLEAR": -1.0}

def sha1(p):
    return hashlib.sha1(Path(p).read_bytes()).hexdigest()

pre_hash = sha1(JSON_OUT) if JSON_OUT.exists() else None
r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=ROOT)
rerun_ok = (r.returncode == 0)
post_hash = sha1(JSON_OUT)
g8 = rerun_ok and pre_hash == post_hash

d = json.loads(JSON_OUT.read_text(encoding="utf-8"))
s = d["per_stock"]
p33 = json.loads(P33.read_text(encoding="utf-8"))["per_stock"]
p41 = json.loads(P41.read_text(encoding="utf-8"))["per_stock"]
p30 = json.loads(P30.read_text(encoding="utf-8"))

# G1：覆盖 == P3.3 覆盖（动态跨层，防滚动累积误判）
g1 = len(s) == len(p33)

# G2
g2 = all(abs(v["divergence_score"] - (v["analyst_divergence"] + v["theme_stock_divergence"] +
        v["view_action_divergence"] + v["holding_action_divergence"]) / 4.0) <= 0.001 for v in s.values())

# G3 / G4 / G5
g3 = g4 = g5 = True
for code, v in s.items():
    sv = p33[code]
    n_a, pos_a, neg_a = sv["n_analysts"], sv["pos_analysts"], sv["neg_analysts"]
    same_rate = max(pos_a, neg_a) / n_a if n_a >= 1 else 0.0
    exp_strength = round(same_rate * min(1.0, n_a / 3.0), 4)
    g3 = g3 and abs(exp_strength - v["consensus_strength"]) <= 1e-9
    exp_adiv = round(min(pos_a, neg_a) / max(pos_a, neg_a), 4) if (n_a >= 2 and max(pos_a, neg_a) > 0) else 0.0
    g4 = g4 and abs(exp_adiv - v["analyst_divergence"]) <= 1e-9
    S, T = p41[code]["S"], p41[code]["T"]
    exp_tsd = round(abs((S or 0) - (T or 0)) / 2.0, 4)
    g5 = g5 and abs(exp_tsd - v["theme_stock_divergence"]) <= 1e-9

# G6 / G7 独立重算
db = sqlite3.connect(DB); db.row_factory = sqlite3.Row
c = db.cursor()
ev_rows = [dict(r) for r in c.execute(
    "SELECT stock_code, action_type, action_status FROM analyst_stock_events WHERE event_id NOT IN (SELECT event_id FROM consensus_event_exclusions)")]
from collections import defaultdict, Counter
intended_net = defaultdict(float); executed_net = defaultdict(float)
for e in ev_rows:
    w = ACTION_W.get(e["action_type"], 0.0)
    if w == 0:
        continue
    if e["action_status"] == "INTENDED":
        intended_net[e["stock_code"]] += w
    elif e["action_status"] == "EXECUTED":
        executed_net[e["stock_code"]] += w

def sign(x):
    return 1 if x > 0.01 else (-1 if x < -0.01 else 0)

g6 = g7 = True
for code, v in s.items():
    iv, ev_ = sign(intended_net.get(code, 0.0)), sign(executed_net.get(code, 0.0))
    if iv == 0 and ev_ == 0:
        exp_vad = 0.0
    elif iv != 0 and ev_ != 0 and iv != ev_:
        exp_vad = 1.0
    elif iv == 0 or ev_ == 0:
        exp_vad = 0.5
    else:
        exp_vad = 0.0
    g6 = g6 and exp_vad == v["view_action_divergence"]

    has_hold = p33[code]["has_holding"]
    a_net = p41[code]["action_net_recent"]
    if has_hold:
        exp_had = 1.0 if (a_net is not None and a_net < -0.01) else (0.0 if (a_net is not None and a_net > 0.01) else 0.5)
    else:
        exp_had = 0.0
    g7 = g7 and exp_had == v["holding_action_divergence"]

# G9
n_excl = c.execute("SELECT COUNT(*) FROM consensus_event_exclusions").fetchone()[0]
g9 = n_excl == p30["events"]["excluded"]  # 动态：治理事件数 == P3.0 excluded

gates = {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "G6": g6, "G7": g7, "G8": g8, "G9": g9}
n_pass = sum(gates.values())
overall = "GO" if n_pass == len(gates) else "NO-GO"

lines = []
lines.append("# P4.2 Consensus / Divergence Benchmark")
lines.append("")
lines.append(f"Overall = **{overall}**（{n_pass}/{len(gates)} Gate）")
lines.append("")
lines.append("| Gate | 判定 | 说明 |")
lines.append("| --- | --- | --- |")
details = {
    "G1": f"覆盖 {len(s)}/{len(p33)}（== P3.3，动态跨层）",
    "G2": "divergence_score = 4 维均分（容差 0.001）",
    "G3": "consensus_strength 公式复算一致",
    "G4": "analyst_divergence 复算一致",
    "G5": "theme_stock_divergence = |S−T|/2 复算一致",
    "G6": "view_action_divergence（INTENDED vs EXECUTED）复算一致",
    "G7": "holding_action_divergence 复算一致",
    "G8": f"幂等：重跑前后 hash {'一致' if g8 else '不一致'}",
    "G9": f"excluded {n_excl} 条隔离",
}
for k, v in gates.items():
    lines.append(f"| {k} | {'✅' if v else '❌'} | {details[k]} |")
lines.append("")
lines.append(f"高分歧(≥0.5): {d['summary']['n_high_divergence(>=0.5)']}　多分析师同向: {d['summary']['n_analyst_same_direction(>=2,div=0)']}　分析师分裂: {d['summary']['n_analyst_split(div>=0.5)']}")
lines.append(f"主题个股反向: {d['summary']['n_theme_stock_mismatch']}　观点操作异号: {d['summary']['n_view_action_mismatch']}　持仓转负: {d['summary']['n_holding_turning_negative']}")
lines.append("")
lines.append(f"**P4.2 Overall = `{overall}`**")

report = ROOT / "reports" / "benchmark_consensus_divergence_p42.md"
report.write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
print("EXIT=", 0 if overall == "GO" else 1)
sys.exit(0 if overall == "GO" else 1)
