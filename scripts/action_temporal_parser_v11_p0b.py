#!/usr/bin/env python3
"""0B.5 规则版 Action/Temporal Parser v1.1（事件级）。

v1.1 相对 v1 的核心变化（用户 2026-08-28 拍板）:
- 行级 temporal_type → 事件级: 每个事件独立 (action, action_status, temporal_type)（协议11）
- Status 判定 scope-first: 条件作用域 > 完成态证据 > 意向/计划 > 动作族默认（避免"跌破就卖"误判已卖）
- 时段词只进 temporal_type; 但"明确成交/进场型动作"本身可构成完成态证据（买入建仓/介入/上车/买进/低吸进场）
- 事件匹配用 multiset（Counter），不做普通集合去重
- 全部 backlog A-P 落地；Gold v1 FINAL 冻结，本 parser 只适配真值、不反向改 Gold

输出:
  events[]         [{action, action_status, temporal_type, stance?}, ...]
  position_state   HOLDING/None
  buy_suppressed   bool
"""
import re

# ============================================================
# 词典（依据冻结 Gold Sample v1 FINAL 112 个 CORE events 反推）
# ============================================================

# ---- 卖出族（协议13 仓位程度分级：同分句取最强 CLEAR > 退出词 > 止盈/减仓） ----
CLEAR_WORDS = ["清仓", "清出", "全走", "全部卖出", "已清", "已走", "清掉", "全部清", "全部走"]
SELL_EXIT_WORDS = ["离场", "出局", "出完", "走人", "出掉", "出光", "断走", "可考虑出"]  # 覆盖止盈 → SELL
SELL_WORDS = ["卖出"]   # 单独出现 → SELL；与止盈同现 → 止盈优先 REDUCE（[13]）
REDUCE_WORDS = ["减仓", "减持", "减出", "减", "落袋", "兑现", "止盈", "高抛", "减掉", "了结"]

# ---- 买入族 ----
BUY_WORDS = ["买入建仓", "买入", "买进", "介入", "上车", "建仓", "建底仓", "打底仓",
             "打板", "抢筹", "半路", "拿筹码", "拿点筹码", "进货", "拿货", "抄底"]
LOW_BUY_WORDS = ["低吸", "低吃", "低吸进场", "低位接", "回踩吸"]
ADD_WORDS = ["加仓", "补仓", "回补", "接回", "小加仓", "加0.5", "之上加", "就加"]
TRIAL_WORDS = ["试错", "试盘", "试仓", "分仓试错", "小仓位博弈", "博弈一把", "想干", "可以动"]
HOLD_WORDS = ["持有", "持股", "拿着", "拿筹码", "继续看", "继续持有", "持股观察",
              "持有观察", "不动", "不用动", "不打算动", "无变化", "不破不走",
              "不破不走人", "继续跑", "拿着筹码", "不用跑", "持有为主"]
WATCH_WORDS = ["关注", "观察", "跟踪", "自选", "受益标的", "标的", "回避", "相信",
               "期待", "看", "耐心", "修复新高", "注意"]
DO_T_WORDS = ["高抛低吸", "滚动操作", "打地鼠", "反复做", "做T", "做t"]

# ---- 完成态证据（协议12 细化） ----
# 已X / X了 / X掉（低吸了 除外——[67] 低吸了一点 → INTENDED，小量试探不算完成）
EXEC_COMPLETED_RE = re.compile(
    r"(已(?:减|加|清|走|卖|接|补|买|出|低吸|建|上车|介入|抢|半路|拿|离|兑现|止盈|落袋|减持)"
    r"|(?:买|加|接|补|出|卖|减|清|走|离|兑现|止盈|落袋|上车|介入)了"
    r"|(?:减|清|卖|走|出)掉)")
# 明确成交/进场型动作 → 本身可构成完成态证据（用户 2026-08-28 修正点 1）
EXEC_ENTRY_WORDS = ["买入建仓", "买进", "介入", "上车", "低吸进场", "抢筹到手", "已拿筹码"]
# 卖出族动作词本身 = 完成态证据（协议6/13；无条件/计划修饰时）
SELL_COMPLETED_WORDS = ["卖出", "减仓", "减持", "离场", "出局", "清仓", "兑现", "止盈",
                        "落袋", "出完", "走人", "已走", "已清", "回本离场", "减出"]

