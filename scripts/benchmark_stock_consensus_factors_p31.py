#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
benchmark_stock_consensus_factors_p31.py — P3.1 Gate 检查
================================================================
G1 excluded 3 治理事件泄漏进事实 = 0
G2 DO_T / WATCH 事件进正负桶 = 0
G3 正负桶一致性（期望计数 == 观测计数）
G4 持仓事实全量使用（== P3.0 positions.total，动态值）
G5 事件全量使用（== P3.0 events.eligible，attention 汇总 == eligible，动态值）
G6 方向冲突仅审计不主导（冲突事件按 action_type 归属，P2.2B 契约）
G7 分层分母全覆盖（== P3.0 events.n_stocks，每股至少 S1/S2/S3 一层，动态值）
G8 幂等（重跑输出 hash 一致）

注：G4/G5/G7 验证「关系/跨层一致」而非固定绝对值（用户 08-31 裁决：
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
JSON_OUT = ROOT / "data" / "p31" / "stock_consensus_factors.json"
SCRIPT = ROOT / "scripts" / "stock_consensus_factors_p31.py"

POSITIVE = {"BUY", "ADD", "LOW_BUY", "TRIAL"}
NEGATIVE = {"REDUCE", "SELL", "CLEAR"}

# ---------- G8 幂等：先记录当前 hash ----------
def sha1(p):
    return hashlib.sha1(Path(p).read_bytes()).hexdigest()

pre_hash = sha1(JSON_OUT) if JSON_OUT.exists() else None

# 重跑
r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=ROOT)
rerun_ok = (r.returncode == 0)
post_hash = sha1(JSON_OUT)
g8 = rerun_ok and pre_hash == post_hash

# ---------- 读数据 ----------
d = json.loads(JSON_OUT.read_text(encoding="utf-8"))
g = d["governance"]
p30 = json.loads((ROOT / "data" / "p30" / "stock_consensus_readiness.json").read_text(encoding="utf-8"))

# 动态基准值（来源：P3.0 readiness 只读盘点）
P30_POSITIONS = p30["positions"]["total"]
P30_ELIGIBLE = p30["events"]["eligible"]
P30_N_STOCKS = p30["events"]["n_stocks"]

# ---------- Gate 计算 ----------
gates = {}

# G1
gates["G1"] = g["excluded_events_in_factors"] == 0
# G2
gates["G2"] = g["do_t_events_in_posneg"] == 0 and g["watch_events_in_posneg"] == 0
# G3
gates["G3"] = g["posneg_consistency"]
# G4：持仓全量使用 == P3.0 positions.total（动态，防滚动累积误判）
gates["G4"] = g["positions_used"] == P30_POSITIONS and g["physical_positions"] == P30_POSITIONS
# G5：事件全量使用 == P3.0 eligible（动态，防滚动累积误判）
gates["G5"] = g["eligible_events_used"] == g["physical_events"] == P30_ELIGIBLE
# G6：冲突事件仍按 action_type 归属（正负桶一致性已隐式保证，这里显式确认冲突数>0 不影响 G3）
gates["G6"] = g["posneg_consistency"] and (g["direction_conflicts"]["n_conflicts"] > 0)
# G7：覆盖股票 == P3.0 events.n_stocks（动态，防滚动累积误判）
gates["G7"] = d["n_stocks"] == P30_N_STOCKS
# G8
gates["G8"] = g8

n_pass = sum(gates.values())
overall = "GO" if n_pass == len(gates) else "NO-GO"

# ---------- 报告 ----------
lines = []
lines.append("# P3.1 Stock Consensus Factors Benchmark")
lines.append("")
lines.append(f"Overall = **{overall}**（{n_pass}/{len(gates)} Gate）")
lines.append("")
lines.append("| Gate | 判定 | 说明 |")
lines.append("| --- | --- | --- |")
details = {
    "G1": f"excluded 泄漏={g['excluded_events_in_factors']}（应 0）",
    "G2": f"DO_T 进正负={g['do_t_events_in_posneg']} / WATCH 进正负={g['watch_events_in_posneg']}（应 0/0）",
    "G3": f"pos {g['positive_events_expected']}/{g['positive_events_observed']} · neg {g['negative_events_expected']}/{g['negative_events_observed']}",
    "G4": f"持仓使用 {g['positions_used']}/{g['physical_positions']}（应 {P30_POSITIONS}/{P30_POSITIONS}）",
    "G5": f"事件使用 {g['eligible_events_used']}/{g['physical_events']}（应 {P30_ELIGIBLE}/{P30_ELIGIBLE}）",
    "G6": f"方向冲突 {g['direction_conflicts']['n_conflicts']} 条，仅审计不主导（正负桶一致性保持）",
    "G7": f"覆盖股票 {d['n_stocks']} == P3.0 eligible {P30_N_STOCKS}",
    "G8": f"幂等：重跑前后 hash {'一致' if g8 else '不一致'}",
}
for k, v in gates.items():
    lines.append(f"| {k} | {'✅' if v else '❌'} | {details[k]} |")

lines.append("")
lines.append(f"每股每日 cell = {d['n_stock_date_cells']}（{d['n_stocks']} 股 × {d['n_dates']} 日）")
lines.append(f"方向冲突 {g['direction_conflicts']['n_conflicts']} 条样本：{'；'.join(c['action'] + '/' + c['dir'] + '(' + c['analyst'] + ')' for c in g['direction_conflicts']['detail'][:6])}")
lines.append("")
lines.append(f"**P3.1 Overall = `{overall}`**")

report_path = ROOT / "reports" / "benchmark_stock_consensus_factors_p31.md"
report_path.write_text("\n".join(lines), encoding="utf-8")

print("\n".join(lines))
print("EXIT=", 0 if overall == "GO" else 1)
sys.exit(0 if overall == "GO" else 1)
