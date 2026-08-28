#!/usr/bin/env python3
"""0B.5 规则版 Action/Temporal Parser v1。

输入: raw_action + raw_logic（博主原始操作描述）
输出:
  actions[]        [(action, status), ...]  多动作，每个带状态
  temporal_type    TODAY/PAST/CURRENT_STATE/FUTURE_PLAN/CONDITIONAL/UNKNOWN
  position_state   HOLDING/None

设计原则（用户确认）:
- 规则优先，不引入 LLM 推理
- 高置信才产出动作；无匹配 → UNKNOWN（Precision 优先）
- 持有/持仓态 → position_state=HOLDING，绝不产出当日 BUY（双轨）
- 计划/条件 → 绝不误标 EXECUTED
"""
import re

# ---------------- 动作词典（按特异性降序，长词优先） ----------------
# (关键词, 动作)
ACTION_RULES = [
    # DO_T（复合/滚动）
    ("高抛低吸", "DO_T"), ("滚动操作", "DO_T"), ("打地鼠", "DO_T"),
    ("反复做", "DO_T"), ("做T", "DO_T"),
    # LOW_BUY
    ("低吸", "LOW_BUY"), ("低吃", "LOW_BUY"),
    # ADD
    ("加仓", "ADD"), ("补仓", "ADD"), ("回补", "ADD"), ("小加仓", "ADD"),
    ("接回", "ADD"), ("能板就加", "ADD"), ("加0.5", "ADD"), ("加", "ADD"),
    # TRIAL
    ("试错", "TRIAL"), ("试盘", "TRIAL"), ("试仓", "TRIAL"), ("博弈", "TRIAL"),
    ("想干的", "TRIAL"), ("可以动", "TRIAL"),
    # BUY
    ("打板", "BUY"), ("打底仓", "BUY"), ("建底仓", "BUY"), ("建仓", "BUY"),
    ("上车", "BUY"), ("介入", "BUY"), ("买入", "BUY"), ("买点", "BUY"),
    ("拿点筹码", "BUY"), ("抢筹", "BUY"), ("半路", "BUY"),
    # REDUCE
    ("减仓", "REDUCE"), ("减持", "REDUCE"), ("减出", "REDUCE"),
    ("止盈", "REDUCE"), ("落袋", "REDUCE"), ("减", "REDUCE"),
    # CLEAR
    ("清仓", "CLEAR"), ("清出", "CLEAR"), ("已走", "CLEAR"), ("已清", "CLEAR"),
    # SELL
    ("卖出", "SELL"), ("出局", "SELL"), ("出完", "SELL"), ("离场", "SELL"),
    ("走人", "SELL"), ("兑现", "SELL"),
    # STOP_LOSS
    ("止损", "STOP_LOSS"), ("破位", "STOP_LOSS"),
    # HOLD（含双轨：不破不走=条件持有 / 无变化=维持）
    ("不破不走", "HOLD"), ("持有", "HOLD"), ("持股", "HOLD"), ("拿着", "HOLD"),
    ("拿筹码", "HOLD"), ("不动", "HOLD"), ("继续看", "HOLD"), ("继续持有", "HOLD"),
    ("底仓", "HOLD"), ("无变化", "HOLD"),
    # WATCH
    ("关注", "WATCH"), ("观察", "WATCH"), ("跟踪", "WATCH"), ("自选", "WATCH"),
    ("参考", "WATCH"), ("受益标的", "WATCH"), ("标的", "WATCH"), ("看", "WATCH"),
]
# 按长度降序，保证长词优先（减仓 在 减 之前）
ACTION_RULES.sort(key=lambda x: -len(x[0]))

# 仓位成数 → BUY（半路0.5仓 / 仓位1成 / 参考区间410-450，仓位1成）
POSITION_SIZE_RE = re.compile(r"(半路|0\.5仓|\d+成仓|仓位\d+成|仓位\d|参考区间)")

# ---------------- 状态标记 ----------------
# EXECUTED：已+动作动词（已减/已加/已清/已走/已卖/已接/已补/已买/已出）
EXECUTED_RE = re.compile(r"(已(?:减|加|清|走|卖|接|补|买|出|低吸|建|上车))")
# 时段+买入动词 → EXECUTED（早盘/尾盘/盘中/今日/今天/开盘/现价）
EXECUTED_TIME_RE = re.compile(r"(早盘|尾盘|盘中|今日|今天|开盘|现价|午后|下午)")
# 排除：已涨停/已跌/已涨/已破（市场状态非动作）
MARKET_STATE_RE = re.compile(r"已(涨停|跌|涨|破|站上|突破|绿|红)")

