#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
theme_momentum_p23.py — P2.3 Theme Momentum v1
================================================
目标：回答「这个主题是刚出现、正在升温、维持主线，还是开始退潮？」
输入只读 P2.2C 冻结的每日 Theme Heat + signal_confidence + heat_status + 四因子贡献。
不重新解析原文，不重新映射股票。

状态 6 类（用户锁定 v1）：
  DISCOVERY / EMERGING / HEATING / STABLE / COOLING / FADING
  暂不做 MAINLINE/CROWDED（8 个交易日样本太短，等 15~20 日后再加持续性条件）

三个量（用户 2026-08-30 裁决版）：
  heat_score（当日）
  Δ1 = 今日 - 上一个 VALID heat（跳过 LOW_SIGNAL —— LOW_SIGNAL 不作为 Δ1 锚点，
       只允许进入 Δ3 加权基线，weight=0.5）
       同时输出 delta1_reference_date / delta1_reference_status 供解释
  Δ3 = 今日 - 近3日加权基线（最近 3 个 VALID/LOW_SIGNAL 可用交易日，VALID=1.0 / LOW_SIGNAL=0.5 加权平均）

状态规则（用户锁定 v1 + 2026-08-30 裁决）：
  DISCOVERY：heat>=15 且 conf>=MEDIUM 且（最近至少2个有效观测日 heat<10 或 此前无有效信号）
             —— 数据首日不能算「此前没有信号」（BASELINE_ONLY 独立处理，不误报 discovery）
  EMERGING ：heat>=15 且 Δ1>=+5 且 近3日总体向上（Δ3>0）
  HEATING  ：heat>=25 且 (Δ1>=+5 或 Δ3>=+10) 且 conf>=MEDIUM
  STABLE   ：heat>=20 且 |Δ1|<5 且 |Δ3|<10
  COOLING  ：heat>=10 且 (Δ1<=-5 或 Δ3<=-10)
  FADING   ：heat<10 且（历史 max>=25（曾达 HEATING 级）或 连续2个 VALID 日严格下降且曾有过信号）

双状态轨：
  observed_momentum_state  —— 纯数据趋势观测（不做 confidence gate，让数据趋势先说话）
  effective_momentum_state —— 正式生效状态（confidence gate + hysteresis 防抖 + transition graph）
  原则：变化必须有历史上下文；LOW_SIGNAL 只降置信，不造成状态机乱跳。

BASELINE（用户 2026-08-30 裁决）：
  数据首日不标 DISCOVERY → momentum_status=BASELINE_ONLY / effective_state=NULL
  第二个有效观测日起进入正式状态机。
  BASELINE_ONLY 是状态机启动状态（技术状态），不属于 6 个市场状态。

hysteresis（用户锁定 v1）：
  升级：满足阈值 1 天即可生效
  降级：需连续 2 个有效交易日确认
  严重恶化（Δ1<=-15 或 NEGATIVE mention + negative trade 同时出现）允许当日直接 COOLING

transition graph（用户锁定 v1 + 补充规则2）：
  主线链：DISCOVERY → EMERGING → HEATING → STABLE → COOLING → FADING
  允许：EMERGING→FADING / HEATING→COOLING / STABLE→HEATING / COOLING→HEATING / FADING→DISCOVERY(重新进入)
  禁止：DISCOVERY→FADING / FADING→HEATING（除非经 DISCOVERY 重新进入）
  FADING→DISCOVERY 需冷却窗口：至少 1 个有效日 heat<10 后再突破 15
  （由 DISCOVERY 历史条件「最近2日 heat<10」天然保证）