# ---- 条件标记（scope-first，协议 B/J；按强度分，避免 可/能 误伤） ----
CONDITIONAL_STRONG_RE = re.compile(
    r"(若|如果|假如|则|再考虑|等|逢|回踩|站上|确认|突破|能板就|不破|收不回|跌破|破位|"
    r"冲涨停|涨多|之上加|之上减|不连板|超预期|断走|走独立行情|冲高择机|换手够|"
    r"跌到|够还|不能回封|可考虑|之后|决定|走出|构成|启动后|确认后|加速后|别追|不追|"
    r"破\d|收回\d|若有所|回调)")
# 未来条件（等待状态到位 → CONDITIONAL + FUTURE_PLAN；华勤 回调结束可打底仓）
FUTURE_COND_RE = re.compile(r"(回调结束|回调到位|调整结束|回落到位|企稳后|回调后|拉回后|回踩确认后)")
# 弱条件词（仅在特定语境）不单独触发 CONDITIONAL
CONDITIONAL_WEAK = ["可", "可以", "能", "够", "将", "才"]

# ---- 意向/计划/倾向（协议10 D；协议9 E） ----
TENDENCY_RE = re.compile(r"(为主|为主基调|倾向|偏多|偏空)")
PLAN_RE = re.compile(r"(准备|打算|计划|将|后市|再考虑|择机)")
RECOMMEND_RE = re.compile(r"(推荐|核心推荐|核心标的|重点推荐|看好|重点关注|建议关注|值得关注)")
# 推荐给他人（同学/大家/散户/你们）→ 建议语义，动作降 INTENDED
ADVICE_TO_OTHERS_RE = re.compile(r"(同学|大家|散户|你们|圈内|建议|可关注)")

# ---- 时间词（已X 只作完成态证据，不作 PAST 标记；PAST 需 之前/周X/昨日 等） ----
PAST_RE = re.compile(r"(之前|昨天|昨日|上周|上周五|前天|前几天|周[一二三四五六日])")
FUTURE_RE = re.compile(r"(明天|明日|下周|准备|打算|计划|后市|月内|年内|之后|接下来|未来)")
TODAY_RE = re.compile(r"(今日|今天|早盘|尾盘|盘中|开盘|现价|午后|下午|尾市|收盘)")
TIME_SEQ_RE = re.compile(r"\d{1,2}:\d{2}")   # 09:55 等

# ---- 仓位/参考区间 → 计划建仓（协议 C，需前置语义词门控） ----
POSITION_SIZE_RE = re.compile(r"(参考区间|配置|仓位建议|仓位\d|计划|目标区间)")
NUM_RANGE_RE = re.compile(r"\d+[-~]\d+|\d+成|\d+%|0\.\d+仓|\d+\.\d+")

# ---- stance（协议 P，不改 Action 枚举） ----
STANCE_RULES = [
    ("回避", "AVOID"), ("不追", "AVOID"), ("不碰", "AVOID"), ("谨慎", "AVOID"),
    ("相信", "POSITIVE"), ("没问题", "POSITIVE"), ("看好", "POSITIVE"), ("强", "POSITIVE"),
    ("观望", "WAIT"), ("等分歧", "WAIT"),
    ("关注", "FOLLOW"), ("跟踪", "FOLLOW"), ("受益", "FOLLOW"), ("强势", "FOLLOW"),
]


def _stance(text: str) -> str | None:
    for w, s in STANCE_RULES:
        if w in text:
            return s
    return None


def _split_clauses(text: str) -> list[tuple[str, int]]:
    """按标点分句（/ 不拆，保留"出局/接回"共享条件；的 作名物化边界 [9]）。
    返回 [(clause, start_pos)]。"""
    out = []
    pos = 0
    # 按标点拆（不含 /）
    for p in re.split(r"[，,；;、。！!？?（）()\n]", text):
        p = p.strip()
        if not p:
            pos += 1
            continue
        # 的 边界拆（去掉空段）
        for s in re.split(r"的", p):
            s = s.strip()
            if s:
                out.append((s, pos))
            pos += len(s) + 1
    return out