# CONDITIONAL：条件/等待/计划触发词
CONDITIONAL_MARKERS = [
    "若", "如果", "假如", "则", "再考虑", "再", "等", "逢", "回踩", "站上",
    "确认", "突破", "能板就", "不破", "收不回", "才", "将", "明天", "之后",
    "后市", "可考虑", "不连板", "则可", "够", "不能", "可", "以", "就", "接",
]
# 注意："以20日均线为锚点" 里的 以/为 不能当条件 → 用更精确的
CONDITIONAL_RE = re.compile(
    r"(若|如果|假如|则|再考虑|等|逢|回踩|站上|确认|突破|能板就|不破|收不回|"
    r"才|将|明天|之后|后市|可考虑|不连板|则可|够|不能|可)" )

# FUTURE_PLAN：未来计划词
FUTURE_RE = re.compile(r"(明天|后市|准备|打算|计划|将|即将|未来)")

# TODAY 时间词
TODAY_RE = re.compile(r"(今日|今天|早盘|尾盘|盘中|开盘|现价|午后|下午|尾市)")
PAST_RE = re.compile(r"(之前|前几天|昨日|昨天|上周|前几天|已|之前)")

# ---------------- 主函数 ----------------
def parse(raw_action: str, raw_logic: str = "") -> dict:
    text = (raw_action or "").strip()
    logic = (raw_logic or "").strip()
    if not text:
        return {"actions": [("UNKNOWN", "UNKNOWN")], "temporal_type": "UNKNOWN",
                "position_state": None, "buy_suppressed": False,
                "clauses": [], "action_clauses": []}

    # ---- 1. 否定 BUY：不追高/不追/不买 抑制买入 ----
    buy_suppressed = bool(re.search(r"不(追|买|抢|接|动)", text)) or "不追高" in text

    # ---- 2. 按分句拆分（；/，/、/；/）----
    clauses = [c for c in re.split(r"[；;，,、/]+", text) if c.strip()]

    # ---- 3. 分句级扫描动作（只在分句内扫，保证分句级状态）----
    found = []          # (action, clause_index, kw)
    seen_keywords = set()

    def clause_status(txt):
        """分句级状态标记"""
        exec_mark = bool(EXECUTED_RE.search(txt)) and not MARKET_STATE_RE.search(txt)
        # 时段+动作 → EXECUTED；但有 机会/最好/可/考虑 等机会语义 → 不标 EXECUTED
        opportunity = bool(re.search(r"机会|最好|可|考虑|会|将|想", txt))
        time_exec = bool(EXECUTED_TIME_RE.search(txt)) and not re.search(r"看|观察|跟踪|关注", txt) and not opportunity
        cond = bool(CONDITIONAL_RE.search(txt.replace("可以动", "")))  # 可以动=许可非条件（确认#5）
        # 未来计划：排除"不打算/没打算"（不打算动 = 维持持有）
        fut = bool(FUTURE_RE.search(txt)) and not re.search(r"不打算|没打算|不打|不准备", txt)
        # 计划标记：价格目标/左右 → 计划而非已执行（73.5左右减一半）
        plan_marker = bool(re.search(r"左右|以上|以下|目标|预计|计划减", txt))
        return exec_mark, time_exec, cond, fut, plan_marker

    for i, cl in enumerate(clauses):
        # 分句级抑制：暂不加仓/不加仓 → 该分句不识别加仓类；不破不走 → 不走人
        no_add = bool(re.search(r"不加仓|暂不加|先不加", cl))
        no_sell = bool(re.search(r"不破不走", cl))
        # 回踩买点跟踪 → WATCH（确认协议#5：无买卖动作，抑制 买点→BUY）
        watch_track = bool(re.search(r"跟踪|观察|关注", cl))
        matched_kws = []   # 本分句已命中的关键词（用于子串去噪）
        for kw, act in ACTION_RULES:
            if kw in cl and kw not in seen_keywords:
                if any(kw in mk for mk in matched_kws):   # 子串去噪：建底仓 命中后 不再命中 底仓/建仓
                    continue
                if act in ("BUY", "LOW_BUY", "ADD") and buy_suppressed and kw in ("买入", "追"):
                    continue
                if no_add and act == "ADD":
                    continue
                if no_sell and act == "SELL":
                    continue
                # 持有已命中 → 抑制同分句的 WATCH（持有观察→HOLD only）
                if act == "WATCH" and any(a_hold in cl for a_hold in ("持有", "持股", "拿着", "拿筹码", "不动", "继续看", "底仓")):
                    continue
                # 跟踪/观察语境下的 买点 → 不是 BUY（回踩买点跟踪=WATCH）
                if act == "BUY" and kw in ("买点", "买") and watch_track:
                    continue
                # CLEAR 已命中 → 抑制冗余 兑现/卖出（清仓兑现→CLEAR only）
                if act == "SELL" and kw in ("兑现", "卖出") and any(mk.startswith("清仓") or mk == "清出" or mk == "已走" for mk in matched_kws):
                    continue
                found.append((act, i, kw))
                seen_keywords.add(kw)
                matched_kws.append(kw)
        # 仓位成数 → BUY（半路0.5仓 / 仓位1成）
        if not no_add and POSITION_SIZE_RE.search(cl) and not re.search(r"控制仓位|仓位.*控制|仓位上", cl):
            if "BUY" not in seen_keywords:
                found.append(("BUY", i, "position-size"))
                seen_keywords.add("BUY")

    # 去重：按 action 保留首个分句（同动作多次出现 → 合并为一个事件）
    action_clauses = []  # [(action, clause_index)]
    seen_actions = set()
    for act, ci, kw in found:
        if act in seen_actions:
            continue
        seen_actions.add(act)
        action_clauses.append((act, ci))
    if not action_clauses:
        # 无动作命中：若被抑制买入 → WATCH（不追=观察），否则 UNKNOWN
        actions = ["WATCH"] if buy_suppressed else ["UNKNOWN"]
        statuses = ["INTENDED"]
        temporal = "UNKNOWN"
        return {"actions": list(zip(actions, statuses)), "temporal_type": temporal,
                "position_state": None, "buy_suppressed": buy_suppressed,
                "clauses": clauses, "action_clauses": [("WATCH" if buy_suppressed else "UNKNOWN", 0)]}

    # ---- 4. 分句级状态判定 ----
    # 每个分句的状态标记
    clause_flags = [clause_status(cl) for cl in clauses]
    # 全文级标记（用于 temporal 判定）
    full_exec, full_time, full_cond, full_fut, _ = clause_status(text)

    actions = []
    statuses = []
    has_sell_act = any(a in ("REDUCE", "SELL", "CLEAR") for a, _ in action_clauses)

    for a, ci in action_clauses:
        exec_mark, time_exec, cond, fut, plan_marker = clause_flags[ci]
        # 双轨：持有类关键词 → POSITION_STATE（独立于买入/减仓，HOLD 是当前持仓状态）
        if a == "HOLD":
            statuses.append("POSITION_STATE")
        # WATCH = 观察姿态（权重0）→ 恒 INTENDED（确认#8 回踩买点跟踪=WATCH/INTENDED）
        elif a == "WATCH":
            statuses.append("INTENDED")
        elif (exec_mark or (time_exec and a in ("BUY", "LOW_BUY", "ADD", "REDUCE", "SELL", "CLEAR", "TRIAL", "DO_T"))):
            statuses.append("EXECUTED")
        # 清仓/清出/已走 = 终止性已报告动作 → 默认 EXECUTED（确认协议#7 清仓兑现=EXECUTED），除非条件/计划
        elif a == "CLEAR" and not cond and not fut and not plan_marker:
            statuses.append("EXECUTED")
        # 减仓/卖出 = 已报告动作 → 默认 EXECUTED（确认协议#6 适度减仓止盈=EXECUTED），除非条件/计划
        elif a in ("REDUCE", "SELL") and not cond and not fut and not plan_marker:
            statuses.append("EXECUTED")
        elif cond:
            statuses.append("CONDITIONAL")
        else:
            statuses.append("INTENDED")
        actions.append(a)

    # ---- 5. 时间语义（按已确认协议：默认 TODAY=当日分析操作）----
    hold_only = set(actions) <= {"HOLD", "WATCH", "DO_T"} and "HOLD" in actions
    # 条件判定：动作所在分句含条件词且该分句无已执行/时间标记（条件词必须门控该动作）
    any_cond_clause = any(
        clause_flags[ci][2] and not clause_flags[ci][0] and not clause_flags[ci][1]
        for _, ci in action_clauses
    )
    if full_fut and not full_exec:
        temporal = "FUTURE_PLAN"
    elif any_cond_clause:
        temporal = "CONDITIONAL"
    elif full_exec or full_time or bool(TODAY_RE.search(text)):
        temporal = "TODAY"
    elif hold_only:
        temporal = "CURRENT_STATE"
    elif PAST_RE.search(text) and not bool(TODAY_RE.search(text)):
        temporal = "PAST"
    else:
        temporal = "TODAY"   # 默认：当日分析中的操作（确认协议#1/#3/#5 均为 TODAY）

    # ---- 6. 双轨：position_state（任一 HOLD 为 POSITION_STATE → 持仓）----
    position_state = "HOLDING" if any(a == "HOLD" and s == "POSITION_STATE" for a, s in zip(actions, statuses)) else None

    action_items = list(zip(actions, statuses))
    return {
        "actions": action_items,
        "temporal_type": temporal,
        "position_state": position_state,
        "buy_suppressed": buy_suppressed,
        "clauses": clauses,
        "action_clauses": action_clauses,  # [(action, clause_index)]
    }


if __name__ == "__main__":
    # 快速自测
    tests = [
        ("低吸持有", ""),
        ("尾盘买入建仓", ""),
        ("部分减仓止盈，放量突破则小幅加仓", ""),
        ("持有", ""),
        ("已清仓", ""),
        ("关注", ""),
        ("回踩60均线构成买点，控制仓位拿点筹码", ""),
        ("绿盘低吃，冲高择机做T", ""),
        ("等底分结构确立再回补，等待放量金叉", ""),
    ]
    for t, l in tests:
        print(f"{t!r} → {parse(t, l)}")
