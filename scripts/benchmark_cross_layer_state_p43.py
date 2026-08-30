#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
benchmark_cross_layer_state_p43.py — P4.3 Gate 检查
================================================================
G1 覆盖 350 全 eligible
G2 状态判定规则复算一致（全 350 只，独立实现）
G3 UNMAPPED = 13（与 P4.1 一致）
G4 CONFIRMED ⊆ 三维共振（linkage∈{CONFIRMED_BULLISH,CONFIRMED_BEARISH} 且 div<0.5）
G5 DIVERGING ⊆ S·T<0（个股主题反向）
G6 REVERSING ⊆ (持仓转负 或 观点异号) 且 dir 为正
G7 WEAKENING ⊆ theme_down 且 S∈{0,+1}
G8 DISCOVERY ⊆ theme_up 且 S∈{0,−1}
G9 幂等（重跑输出 hash 一致）
G10 excluded 3 治理事件隔离（上游 P4.1/P4.2 已保证，复查）

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
JSON_OUT = ROOT / "data" / "p43" / "cross_layer_state.json"
SCRIPT = ROOT / "scripts" / "cross_layer_state_p43.py"
P41 = ROOT / "data" / "p41" / "stock_theme_linkage.json"
P42 = ROOT / "data" / "p42" / "consensus_divergence.json"

def sha1(p):
    return hashlib.sha1(Path(p).read_bytes()).hexdigest()

pre_hash = sha1(JSON_OUT) if JSON_OUT.exists() else None
r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=ROOT)
rerun_ok = (r.returncode == 0)
post_hash = sha1(JSON_OUT)
g9 = rerun_ok and pre_hash == post_hash

d = json.loads(JSON_OUT.read_text(encoding="utf-8"))
s = d["per_stock"]
p41 = json.loads(P41.read_text(encoding="utf-8"))["per_stock"]
p42 = json.loads(P42.read_text(encoding="utf-8"))["per_stock"]

g1 = len(s) == 350
g3 = sum(1 for v in s.values() if v["cross_layer_state"] == "UNMAPPED") == 13

# G4-G8 子集约束
g4 = all(v["linkage_signal"] in ("CONFIRMED_BULLISH", "CONFIRMED_BEARISH") and v["divergence_score"] < 0.5
         for v in s.values() if v["cross_layer_state"] == "CONFIRMED")
g5 = all(v["S"] != 0 and v["T"] != 0 and v["S"] * v["T"] < 0
         for v in s.values() if v["cross_layer_state"] == "DIVERGING")
g6 = all(v["S"] == 1 and (v["holding_action_divergence"] == 1.0 or v["view_action_divergence"] == 1.0)
         for v in s.values() if v["cross_layer_state"] == "REVERSING")
g7 = all(v["T"] == -1 and v["S"] in (0, 1)
         for v in s.values() if v["cross_layer_state"] == "WEAKENING")
g8 = all(v["T"] == 1 and v["S"] in (0, -1)
         for v in s.values() if v["cross_layer_state"] == "DISCOVERY")

# G2 独立复算状态判定
def decide(code, v):
    if not v["mapped"]:
        return "UNMAPPED"
    S, T = v["S"], v["T"]
    dir_pos = S == 1
    theme_up = T == 1
    theme_down = T == -1
    holding_neg = p42[code]["holding_action_divergence"] == 1.0
    view_mismatch = p42[code]["view_action_divergence"] == 1.0
    div = p42[code]["divergence_score"]
    linkage = v["linkage_signal"]
    if dir_pos and (holding_neg or view_mismatch) and not theme_up:
        return "REVERSING"
    if dir_pos and theme_up and div < 0.5 and linkage == "CONFIRMED_BULLISH":
        return "CONFIRMED"
    if S == -1 and theme_down and div < 0.5 and linkage == "CONFIRMED_BEARISH":
        return "CONFIRMED"
    if dir_pos and theme_up and (div >= 0.5 or linkage == "THEME_CONFIRMED_STOCK"):
        return "CONFIRMING"
    if S == -1 and theme_down and (div >= 0.5 or linkage == "THEME_CONFIRMED_STOCK"):
        return "CONFIRMING"
    if S != 0 and T != 0 and S * T < 0:
        return "DIVERGING"
    if theme_down and (dir_pos or S == 0):
        return "WEAKENING"
    if theme_up and (S == -1 or S == 0):
        return "DISCOVERY"
    return "NEUTRAL"
g2 = all(decide(code, p41[code]) == v["cross_layer_state"] for code, v in s.items())

# G10
db = sqlite3.connect(DB); db.row_factory = sqlite3.Row
c = db.cursor()
n_excl = c.execute("SELECT COUNT(*) FROM consensus_event_exclusions").fetchone()[0]
g10 = n_excl == 3

gates = {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "G6": g6, "G7": g7, "G8": g8, "G9": g9, "G10": g10}
n_pass = sum(gates.values())
overall = "GO" if n_pass == len(gates) else "NO-GO"

lines = []
lines.append("# P4.3 Cross-Layer State Benchmark")
lines.append("")
lines.append(f"Overall = **{overall}**（{n_pass}/{len(gates)} Gate）")
lines.append("")
lines.append("| Gate | 判定 | 说明 |")
lines.append("| --- | --- | --- |")
details = {
    "G1": f"覆盖 {len(s)}/350",
    "G2": "状态判定独立复算一致（全 350 只）",
    "G3": f"UNMAPPED={sum(1 for v in s.values() if v['cross_layer_state']=='UNMAPPED')}/13",
    "G4": f"CONFIRMED {sum(1 for v in s.values() if v['cross_layer_state']=='CONFIRMED')} 全为三维共振低分歧",
    "G5": f"DIVERGING {sum(1 for v in s.values() if v['cross_layer_state']=='DIVERGING')} 全为 S·T<0",
    "G6": f"REVERSING {sum(1 for v in s.values() if v['cross_layer_state']=='REVERSING')} 全为持仓转负/观点异号",
    "G7": f"WEAKENING {sum(1 for v in s.values() if v['cross_layer_state']=='WEAKENING')} 全为 theme_down",
    "G8": f"DISCOVERY {sum(1 for v in s.values() if v['cross_layer_state']=='DISCOVERY')} 全为 theme_up",
    "G9": f"幂等：重跑前后 hash {'一致' if g9 else '不一致'}",
    "G10": f"excluded {n_excl} 条隔离",
}
for k, v in gates.items():
    lines.append(f"| {k} | {'✅' if v else '❌'} | {details[k]} |")
lines.append("")
lines.append(f"状态分布: {json.dumps(d['summary']['state_distribution'], ensure_ascii=False)}")
lines.append("")
lines.append(f"**P4.3 Overall = `{overall}`**")

report = ROOT / "reports" / "benchmark_cross_layer_state_p43.md"
report.write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
print("EXIT=", 0 if overall == "GO" else 1)
sys.exit(0 if overall == "GO" else 1)