def _find_actions(clause: str) -> list[dict]:
    """在单个分句中找全部动作（含卖出程度分级、止盈让位）。返回 [{word, action, pos}]。"""
    found = []
    # 卖出族：程度分级（协议13）—— CLEAR > 退出词(SELL) > 止盈/减仓(REDUCE)
    # 止盈 + 卖出(无退出词) → REDUCE（[13] 止盈卖出）；止盈 + 离场/出局/出完/走人/清仓 → 让位
    def _sell_degree():
        for w in CLEAR_WORDS:
            if w in clause:
                return "CLEAR", w
        for w in SELL_EXIT_WORDS:
            if w in clause:
                return "SELL", w
        if "止盈" in clause:
            return "REDUCE", "止盈"      # 止盈 + 卖出/减仓/无 → REDUCE（[13][5][92]）
        for w in SELL_WORDS:
            if w in clause:
                return "SELL", w
        if "高抛" in clause:
            return "REDUCE", "高抛"
        for w in REDUCE_WORDS:
            if w in clause:
                return "REDUCE", w
        return None, None
    sell_action, sell_word = _sell_degree()
    if sell_action:
        # 兑现为主/以兑现为主 → SELL（[29]）；兑现+收益/利润/浮盈/修复 → REDUCE 部分兑现
        if sell_word == "兑现":
            if TENDENCY_RE.search(clause):
                sell_action = "SELL"
            elif re.search(r"兑现(收益|利润|浮盈|修复|部分)", clause):
                sell_action = "REDUCE"
        pos = clause.find(sell_word)
        found.append({"word": sell_word, "action": sell_action, "pos": pos})
    # 买入族
    for w in BUY_WORDS + LOW_BUY_WORDS + ADD_WORDS + TRIAL_WORDS + DO_T_WORDS:
        for m in re.finditer(re.escape(w), clause):
            act = None
            if w in BUY_WORDS:
                act = "BUY"
            elif w in LOW_BUY_WORDS:
                act = "LOW_BUY"
            elif w in ADD_WORDS:
                act = "ADD"
            elif w in TRIAL_WORDS:
                act = "TRIAL"
            elif w in DO_T_WORDS:
                act = "DO_T"
            found.append({"word": w, "action": act, "pos": m.start()})
    # HOLD / WATCH
    for w in HOLD_WORDS:
        for m in re.finditer(re.escape(w), clause):
            found.append({"word": w, "action": "HOLD", "pos": m.start()})
    for w in WATCH_WORDS:
        for m in re.finditer(re.escape(w), clause):
            found.append({"word": w, "action": "WATCH", "pos": m.start()})
    # 去重同位置同词；按位置排序
    seen = set()
    uniq = []
    for f in sorted(found, key=lambda x: (x["pos"], -len(x["word"]))):
        k = (f["pos"], f["word"])
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    # 同分句同 action 去重（保留第一个出现）+ 否定过滤（不/没/暂不/别 + 动作词 → 抑制）
    final = []
    act_seen = set()
    NEGATABLE = ("BUY", "LOW_BUY", "ADD", "TRIAL", "REDUCE", "SELL", "CLEAR")
    for f in uniq:
        if f["action"] in NEGATABLE and re.search(r"(不|没|暂不|别)" + re.escape(f["word"]), clause):
            continue   # [69] 暂不加仓 / [52] 不破不走人→不走人 抑制
        if f["action"] not in act_seen:
            act_seen.add(f["action"])
            final.append(f)
    # WATCH 姿态词（关注/观察/跟踪/看）与真实动作同句 → WATCH 是 stance 前缀，抑制 WATCH 事件（[27] 持续跟踪反复做→DO_T）
    real = [f for f in final if f["action"] not in ("WATCH",)]
    if real and any(f["action"] == "WATCH" for f in final):
        final = [f for f in final if f["action"] != "WATCH"]
    # 高抛低吸 复合词 → DO_T 不拆（协议6）：抑制其子词 高抛/低吸 产生的 REDUCE/LOW_BUY（[9] 博睿）
    if "高抛低吸" in clause or "来回高抛" in clause:
        final = [f for f in final if f["action"] not in ("REDUCE", "LOW_BUY") and f["word"] not in ("高抛", "低吸")]
    return final


HOLD_COND_IN_CLAUSE = re.compile(r"(若|如果|不破|收不回|走独立行情|等|逢|收回\d|站上\d|破\d|若有所)")
HOLD_COND_IN_REMAIN = re.compile(r"(若|如果|破\d|等|收不回|逢|站上\d|跌破)")
WATCH_COND = re.compile(r"(等|若|如果|逢|分歧|再看|回踩)")


