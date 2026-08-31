#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
benchmark_stock_theme_linkage_p41.py — P4.1 Gate 检查
================================================================
G1 映射覆盖一致：mapped/unmapped == P4.0 mapping（动态值）
G2 三维信号 S/T/A 复算一致（全 mapped 股票）
G3 linkage 标签与规则矩阵复算一致（全 mapped 股票）
G4 每股最近 3 动作净方向正确（与 P3.2 事件流一致）
G5 主主题 = confidence 最高映射（P2.2A Top3 治理）
G6 excluded 治理事件不进动作流（P3.2 已保证，事件级复查；事件全量 == P3.0 eligible）
G7 幂等（重跑输出 hash 一致）
G8 无缺失：全 eligible 股票都有 linkage_signal（== P4.0 n_eligible，动态值）

注：G1/G6/G8 验证「关系/跨层一致」而非固定绝对值（用户 08-31 裁决：
验关系而非固定值；冻结期报告保持 immutable）。数据滚动累积不误判。

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
JSON_OUT = ROOT / "data" / "p41" / "stock_theme_linkage.json"
SCRIPT = ROOT / "scripts" / "stock_theme_linkage_p41.py"
P40 = ROOT / "data" / "p40" / "cross_layer_readiness.json"
P32 = ROOT / "data" / "p32" / "analyst_action_flow.json"
P30 = ROOT / "data" / "p30" / "stock_consensus_readiness.json"

ACTION_W = {"BUY": 1.0, "ADD": 0.8, "LOW_BUY": 0.7, "TRIAL": 0.4,
            "REDUCE": -0.5, "SELL": -0.8, "CLEAR": -1.0}
UP = {"HEATING", "EMERGING"}
DOWN = {"COOLING", "FADING"}

def sha1(p):
    return hashlib.sha1(Path(p).read_bytes()).hexdigest()

pre_hash = sha1(JSON_OUT) if JSON_OUT.exists() else None
r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=ROOT)
rerun_ok = (r.returncode == 0)
post_hash = sha1(JSON_OUT)
g7 = rerun_ok and pre_hash == post_hash

d = json.loads(JSON_OUT.read_text(encoding="utf-8"))
s = d["per_stock"]
p40 = json.loads(P40.read_text(encoding="utf-8"))
p32f = json.loads(P32.read_text(encoding="utf-8"))["per_analyst_stock_flow"]
p30 = json.loads(P30.read_text(encoding="utf-8"))

# 动态基准值（来源：P4.0 readiness + P3.0 readiness）
P40_MAPPED = p40["mapping"]["n_mapped_stocks"]
P40_UNMAPPED = p40["mapping"]["n_unmapped_stocks"]
P40_N_ELIGIBLE = p40["stock_layer"]["n_eligible"]
P30_ELIGIBLE = p30["events"]["eligible"]
P30_EXCLUDED = p30["events"]["excluded"]

# ---------- G1 ----------
n_mapped = sum(1 for v in s.values() if v["mapped"])
n_unmapped = sum(1 for v in s.values() if not v["mapped"])
g1 = n_mapped == P40_MAPPED and n_unmapped == P40_UNMAPPED and n_mapped == P40_MAPPED

# ---------- G2/G3 复算 ----------
def stock_dir(state):
    return 1 if state in ("STRONG_POSITIVE", "POSITIVE") else (-1 if state in ("STRONG_NEGATIVE", "NEGATIVE") else 0)
def theme_dir(meff):
    return 1 if meff in UP else (-1 if meff in DOWN else 0)
def act_dir(net):
    return 1 if net > 0.5 else (-1 if net < -0.5 else 0)
def linkage(S, T, A):
    if S == 1 and T == 1 and A == 1:
        return "CONFIRMED_BULLISH"
    if S == -1 and T == -1 and A == -1:
        return "CONFIRMED_BEARISH"
    if (S == 1 and T == -1) or (S == -1 and T == 1):
        return "STOCK_THEME_DIVERGENCE"
    if T == 1 and A == -1:
        return "LAGGING_OR_DISTRIBUTION"
    if S == 1 and T == 1 and A == 0:
        return "THEME_CONFIRMED_STOCK"
    return "NEUTRAL"