用法：python3 scripts/theme_momentum_p23.py
"""

import json
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEAT_JSON = ROOT / "data" / "p22c" / "theme_heat_scores.json"
OUT_JSON = ROOT / "data" / "p23" / "theme_momentum.json"

# ---------------- 用户锁定的规则参数 ----------------
DISCOVERY_HEAT_MIN = 15.0
EMERGING_HEAT_MIN = 15.0
EMERGING_DELTA1 = 5.0
HEATING_HEAT_MIN = 25.0
HEATING_DELTA1 = 5.0
HEATING_DELTA3 = 10.0
STABLE_HEAT_MIN = 20.0
STABLE_DELTA1_ABS = 5.0
STABLE_DELTA3_ABS = 10.0
COOLING_HEAT_MIN = 10.0
COOLING_DELTA1 = -5.0
COOLING_DELTA3 = -10.0
FADING_HEAT_MAX = 10.0
FADING_PREV_ACTIVE_HEAT = 25.0     # 曾达 HEATING 级（heat>=25）即可作为退潮锚点（用户裁决：45→25）
SEVERE_DROP_DELTA1 = -15.0         # 严重恶化：Δ1<=-15 立即降级
VALID_WEIGHT = 1.0
LOW_SIGNAL_WEIGHT = 0.5            # LOW_SIGNAL 只降置信、只进 Δ3，不能和 VALID 等权、不作 Δ1 锚点
DELTA3_WINDOW = 3                  # 近 3 日基线

# 状态枚举（强度从低到高；用于 upgrade/downgrade 判定）
STATE_ORDER = ["DISCOVERY", "EMERGING", "HEATING", "STABLE", "COOLING", "FADING"]

# 合法 transition graph（用户锁定 v1）
ALLOWED_TRANSITIONS = {
    "DISCOVERY": {"EMERGING"},
    "EMERGING": {"HEATING", "FADING"},       # EMERGING→FADING 用户显式允许
    "HEATING": {"STABLE", "COOLING"},        # HEATING→COOLING 用户显式允许
    "STABLE": {"HEATING", "COOLING"},        # STABLE→HEATING 用户显式允许
    "COOLING": {"HEATING", "FADING"},        # COOLING→HEATING 用户显式允许
    "FADING": {"DISCOVERY"},                 # 只能经 DISCOVERY 重新进入（冷却窗口后）
}
# 自持（状态不变）总是允许
for _s in STATE_ORDER:
    ALLOWED_TRANSITIONS.setdefault(_s, set()).add(_s)

# 升级类状态（需要 confidence 支撑；LOW_SIGNAL 日升级挂起）
UPGRADE_STATES = {"DISCOVERY", "EMERGING", "HEATING"}

# 退潮态（降级目标）：COOLING / FADING —— 需要 2 个有效交易日确认（用户锁定）
RETREAT_STATES = {"COOLING", "FADING"}

# 严重恶化信号：Δ1 暴跌 或 当日同时出现 NEGATIVE mention + negative trade
SEVERE_DROP_DELTA1_TH = -15.0


def is_available(r):
    """有效交易日 = VALID 或 LOW_SIGNAL；INSUFFICIENT_DATA 跳过。"""
    return r["heat_status"] in ("VALID", "LOW_SIGNAL") and r["heat_score"] is not None


def day_weight(r):
    return VALID_WEIGHT if r["heat_status"] == "VALID" else LOW_SIGNAL_WEIGHT


def compute_observed(heat, d1, d3, hist_max_heat, consecutive_valid_decline, prior_available):
    """
    observed = 纯数值规则（不做 confidence gate，让数据趋势先说话，gates 在 effective 层）。
    prior_available: 今日之前所有有效交易日（不含今日）的 row 列表，按日期升序
    hist_max_heat: 历史 max heat（含今日之前所有有效观测）
    consecutive_valid_decline: 连续几个 VALID 交易日 heat 严格递减
    """
    # DISCOVERY：首次达到阈值 + 有足够历史（此前冷 / 此前无信号）—— 首日由 BASELINE_ONLY 处理，不算 discovery
    if heat >= DISCOVERY_HEAT_MIN and len(prior_available) >= 2:
        last2 = [r["heat_score"] for r in prior_available[-2:]]
        recently_cold = all(h < FADING_HEAT_MAX for h in last2)   # 最近至少2个有效观测日 heat<10
        no_prior_signal = hist_max_heat == 0                      # 此前从未有有效主题信号
        if recently_cold or no_prior_signal:
            return "DISCOVERY"
    # FADING：heat<10 且（曾达 HEATING 级>=25 或 连续2个 VALID 日严格下降且曾有过信号）
    if heat < FADING_HEAT_MAX and (hist_max_heat >= FADING_PREV_ACTIVE_HEAT
                                   or (consecutive_valid_decline >= 2 and hist_max_heat > 0)):
        return "FADING"
    if heat >= COOLING_HEAT_MIN and (
            (d1 is not None and d1 <= COOLING_DELTA1)
            or (d3 is not None and d3 <= COOLING_DELTA3)):
        return "COOLING"
    if heat >= STABLE_HEAT_MIN and (
            d1 is not None and abs(d1) < STABLE_DELTA1_ABS
            and d3 is not None and abs(d3) < STABLE_DELTA3_ABS):
        return "STABLE"
    if heat >= HEATING_HEAT_MIN and (
            (d1 is not None and d1 >= HEATING_DELTA1)
            or (d3 is not None and d3 >= HEATING_DELTA3)):
        return "HEATING"
    if heat >= EMERGING_HEAT_MIN and (d1 is not None and d1 >= EMERGING_DELTA1) and (d3 is not None and d3 > 0):
        return "EMERGING"
    # 回退：有历史但没命中任何明确规则 → COLD_UNCLASSIFIED（交由 effective 层保持上一状态）
    # 不硬套 STABLE/COOLING：避免「从低位上涨未达阈值」被误标成退潮
    return "COLD_UNCLASSIFIED"


def decide_effective(prev_eff, observed, conf_ok, severe, pending_downgrade):
    """
    纯函数：effective 状态决策（confidence gate + hysteresis + transition graph）。
    返回 (effective, pending_downgrade, note)。
    prev_eff: 上一 effective 状态（None = 从未进入状态机）
    observed: 当日观测状态
    conf_ok: 当日 signal_confidence 是否 HIGH/MEDIUM
    severe: 是否严重恶化（Δ1<=-15 或 NEG mention + negative trade 同日）
    pending_downgrade: 降级防抖计数（0/1/2）
    """
    if prev_eff is None or prev_eff == "NONE":
        # 从未进入状态机
        if observed in ("NONE", "COLD_UNCLASSIFIED", "UNCLASSIFIED_BASELINE"):
            return None, 0, "NO_STATE"
        if not conf_ok:
            # LOW_SIGNAL 首日不初始化升级态
            return None, 0, "ENTRY_BLOCKED_LOW_CONFIDENCE"
        return observed, 0, "STATE_MACHINE_ENTRY"
    if observed in ("NONE", "COLD_UNCLASSIFIED", "UNCLASSIFIED_BASELINE"):
        # 当日无有效观测 → 保持上一 effective
        return prev_eff, 0, "SELF_HOLD_NO_OBSERVED"
    if severe:
        # 严重恶化：跳过防抖立即降级到 COOLING（若从 prev 合法可达）
        if "COOLING" in ALLOWED_TRANSITIONS.get(prev_eff, set()):
            return "COOLING", 0, "SEVERE_DROP_IMMEDIATE"
        return prev_eff, 0, "SEVERE_DROP_BLOCKED_TRANSITION"
    if observed == prev_eff:
        return prev_eff, 0, "SELF_HOLD"
    if observed in ALLOWED_TRANSITIONS.get(prev_eff, set()):
        # 合法转移
        if observed in RETREAT_STATES:
            # 退潮：连续 2 个有效交易日确认
            pending_downgrade += 1
            if pending_downgrade >= 2:
                return observed, pending_downgrade, "DOWNGRADE_CONFIRMED"
            return prev_eff, pending_downgrade, "PENDING_DOWNGRADE"
        # 升级/横向：1 天生效，但 UPGRADE_STATES 需要 confidence gate
        if observed in UPGRADE_STATES and not conf_ok:
            return prev_eff, 0, "UPGRADE_BLOCKED_LOW_CONFIDENCE"
        return observed, 0, "UPGRADE"
    # 非法转移（无解释大跳）→ 保持上一 effective
    return prev_eff, 0, "TRANSITION_BLOCKED"


def compute_driver_flags(factors_now, factors_prev):
    """四因子日变化 → drivers 标签。"""
    drivers = []
    if factors_prev is None:
        return drivers
    cov_d = (factors_now["coverage"]["score"] or 0) - (factors_prev["coverage"]["score"] or 0)
    men_d = (factors_now["mention"].get("net") or 0) - (factors_prev["mention"].get("net") or 0)
    trd_d = (factors_now["trade"]["raw_directional_value"] or 0) - (factors_prev["trade"]["raw_directional_value"] or 0)
    hold_d = (factors_now["holding"]["weighted_support"] or 0) - (factors_prev["holding"]["weighted_support"] or 0)
    if trd_d >= 1.5:
        drivers.append("TRADE_ACCELERATION")
    elif trd_d <= -1.5:
        drivers.append("TRADE_WEAKENING")
    if cov_d >= 0.5:
        drivers.append("COVERAGE_EXPANSION")
    elif cov_d <= -0.5:
        drivers.append("COVERAGE_CONTRACTION")
    if men_d >= 1:
        drivers.append("MENTION_POSITIVE_SHIFT")
    elif men_d <= -1:
        drivers.append("MENTION_NEGATIVE_SHIFT")
    if hold_d <= -0.2:
        drivers.append("HOLDING_SUPPORT_WEAKENING")
    elif hold_d >= 0.2:
        drivers.append("HOLDING_SUPPORT_STRENGTHENING")
    return drivers


def compute():
    grid = json.loads(HEAT_JSON.read_text(encoding="utf-8"))
    dates = sorted({r["date"] for r in grid})
    by_theme = defaultdict(list)
    for r in grid:
        by_theme[r["theme_id"]].append(r)
    for t in by_theme:
        by_theme[t].sort(key=lambda x: x["date"])

    out = []

    for theme_id in sorted(by_theme):
        rows = by_theme[theme_id]
        prev_eff = None            # 上一 effective 状态
        prev_row = None            # 上一有效交易日（drivers / has_history 用）
        prev_valid_row = None      # 上一 VALID 交易日（Δ1 参考；跳过 LOW_SIGNAL）
        prev_hist = []             # 之前所有有效交易日 (weight, row)（Δ3 与 max heat 用）
        pending_downgrade = 0      # 降级防抖：连续命中降级的天数（0/1/2）
        hist_max_heat = 0.0        # 历史 max heat（FADING 锚点 / no_prior_signal）
        consecutive_valid_decline = 0  # 连续几个 VALID 交易日 heat 严格递减

        for i, row in enumerate(rows):
            if not is_available(row):
                out.append({
                    "date": row["date"], "theme_id": theme_id,
                    "heat_score": None, "delta_1d": None, "delta_3d": None,
                    "delta1_reference_date": None, "delta1_reference_status": None,
                    "observed_momentum_state": None, "effective_momentum_state": prev_eff,
                    "momentum_status": None,
                    "signal_confidence": row["signal_confidence"],
                    "heat_status": row["heat_status"], "momentum_drivers": [],
                    "note": "INSUFFICIENT_DATA_SKIP",
                })
                continue

            heat = row["heat_score"]
            conf = row["signal_confidence"]
            conf_ok = conf in ("HIGH", "MEDIUM")

            # ====== BASELINE：该主题的第一个有效观测日 ======
            # 数据观察起点 ≠ 主题发现日 → 不标 DISCOVERY，设 momentum_status=BASELINE_ONLY / effective=NULL
            if prev_row is None:
                out.append({
                    "date": row["date"], "theme_id": theme_id,
                    "theme_name": row["theme_name"],
                    "heat_score": round(heat, 2),
                    "delta_1d": None, "delta_3d": None,
                    "delta1_reference_date": None, "delta1_reference_status": None,
                    "observed_momentum_state": "UNCLASSIFIED_BASELINE",
                    "effective_momentum_state": None,
                    "momentum_status": "BASELINE_ONLY",
                    "signal_confidence": conf,
                    "heat_status": row["heat_status"],
                    "momentum_drivers": [],
                    "note": "BASELINE_ONLY",
                })
                prev_row = row
                prev_hist.append((day_weight(row), row))
                hist_max_heat = max(hist_max_heat, heat)
                if row["heat_status"] == "VALID":
                    prev_valid_row = row
                continue

            # ================= 三量计算 =================
            # Δ1：跳过 LOW_SIGNAL，取上一个 VALID 日
            d1 = heat - prev_valid_row["heat_score"] if prev_valid_row is not None else None
            d1_ref_date = prev_valid_row["date"] if prev_valid_row is not None else None
            d1_ref_status = prev_valid_row["heat_status"] if prev_valid_row is not None else None

            # Δ3：近 3 个有效交易日加权基线（VALID=1.0 / LOW_SIGNAL=0.5）
            window = prev_hist[-DELTA3_WINDOW:]
            d3 = None
            if window:
                wsum = sum(w * (r_["heat_score"]) for w, r_ in window)
                wden = sum(w for w, _ in window)
                if wden > 0:
                    base3 = wsum / wden
                    d3 = heat - base3

            observed = compute_observed(heat, d1, d3, hist_max_heat,
                                        consecutive_valid_decline, [r for _, r in prev_hist])

            # ================= effective 决策 =================
            # 严重恶化（Δ1<=-15 或 NEGATIVE mention + negative trade 同日）→ 立即进 COOLING
            men_neg = (row["factors"]["mention"].get("net") or 0) < 0
            trd_neg = (row["factors"]["trade"]["raw_directional_value"] or 0) < 0
            severe = (d1 is not None and d1 <= SEVERE_DROP_DELTA1_TH) or (men_neg and trd_neg)

            effective, pending_downgrade, note = decide_effective(
                prev_eff, observed, conf_ok, severe, pending_downgrade)

            drivers = compute_driver_flags(row["factors"], prev_row["factors"] if prev_row else None)

            rec = {
                "date": row["date"], "theme_id": theme_id,
                "theme_name": row["theme_name"],
                "heat_score": round(heat, 2),
                "delta_1d": round(d1, 2) if d1 is not None else None,
                "delta_3d": round(d3, 2) if d3 is not None else None,
                "delta1_reference_date": d1_ref_date,
                "delta1_reference_status": d1_ref_status,
                "observed_momentum_state": observed,
                "effective_momentum_state": effective,
                "momentum_status": "TRACKING",
                "signal_confidence": conf,
                "heat_status": row["heat_status"],
                "momentum_drivers": drivers,
                "note": note,
            }
            out.append(rec)

            # 推进状态（先算 consecutive 再更新 prev_row）
            prev_heat_valid = prev_valid_row["heat_score"] if prev_valid_row is not None else None
            prev_row = row
            prev_hist.append((day_weight(row), row))
            prev_eff = effective
            hist_max_heat = max(hist_max_heat, heat)
            # 连续下降只统计 VALID 日（LOW_SIGNAL 不推进也不打断 VALID 连续下降）
            if row["heat_status"] == "VALID" and prev_heat_valid is not None:
                consecutive_valid_decline = consecutive_valid_decline + 1 if heat < prev_heat_valid else 0
            if row["heat_status"] == "VALID":
                prev_valid_row = row

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写出 {len(out)} 行 → {OUT_JSON}")

    # 快速汇总
    eff_states = Counter(r["effective_momentum_state"] for r in out if r["effective_momentum_state"])
    obs_states = Counter(r["observed_momentum_state"] for r in out if r["observed_momentum_state"])
    print("observed:", dict(obs_states))
    print("effective:", dict(eff_states))
    return 0


if __name__ == "__main__":
    raise SystemExit(compute())