def _is_conditional(clause: str, act_pos: int, action: str, remain: str = "") -> bool:
    """条件作用域优先：当前动作是否被条件词支配（协议11 scope-first）。"""
    if action == "HOLD":
        # 持有条件：持有分句内 或 紧随其后的分句含显式条件词（[56][100] COND；[80][44] 断言→CURRENT_STATE）
        return bool(HOLD_COND_IN_CLAUSE.search(clause) or HOLD_COND_IN_REMAIN.search(remain))
    if action == "WATCH":
        # [32] 等分歧看... → CONDITIONAL
        return bool(WATCH_COND.search(clause))
    if action == "DO_T":
        return bool(re.search(r"(涨多|之上|若|则|等)", clause))
    m = CONDITIONAL_STRONG_RE.search(clause)
    if not m:
        return False
    cpos = m.start()
    # 条件词出现在动作位置或之前 → 支配（断走/可考虑出/之上加 等动作词本身即条件短语）
    if cpos <= act_pos:
        return True
    # 条件词在动作之后但属于"X后/之后"结构（[92] 走出...后 接回 / [80] 断走）
    if re.search(r"(突破|超预期|走出|确认|之后|后).{0,6}(接|出|加|减|落|买|建)", clause):
        return True
    # 弱条件词在动作前（可/能/将/才）不单独触发
    return False


def _has_completion(clause: str, action: str, logic: str, raw: str) -> bool:
    """完成态证据：已X / X了 / 卖出族动作词 / 成交进场型动作（协议12 细化）。"""
    if EXEC_COMPLETED_RE.search(clause):
        return True
    if any(w in clause for w in EXEC_ENTRY_WORDS):
        return True
    if action in ("REDUCE", "SELL", "CLEAR"):
        if any(w in clause for w in SELL_COMPLETED_WORDS):
            return True
    # logic 补强（协议 N：同 sample 同 target 同 action 才有效；LOW_BUY 不适用——[62][64] 低吸持有仍 INTENDED）
    if logic:
        LOGIC_EV = {
            "BUY": ["买", "建", "上车", "介入", "拿"],
            "ADD": ["加", "补", "回", "接"],
            "LOW_BUY": [],      # 低吸小量试探不算完成态（[62][64]）
            "TRIAL": [],
            "REDUCE": ["减", "落", "兑现", "止盈"],
            "SELL": ["卖", "出", "离场", "走"],
            "CLEAR": ["清", "走"],
        }
        fam_ev = {"BUY": BUY_WORDS, "LOW_BUY": LOW_BUY_WORDS, "ADD": ADD_WORDS,
                  "TRIAL": TRIAL_WORDS, "REDUCE": REDUCE_WORDS, "SELL": SELL_WORDS + SELL_EXIT_WORDS,
                  "CLEAR": CLEAR_WORDS}[action]
        if any(m in logic for m in LOGIC_EV[action]) and any(w in raw for w in fam_ev):
            # 完成态逻辑词（已/了/只回）且 raw 确有该动作族
            if re.search(r"(已|了|只回|已回|已补|已接|已买|已卖)", logic):
                return True
    return False


def _is_tendency(clause: str) -> bool:
    """为主/倾向 → INTENDED（协议10 D）。"""
    return bool(TENDENCY_RE.search(clause))


def _is_advice_to_others(clause: str) -> bool:
    """推荐给他人（同学/大家/散户）→ 建议，动作降 INTENDED（[92] 短线同学清仓）。"""
    return bool(ADVICE_TO_OTHERS_RE.search(clause))


def _temporal_for(clause: str, act_pos: int, action: str, status: str,
                  is_cond: bool, logic: str, full_text: str) -> str:
    """事件级 temporal（协议11 隔离；本地分句作用域 + logic/全文辅助）。"""
    if action == "HOLD" and status == "POSITION_STATE":
        return "CONDITIONAL" if is_cond else "CURRENT_STATE"
    # FUTURE_PLAN：未来词 或 参考区间+仓位 或 未来条件（协议 C、O）——优先于条件（[96] 明天→FUTURE_PLAN）
    if FUTURE_RE.search(clause) or (is_cond and FUTURE_RE.search(full_text)) or \
            (is_cond and FUTURE_COND_RE.search(clause)):
        return "FUTURE_PLAN"
    if POSITION_SIZE_RE.search(clause) and NUM_RANGE_RE.search(clause):
        return "FUTURE_PLAN"
    if is_cond:
        return "CONDITIONAL"
    # logic 提供 PAST 仅当 raw 有明确完成态证据 且 raw 无今日词（[73] 周三；[5][11][95] 昨日/昨天不生效）
    if logic and PAST_RE.search(logic) and status == "EXECUTED" and \
            EXEC_COMPLETED_RE.search(full_text) and not TODAY_RE.search(full_text):
        return "PAST"
    if PAST_RE.search(clause):
        return "PAST"
    if TODAY_RE.search(clause):
        return "TODAY"
    return "TODAY"   # 默认 TODAY（P5：最后 fallback）