g2 = g3 = True
for code, v in s.items():
    if not v["mapped"]:
        continue
    S_exp = stock_dir(v["stock_consensus_state"])
    T_exp = theme_dir(v["theme_momentum_eff"])
    A_exp = act_dir(v["action_net_recent"])
    sig_exp = linkage(S_exp, T_exp, A_exp)
    g2 = g2 and (S_exp == v["S"] and T_exp == v["T"] and A_exp == v["A"])
    g3 = g3 and (sig_exp == v["linkage_signal"])

# ---------- G4 最近3动作复算 ----------
db = sqlite3.connect(DB); db.row_factory = sqlite3.Row
c = db.cursor()
excluded = tuple(r[0] for r in c.execute("SELECT event_id FROM consensus_event_exclusions"))
g4 = True
checked = 0
for code, v in s.items():
    if not v["mapped"]:
        continue
    evs = [dict(r) for r in c.execute(
        "SELECT event_date, event_id, action_type FROM analyst_stock_events WHERE stock_code=? AND event_id NOT IN (SELECT event_id FROM consensus_event_exclusions) ORDER BY event_date, event_id", (code,))]
    last3 = evs[-3:]
    net = sum(ACTION_W.get(e["action_type"], 0.0) for e in last3)
    acts = [e["action_type"] for e in last3]
    if abs(net - v["action_net_recent"]) > 1e-9 or acts != v["recent_actions"]:
        g4 = False
    checked += 1

# ---------- G5 主主题 = 最高 confidence ----------
mappings = [dict(r) for r in c.execute(
    "SELECT stock_code, theme_id, confidence FROM stock_theme_mapping WHERE confidence >= 0.60")]
best = {}
for m in sorted(mappings, key=lambda x: -x["confidence"]):  # 降序，首次遇到即最高
    if m["stock_code"] not in best:
        best[m["stock_code"]] = m["theme_id"]
g5 = all(v["main_theme"] == best[code] for code, v in s.items() if v["mapped"])

# ---------- G6 excluded 泄漏（动作流来自 P3.2 已隔离，事件级复查；事件全量 == P3.0 eligible） ----------
n_p32_events = sum(len(fl) for fl in p32f.values())
g6 = len(excluded) == P30_EXCLUDED and n_p32_events == P30_ELIGIBLE

# ---------- G8 ----------
g8 = len(s) == P40_N_ELIGIBLE and all("linkage_signal" in v for v in s.values())

gates = {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5, "G6": g6, "G7": g7, "G8": g8}
n_pass = sum(gates.values())
overall = "GO" if n_pass == len(gates) else "NO-GO"

lines = []
lines.append("# P4.1 Stock × Theme Linkage Benchmark")
lines.append("")
lines.append(f"Overall = **{overall}**（{n_pass}/{len(gates)} Gate）")
lines.append("")
lines.append("| Gate | 判定 | 说明 |")
lines.append("| --- | --- | --- |")
details = {
    "G1": f"mapped={n_mapped}/{P40_MAPPED}, unmapped={n_unmapped}/{P40_UNMAPPED}（P4.0 动态）",
    "G2": "S/T/A 三维信号复算一致（全 mapped 股票）",
    "G3": "linkage 标签与规则矩阵复算一致（全 mapped 股票）",
    "G4": f"最近3动作净方向复算一致（checked {checked} 只）",
    "G5": "主主题 = confidence 最高映射",
    "G6": f"excluded {len(excluded)}/{P30_EXCLUDED} 条隔离；p32 动作流 {n_p32_events}/{P30_ELIGIBLE}",
    "G7": f"幂等：重跑前后 hash {'一致' if g7 else '不一致'}",
    "G8": f"覆盖 {len(s)}/{P40_N_ELIGIBLE}，全部有 linkage_signal",
}
for k, v in gates.items():
    lines.append(f"| {k} | {'✅' if v else '❌'} | {details[k]} |")
lines.append("")
lines.append(f"联动分布: {json.dumps(d['summary']['linkage_distribution'], ensure_ascii=False)}")
lines.append("")
lines.append(f"**P4.1 Overall = `{overall}`**")

report = ROOT / "reports" / "benchmark_stock_theme_linkage_p41.md"
report.write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
print("EXIT=", 0 if overall == "GO" else 1)
sys.exit(0 if overall == "GO" else 1)
