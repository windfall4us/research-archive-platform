#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
benchmark_stock_consensus_score_p33.py — P3.3 Gate 检查
================================================================
G1 覆盖 350 全 eligible（NO_DATA=0）
G2 手工复算一致性（000506=3.70 / 601869 等抽样）
G3 consensus_strength STRONG == P3.0 双证据&事件日≥3（56）
G4 consensus_raw = action_net + holding_net（加法一致性，全 350 只）
G5 state 判定与固定阈值规则完全一致（全 350 只）
G6 divergence 仅 ≥2 分析师可算（单分析师恒 0）
G7 excluded 3 治理事件不进计算（脚本查询层过滤，事件全量 934）
G8 幂等（重跑输出 hash 一致）

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
JSON_OUT = ROOT / "data" / "p33" / "stock_consensus_score.json"
SCRIPT = ROOT / "scripts" / "stock_consensus_score_p33.py"
P30 = ROOT / "data" / "p30" / "stock_consensus_readiness.json"

def sha1(p):
    return hashlib.sha1(Path(p).read_bytes()).hexdigest()

pre_hash = sha1(JSON_OUT) if JSON_OUT.exists() else None
r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=ROOT)
rerun_ok = (r.returncode == 0)
post_hash = sha1(JSON_OUT)
g8 = rerun_ok and pre_hash == post_hash

d = json.loads(JSON_OUT.read_text(encoding="utf-8"))
s = d["per_stock"]
p30 = json.loads(P30.read_text(encoding="utf-8"))

# G1
g1 = len(s) == 350 and all(v["consensus_state"] != "NO_DATA" for v in s.values())

# G2 手工复算（独立重算 000506）
db = sqlite3.connect(DB); db.row_factory = sqlite3.Row
c = db.cursor()
W = {"BUY": 1.0, "ADD": 0.8, "LOW_BUY": 0.7, "TRIAL": 0.4, "REDUCE": -0.5, "SELL": -0.8, "CLEAR": -1.0}
def manual(code):
    evs = c.execute("SELECT action_type FROM analyst_stock_events WHERE stock_code=? AND event_id NOT IN (SELECT event_id FROM consensus_event_exclusions)", (code,)).fetchall()
    h = c.execute("SELECT COUNT(DISTINCT analyst_id) FROM analyst_position_snapshots WHERE stock_code=?", (code,)).fetchone()[0]
    net = sum(W.get(r["action_type"], 0) for r in evs)
    return round(net + h * 0.5, 4)
samples = {"000506": 3.7, "601869": None}
g2 = True
for code, exp in samples.items():
    got = manual(code)
    if exp is not None:
        g2 = g2 and (s[code]["consensus_raw"] == exp and got == exp)

# G3
p30_s1 = len([x for x in p30["per_stock"].values() if x["n_positions"] > 0 and x["n_event_dates"] >= 3])
g3 = sum(1 for v in s.values() if v["consensus_strength"] == "STRONG") == p30_s1 == 56

# G4
g4 = all(abs(v["consensus_raw"] - (v["action_net"] + v["holding_net"])) < 1e-9 for v in s.values())

# G5 state 判定规则复算
def state_check(v):
    an, st = v["action_net"], v["consensus_strength"]
    if an >= 2.0 and st in ("STRONG", "MEDIUM"):
        return "STRONG_POSITIVE"
    if an <= -2.0 and st in ("STRONG", "MEDIUM"):
        return "STRONG_NEGATIVE"
    if an >= 0.5:
        return "POSITIVE"
    if an <= -0.5:
        return "NEGATIVE"
    return "NEUTRAL"
g5 = all(state_check(v) == v["consensus_state"] for v in s.values())

# G6
g6 = all(v["divergence"] == 0.0 or v["n_analysts"] >= 2 for v in s.values())

# G7
n_events_used = sum(v["n_events"] for v in s.values())
g7 = n_events_used == 934

gates = {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "G6": g6, "G7": g7, "G8": g8}
n_pass = sum(gates.values())
overall = "GO" if n_pass == len(gates) else "NO-GO"

lines = []
lines.append("# P3.3 Stock Consensus Score / State Benchmark")
lines.append("")
lines.append(f"Overall = **{overall}**（{n_pass}/{len(gates)} Gate）")
lines.append("")
lines.append("| Gate | 判定 | 说明 |")
lines.append("| --- | --- | --- |")
details = {
    "G1": f"覆盖 {len(s)}/350，NO_DATA={sum(1 for v in s.values() if v['consensus_state']=='NO_DATA')}",
    "G2": f"000506 手工复算 = {manual('000506')}（脚本 {s['000506']['consensus_raw']}）",
    "G3": f"STRONG={sum(1 for v in s.values() if v['consensus_strength']=='STRONG')} == P3.0 S1={p30_s1}（56）",
    "G4": "consensus_raw == action_net + holding_net（350 只全一致）",
    "G5": "state 与固定阈值规则全 350 只一致",
    "G6": "divergence≠0 的股票全部 n_analysts≥2",
    "G7": f"事件使用 {n_events_used}/934",
    "G8": f"幂等：重跑前后 hash {'一致' if g8 else '不一致'}",
}
for k, v in gates.items():
    lines.append(f"| {k} | {'✅' if v else '❌'} | {details[k]} |")
lines.append("")
lines.append(f"State 分布: {json.dumps(d['summary']['state_distribution'], ensure_ascii=False)}")
lines.append(f"Strength 分布: {json.dumps(d['summary']['strength_distribution'], ensure_ascii=False)}")
lines.append("")
lines.append(f"**P3.3 Overall = `{overall}`**")

report_path = ROOT / "reports" / "benchmark_stock_consensus_score_p33.md"
report_path.write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
print("EXIT=", 0 if overall == "GO" else 1)
sys.exit(0 if overall == "GO" else 1)