def parse(raw_action: str, raw_logic: str = "") -> dict:
    text = (raw_action or "").strip()
    logic = (raw_logic or "").strip()
    if not text:
        return {"events": [{"action": "UNKNOWN", "action_status": "UNKNOWN",
                            "temporal_type": "UNKNOWN"}],
                "position_state": None, "buy_suppressed": False}

    clauses = _split_clauses(text)
    events = []
    buy_suppressed = False
    pending_cond = False   # 跨分句条件（[86] 回踩...构成买点 → 控制仓位拿点筹码 继承条件）

    for clause, base_pos in clauses:
        # 条件 setup 句（以 后/迹象/买点/结构/确认 等收尾）→ 下一分句动作继承条件
        clause_is_setup = bool(re.search(
            r"(回踩|突破|超预期|站上|确认|等|不破|收不回|跌破|冲涨停|若|如果|走出|探路)", clause)) and bool(
            re.search(r"(后|迹象|确认|买点|结构|信号|模型|成立|为止|决定)$", clause))
        remain = text[base_pos + len(clause):]   # 该分句之后的文本（供 HOLD 条件判定）
        acts = _find_actions(clause)
        if not acts:
            # 无动作动词：计划建仓 > 姿态/推荐句 > 其他
            if POSITION_SIZE_RE.search(clause) and NUM_RANGE_RE.search(clause):
                events.append({"action": "BUY", "action_status": "INTENDED",
                               "temporal_type": "FUTURE_PLAN"})
                pending_cond = clause_is_setup
                continue
            if RECOMMEND_RE.search(clause) or any(
                    w in clause for w in ("关注", "观察", "跟踪", "参考", "标的", "回避",
                                          "相信", "看", "注意", "期待", "耐心")):
                ev = {"action": "WATCH", "action_status": "INTENDED",
                      "temporal_type": "TODAY", "stance": _stance(clause)}
                events.append(ev)
                pending_cond = clause_is_setup
                continue
            if TIME_SEQ_RE.search(clause):
                events.append({"action": "WATCH", "action_status": "INTENDED",
                               "temporal_type": "TODAY", "stance": _stance(clause)})
                pending_cond = clause_is_setup
                continue
            pending_cond = clause_is_setup
            continue

        for a in acts:
            action = a["action"]
            # E：推荐/看好 抑制买入族 → WATCH
            if action in ("BUY", "LOW_BUY", "ADD", "TRIAL") and RECOMMEND_RE.search(clause):
                action = "WATCH"
                buy_suppressed = True
            # K：姿态句（关注/观察/回避/相信/期待，无真实交易动作）→ WATCH
            if action in ("BUY", "SELL", "REDUCE", "CLEAR") and any(
                    w in clause for w in ("关注", "观察", "跟踪", "回避", "相信", "期待", "观望")):
                # 仅当动作词与姿态词距离很远且动作词是弱词（拿筹码/买点/低吸）→ 姿态优先
                pass

            # ---- Status（HOLD/WATCH/DO_T 状态固定，is_cond 只影响其 temporal；其余 scope-first） ----
            is_cond = pending_cond or _is_conditional(clause, a["pos"], action, remain)
            if action == "HOLD":
                # 建议继续持有(可以继续/继续持有/继续跑) → INTENDED；否则持仓事实 → POSITION_STATE
                status = "INTENDED" if re.search(r"(可以继续|可继续|继续持有|继续跑)", clause) else "POSITION_STATE"
            elif action in ("WATCH", "DO_T"):
                status = "INTENDED"      # [59] DO_T/CONDITIONAL 由 temporal 表达条件
            elif is_cond:
                status = "CONDITIONAL"
            elif _is_tendency(clause):
                status = "INTENDED"      # 协议10：为主/倾向 = 意向，覆盖卖出族默认 EXECUTED
            elif _has_completion(clause, action, logic, text):
                status = "EXECUTED"
            elif PLAN_RE.search(clause):
                status = "INTENDED"
            elif action in ("BUY", "LOW_BUY", "ADD", "TRIAL"):
                status = "INTENDED"      # 买入族无完成证据 → INTENDED（保守执行语义）
            elif action in ("REDUCE", "SELL", "CLEAR"):
                status = "EXECUTED"      # 卖出族无条件/计划 → EXECUTED
            else:
                status = "INTENDED"

            # 推荐给他人（同学清仓等）→ 建议降 INTENDED
            if status == "EXECUTED" and _is_advice_to_others(clause):
                status = "INTENDED"

            # ---- Temporal（事件级） ----
            temporal = _temporal_for(clause, a["pos"], action, status, is_cond, logic, text)

            ev = {"action": action, "action_status": status, "temporal_type": temporal}
            if action == "WATCH":
                st = _stance(clause)
                if st:
                    ev["stance"] = st
            events.append(ev)
        pending_cond = clause_is_setup

    # 行内去重相同三元组（多分句同动作同态合并；Gold 亦折叠 [80][11]）
    seen = set()
    dedup = []
    for ev in events:
        k = (ev["action"], ev["action_status"], ev["temporal_type"])
        if k not in seen:
            seen.add(k)
            dedup.append(ev)
    events = dedup

    # DO_T 与条件动作（涨多减/之上加）同现 → DO_T 为条件 temporal（[59] 滚动操作；status 保持 INTENDED）
    # 仅限具体条件词 涨多/之上，不含 等/若（[9] 等待择向 → TODAY）
    if any(e["action"] == "DO_T" for e in events) and re.search(r"(涨多|之上)", text):
        for e in events:
            if e["action"] == "DO_T":
                e["temporal_type"] = "CONDITIONAL"
    # TRIAL 受结构条件支配（[76] 突破买点结构后...小仓位博弈；[M] 突破后/回踩后）
    if any(e["action"] == "TRIAL" for e in events) and re.search(
            r"(突破|超预期|走出|站上|确认|回踩|探路尖兵)", text):
        for e in events:
            if e["action"] == "TRIAL":
                e["action_status"] = "CONDITIONAL"
                e["temporal_type"] = "CONDITIONAL"

    # 空事件兜底：A股换X → UNKNOWN（[78]）；其余无动作句 → WATCH（语料默认观察姿态）
    if not events and clauses:
        if re.search(r"(换股|换港股|换美股|换市场)", text):
            events = [{"action": "UNKNOWN", "action_status": "INTENDED",
                       "temporal_type": "UNKNOWN"}]
        else:
            events = [{"action": "WATCH", "action_status": "INTENDED",
                       "temporal_type": "TODAY", "stance": _stance(text)}]

    position_state = "HOLDING" if any(
        e["action"] == "HOLD" and e["action_status"] == "POSITION_STATE" for e in events) else None

    return {"events": events, "position_state": position_state, "buy_suppressed": buy_suppressed}


if __name__ == "__main__":
    # 自测（含 v1 回归 + 新规则）
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
        ("收回5日均线持股，收不回减持，等13日均线再考虑回补", ""),   # A
        ("冲涨停出局/接回", ""),                                    # B
        ("参考区间410-450，仓位1成", ""),                          # C
        ("操作谨慎，今日兑现为主", ""),                             # D
        ("核心推荐标的", ""),                                      # E
        ("之前减仓的可以继续跑", ""),                              # F
        ("圈友已加仓，走独立行情可继续持有", "圈内旧票被重新炒作逻辑未变，圈友周三41"),  # G/N
        ("回补持有", "五虎中只回了有研硅（回去的是最强的）"),        # N
        ("打底仓（盘中不追高）；等半导体设备指数收盘确认突破后绿盘小加仓", ""),  # I
        ("止盈离场", ""),                                          # J
        ("回避，科技套牢盘太重", ""),                             # K/P
        ("提前拿筹码控仓位，博弈资金回流", ""),                    # L
        ("突破买点结构后走出探路尖兵模型迹象，可小仓位博弈", ""),  # M
        ("明天能否超预期决定板块强度，不能强更强加速则后排落袋", ""),  # O
    ]
    for t, l in tests:
        r = parse(t, l)
        print(f"{t[:22]!r} → {r['events']} pos={r['position_state']}")
