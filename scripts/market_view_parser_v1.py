#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
market_view_parser_v1 — Market View 三轴独立解析器（Phase 2.0B）v2 重写版
=====================================================================
与 Action Parser 完全解耦：独立文件、独立词典、独立 benchmark，不 import action parser。

输入 : raw_text —— 某分析师某天 core_theme + trend + logic 原文聚合
输出 : dict 固定结构
    view_scope            : MARKET | MIXED | STOCK_ONLY | UNKNOWN
    market_direction      : STRONG_BULLISH | BULLISH | NEUTRAL | BEARISH | STRONG_BEARISH | UNKNOWN
    market_score          : +2/+1/0/-1/-2/None —— 由 market_direction 自动映射（MV-1）
    risk_level            : LOW | MEDIUM | HIGH | UNKNOWN
    position_bias         : AGGRESSIVE | ADD_ON_DIP | HOLD | CONTROL_POSITION | REDUCE | WAIT | UNKNOWN
    direction_evidence    : [命中原始短句]（解释层基础）
    risk_evidence         : [命中原始短句]
    bias_evidence         : [命中原始短句]
    confidence            : {direction, risk, bias} ∈ 0~1
    exclude_from_market_consensus : bool
    explain               : 判定说明

协议（用户 2026-08-29/30 锁定）：
  MV-1 : score 由 direction 自动映射
  MV-2 : 三轴独立判定，任一轴不反推另一轴
  MV-3 : direction 取最近 1-3 交易日最明确方向；多空冲突不强行中和（真矛盾→NEUTRAL）
  MV-4 : STOCK_ONLY / 无观点 → 三轴 UNKNOWN + exclude=True
  Benchmark：Scope=50 / Direction|Risk|Bias=46 eligible；硬 Gate：STOCK_ONLY→误生成=0，UNKNOWN→误生成=0
"""

import re

# ============================== MV-1 方向→分数映射 ==============================
DIRECTION_SCORE_MAP = {
    "STRONG_BULLISH": +2, "BULLISH": +1, "NEUTRAL": 0,
    "BEARISH": -1, "STRONG_BEARISH": -2, "UNKNOWN": None,
}
VALID_DIRECTIONS = set(DIRECTION_SCORE_MAP)
VALID_RISK   = {"LOW", "MEDIUM", "HIGH", "UNKNOWN"}
VALID_BIAS   = {"AGGRESSIVE", "ADD_ON_DIP", "HOLD", "CONTROL_POSITION", "REDUCE", "WAIT", "UNKNOWN"}
VALID_SCOPE  = {"MARKET", "MIXED", "STOCK_ONLY", "UNKNOWN"}

# ============================== 无观点信号 ==============================
NO_VIEW_PATTERNS = [
    "今日无有效新观点", "无有效新观点", "今日无观点", "无观点", "暂无观点",
    "今天没观点", "今日没观点", "无新增观点", "没有新观点", "无有效观点",
    "今日无观点更新", "今日暂无明显观点", "没有明显观点", "今日没有新观点",
]

# ============================== 句子级 scope 词表 ==============================
# 强市场词（权重1）：出现 1 个即构成市场句（板块/大盘/事件级判断）
STRONG_MKT_TERMS = [
    "大盘", "指数", "上证", "深成", "创业板指", "两市", "沪深", "A股", "市场",
    "成交额", "成交量", "放量", "缩量", "普涨", "普跌", "赚钱效应", "冰点",
    "变盘", "主升", "二浪", "三浪", "牛市", "熊市", "退潮", "恐慌", "避险",
    "破位", "失守", "站上", "站稳", "关口", "4000", "3900", "3874", "底部",
    "顶部", "压力位", "支撑位", "背离", "双金叉", "死叉", "翻红", "绿盘",
    "中阳", "中阴", "涨停潮", "跌停潮", "避险", "风险偏好", "增量资金",
    "净流出", "净流入", "资金", "风格", "外围", "美股", "纳指", "美债",
    "加息", "熔断", "黑天鹅", "监管", "利好", "利空", "行情", "科技",
    "双创", "科创", "英伟达", "财报", "业绩", "券商", "机会", "新高",
    "反包", "见顶", "事件", "上市", "大环境", "跷跷板", "最后一跌", "好日子",
    "收复", "降息", "靴子落地", "不确定性", "压力", "压制", "支撑", "均线",
    "趋势", "变盘期", "确定性", "盘面", "看多", "做多", "看好",
]
# 弱市场词（权重0.5）：需 2 个弱词或 1 强词才构成市场句；个股语境也常见故不给强权
WEAK_MKT_TERMS = [
    "高开", "低开", "轮动", "情绪", "反弹", "修复", "回调", "调整", "企稳",
    "回暖", "上涨", "下跌", "走强", "转强", "走弱", "转弱", "拉升", "冲",
    "回落", "探底", "分化", "震荡", "护盘", "托举", "接力", "跳水",
    "急跌", "弱势",
]
# 个股操作词
STOCK_OP_TERMS = [
    "持仓", "买入", "卖出", "低吸", "低吃", "做T", "加仓", "减仓", "止盈",
    "止损", "清仓", "换仓", "建仓", "半路", "打板", "割肉", "回补", "开仓",
    "出局", "落袋", "卖飞", "追高", "买点", "卖点", "仓位", "持股", "持有",
    "标的", "个股", "自选", "换板", "秒板", "连板", "封板", "兑现", "减半",
    "买入", "买入", "回踩均线", "涨停",
]

def _split_sentences(text):
    return [s.strip() for s in re.split(r"[。；！？\n]|SEP", text) if s.strip()]

def _sentence_market_score(sent):
    strong = sum(1 for t in STRONG_MKT_TERMS if t in sent)
    weak = sum(1 for t in WEAK_MKT_TERMS if t in sent)
    # 市场句 = 1 个强市场词，或 2 个弱市场词
    if strong >= 1:
        return 1.0
    if weak >= 2:
        return 1.5
    return 0.0

def _sentence_stock_score(sent):
    return sum(1 for t in STOCK_OP_TERMS if t in sent)

# ============================== Direction：立场短语 ==============================
# 每个短语：(正则, 权重)。权重正=多头 负=空头。条件/否定/转折由 _score_clause 处理。
DIR_PATTERNS = [
    # ---- 强多头 +3/+4 ----
    (r"坚决看多|坚定看多", 4), (r"否极泰来", 4), (r"开启(新)?(的)?一轮|新一轮", 4),
    (r"升级为反转", 4), (r"天时转好", 4), (r"情绪修复转强|修复转强", 3),
    (r"放量(上涨|向上|突破)", 3), (r"止跌回暖|止跌回升", 3), (r"转强向上", 3),
    (r"大概率(二次|多次)?冲顶", 3), (r"站上", 2), (r"站稳", 3),
    (r"反包新高", 3), (r"新高", 1), (r"再向上(一步|一程)?", 3),
    (r"行情(感觉)?(要)?来了", 3), (r"大好消息", 3), (r"最好的消息", 3),
    (r"全面超预期|大幅超预期|强于预期", 3), (r"超预期", 2),
    (r"支持做多|继续做多|积极做多|做多", 2), (r"看多", 2), (r"看好", 2), (r"看涨", 2),
    (r"主升", 3), (r"反转", 2), (r"迎接(日线)?(三浪|上涨|主升)", 3),
    (r"收复", 2), (r"上攻", 2), (r"冲(击|关)?\s*\d+", 2), (r"冲\s*\d+", 2),
    (r"机会(确定性)?|总(是)?有机会|就有机会|也有机会", 1), (r"低开.{0,8}(总)?有机会", 2),
    (r"拯救市场", 3), (r"站回", 2), (r"承接(未破|住|良好)?", 1), (r"稳住|守稳", 1),
    (r"安全时间", 2), (r"后(2-3|两|三|3)?天(整体)?风险不大", 2),
    (r"有机会(再)?向(上|好)", 2), (r"向好", 2), (r"转好|变好", 2), (r"不悲观", 2),
    (r"慢牛|长牛", 2), (r"企稳回升", 2), (r"探底回升", 2), (r"中阳", 1),
    (r"企稳", 1), (r"回暖", 1), (r"修复", 1), (r"转强", 2), (r"走强", 2),
    (r"翻红", 1), (r"拉升", 1), (r"走高", 1), (r"上涨", 1), (r"向上", 1),
    (r"突破(确认|新高|买入点)?", 1), (r"站稳3800|站稳3900|站稳3897|站稳3927|站稳3922", 3),
    (r"增量", 1), (r"资金回流", 1), (r"机构(配置盘|回流|进场)", 2),
    (r"就是主线|仍是主线|重回主线", 3), (r"大阳线", 2), (r"砸不下(来|去)", 1),
    (r"大赚回血|回血", 1), (r"跌出黄金坑", 2), (r"利空出尽", 2),
    (r"二次冲顶|多次冲顶|(二次|多次)\/多次?冲顶|冲顶", 3), (r"大概率.{0,8}冲顶", 4),
    (r"不再纠结", 3), (r"交易(景气|AI).{0,8}(拉长|延长)", 2),
    (r"产业(升级|逻辑)(未停|仍在|继续)", 2), (r"中轨守住|守住.{0,6}(线|位)", 1),
    (r"大盘无忧|市场无忧", 4), (r"能(拉|翻)红就不错|能(拉|翻)红.{0,4}就不错", -3),
    (r"有肉就走|有肉就", -1), (r"内部结构转弱", -0.5), (r"最悲观\s*(状态)?(去)?\s*\d+", -0.5),
    (r"冲(上|到)\d+|冲上", 2),
    (r"坚决看空|坚定看空", -4), (r"熊市", -3), (r"退潮(期|周期)?", -3),
    (r"(美股|科技|接力)?三杀|三杀共振", -4), (r"二次探底", -3), (r"顶背离", -3),
    (r"破位(下跌|下破)?", -3), (r"失守", -3), (r"跳水", -3), (r"崩(盘|了|溃)", -3),
    (r"崩塌", -1), (r"恐慌(延续|大概率)?", -3), (r"普跌", -3), (r"跌停(潮|家数)?", -3),
    (r"续跌|继续跌", -3), (r"大跌|暴跌", -3), (r"下杀", -2), (r"杀跌", -2),
    (r"下探", -2), (r"深跌", -2), (r"高开低走", -2), (r"确认(进入|日线)?(二浪|调整)", -2),
    (r"破坏(短周期)?趋势|趋势(破坏|破坏确认)", -3), (r"没(有)?打开持续性", -3),
    (r"集体(调整|下跌|走弱|翻绿)", -2), (r"共振(下跌|调整)", -2), (r"被动(减仓|降仓)", -1),
    (r"集体(歇菜|萎缩)", -1), (r"行情难做|难做", -1), (r"打地鼠", -2), (r"狗(行情|的局面)?", -2),
    (r"看空", -2), (r"看跌", -2), (r"悲观", -2), (r"最悲观(?!\s*(状态)?(去)?\s*\d)", -2),
    (r"弱势", -2), (r"走弱", -2), (r"转弱", -2), (r"下跌", -1), (r"回落", -1),
    (r"低开", -1), (r"砸盘", -1), (r"阴线|中阴", -1), (r"下挫", -2), (r"低迷", -2),
    (r"逼近", -1), (r"接近尾声", -1), (r"情绪(冰点|崩塌|差)", -2),
    (r"赚钱效应差|赚钱效应(崩塌|没了)", -2), (r"恶劣|恶化", -2), (r"回踩", -0.5),
    (r"调整", -0.5), (r"回调", -0.5), (r"回撤", -0.5), (r"缩量", -0.5),
    (r"黑暗|艰难|煎熬", -1), (r"卖飞", -0.5), (r"被埋|接飞刀", -1),
    (r"利空|负面", -1), (r"压力|压制", -0.5), (r"承压", -1), (r"走低", -1),
]
# 中性信号词（命中 → 增加 NEUTRAL 倾向）
DIR_NEUTRAL = [
    "震荡", "分化", "轮动", "变盘", "博弈", "横盘", "跷跷板", "纠结", "混沌",
    "随机", "等待", "观望", "缩量震荡", "电风扇", "平衡", "僵持", "说不清",
    "说不准", "没方向", "无方向", "不确定", "不主观", "待确认", "待验证",
    "未确认", "尚未", "揭晓答案", "倒计时", "左侧寻底", "等落地", "等确认",
    "等催化", "等业绩", "等结果", "正负相抵",
]

NEGATE_PREFIX = re.compile(r"(不|没|未|无|别|不会|不可能|不是|无需|不用|少|难)([^。；！？，]{0,6})$")
CONDITION_MARKERS = ["如果", "若", "假如", "除非", "只要", "一旦", "才", "只有", "要不", "不然", "不充分", "才算", "才叫", "才做"]
PREDICTION_MARKERS = ["可能", "有望", "或成", "预计", "预期", "或将", "待", "等待", "看", "应", "需观察"]
SYSTEM_DESC_MARKERS = ["=", "模型", "框架", "体系", "定义", "要素", "规则", "方法", "原则", "理论"]
TURN_MARKERS = ["但", "不过", "然而", "只是", "可是", "唯独", "反而", "倒是"]


def _clause_score(sent):
    """单句方向分（含体系句/条件/预测/否定/转折处理）"""
    # 体系/教学/定义句 → 不计方向（"突破买点=放量中阳站上中期均线组"）
    if any(m in sent for m in SYSTEM_DESC_MARKERS):
        return 0.0, 0.0
    pos = neg = 0.0
    cond_hit = any(m in sent for m in CONDITION_MARKERS)
    pred_hit = any(m in sent for m in PREDICTION_MARKERS) and "大概率" not in sent
    turn = any(sent.startswith(m) for m in TURN_MARKERS)
    for pat, w in DIR_PATTERNS:
        # 恐慌低吸/低吸强势/低吸机会 = 低吸机会不是空头
        if w < 0 and pat == r"恐慌(延续|大概率)?" and any(k in sent for k in ("恐慌低吸", "低吸强势", "低吸机会", "低吸核心")):
            continue
        for m in re.finditer(pat, sent):
            start = m.start()
            prefix = sent[max(0, start - 8):start]
            # 否定检测：立场词前有否定词 → 反向减半
            if NEGATE_PREFIX.search(prefix):
                w = -w * 0.5
            mult = 1.0
            if cond_hit:
                mult = 0.0          # 条件句：未确认，不计方向
            elif pred_hit:
                mult = 0.5          # 预测句：弱化
            if turn:
                mult *= 1.3
            if w > 0:
                pos += w * mult
            else:
                neg += w * mult
    return pos, neg


def _parse_direction(text):
    clauses = _split_sentences(text)
    pos = neg = 0.0
    evidences = []
    for c in clauses:
        p, n = _clause_score(c)
        pos += p; neg += n
        if p > 0: evidences.append(f"多:{c[:60]}")
        if n < 0: evidences.append(f"空:{c[:60]}")
    neu = sum(1 for t in DIR_NEUTRAL if t in text)
    net = pos + neg

    # 特判 0：恐慌低吸/低吸强势 = 低吸机会不是空头 → 已在 _clause_score 内处理
    # 特判 1：变盘/胜负手/倒计时（未定状态）→ NEUTRAL
    if re.search(r"变盘|胜负手|倒计时|揭晓答案", text) and abs(net) < 12:
        direction = "NEUTRAL"
    # 特判 2：待确认/未确认/等待 ≥2 次（未确认）→ NEUTRAL
    elif len(re.findall(r"待确认|未确认|等待|待验证|尚未|说不清", text)) >= 2 and abs(net) < 7:
        direction = "NEUTRAL"
    # 特判 3：强条件句（"才是真正…信号/确认"）且方向不极端 → NEUTRAL
    elif re.search(r"才(是|算|叫|做).{0,12}(信号|确认|充分|到位)|才是真正", text) and abs(net) < 9:
        direction = "NEUTRAL"
    # 特判 4：随机/说不清主导 → NEUTRAL
    elif re.search(r"太随机|说不清|说不准|完全随机|无方向", text) and abs(net) < 9:
        direction = "NEUTRAL"
    # 特判 5：分化/跷跷板主导 或 "轮动行情"（结构市无方向）→ NEUTRAL
    elif (len(re.findall(r"分化|跷跷板", text)) >= 2 or re.search(r"轮动(行情|市|格局)", text)) and abs(net) < 7:
        direction = "NEUTRAL"
    # 特判 6：多空双强且接近（真矛盾，MV-3 不中和 → NEUTRAL）
    elif pos >= 3 and abs(neg) >= 3 and abs(net) <= 2:
        direction = "NEUTRAL"
    elif net >= 2:
        direction = "BULLISH"
    elif net <= -2:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    total = pos + abs(neg) + neu
    conf = min(1.0, abs(net) / max(total, 1))
    explain = f"dir净分={net:+.1f}(多{pos:+.1f}/空{neg:+.1f}/中{neu})→{direction}"
    return direction, evidences, round(conf, 3), explain


# ============================== Risk：市场环境风险（独立轴） ==============================
# 带权词表：(词, 权重)。权重正=高风险，负=降险。
RISK_WORDS = [
    # 强系统风险 +4
    ("普跌", 4), ("大跌", 4), ("暴跌", 4), ("恐慌", 4), ("崩盘", 4), ("崩溃", 4), ("跌停", 4),
    ("熔断", 4), ("三杀", 4), ("退潮", 4), ("熊市", 4), ("破位", 4), ("失守", 4),
    ("二次探底", 4), ("枯竭", 4), ("净流出", 3), ("资金撤退", 3), ("最大风险", 3),
    ("风险较大", 3), ("冰点", 3), ("核按钮", 3), ("离别钩", 3), ("负反馈", 3),
    ("被核", 3), ("炸板", 2), ("监管", 3), ("情绪崩塌", 3), ("赚钱效应差", 3),
    ("高开低走", 3), ("离谱", 4), ("下探", 2), ("急跌", 2), ("严重缩量", 2), ("狗", 3),
    ("行情差", 2), ("地量", 2), ("黑天鹅", 2), ("踩踏", 2), ("爆雷", 2),
    ("制裁", 2), ("禁令", 2), ("不确定性", 2), ("深水区", 2), ("离场", 1), ("崩塌", 1),
    ("利率", 3), ("加息", 3), ("长端利率", 3), ("美债", 2), ("通胀", 2), ("高估值", 1),
    ("崩", 2),
    # 中等风险 +1（常见行情描述词给 0.5，避免堆高）
    ("风险", 1), ("危险", 1), ("回撤", 1), ("弱势", 1), ("走弱", 1), ("低迷", 1),
    ("压力", 1), ("压制", 1), ("难做", 1), ("超买", 1), ("警惕", 1), ("谨慎", 1),
    ("套牢", 1), ("杀跌", 1), ("阴跌", 1), ("担忧", 1), ("试探", 1), ("波动", 1),
    ("下杀", 1), ("走差", 1), ("变差", 1), ("恶心", 1), ("煎熬", 1),
    ("回踩", 0.5), ("调整", 0.5), ("回调", 0.5), ("缩量", 0.5), ("分化", 0.5), ("分歧", 0.5),
    # 明确低风险表态 -2
    ("风险不大", -2), ("无忧", -2), ("没问题", -2), ("安全", -2), ("转好", -2),
    ("变好", -2), ("放心", -2), ("风险较小", -2), ("利空出尽", -2), ("天时转好", -2),
    ("修复转强", -2), ("安全时间", -2), ("大环境已变好", -2), ("稳", -1),
    ("没什么风险", -2), ("后三天风险不大", -2), ("后2-3天风险不大", -2), ("大盘无忧", -2),
]
RISK_DESCEND = [  # 降险/缓解词：把 HIGH 拉回 MEDIUM
    "未跌穿", "守住", "企稳", "未破", "翻红", "点刹", "非拐点", "托举",
    "承接", "支撑", "极强", "有支撑", "缓冲", "问题不大", "可钝化", "强趋势",
    "持股", "站稳", "好日子", "拉起", "大阳线", "探底回升", "未散", "大盘无忧",
    "迎接日线三浪", "三浪上涨", "回血", "大赚回血",
]

NEG_RISK_PREFIX = re.compile(r"(不|没|未|无|别|不会|不可能|无需|不用|少|难|非|反)([^。；！？，]{0,6})$")
NEG_RISK_SUFFIX = re.compile(r"^([^。；！？，]{0,6})(不|没|未|别|不会|不可能|无需|不用|算了)$")

def _parse_risk(text):
    low_spans = []
    l = 0.0
    for t, w in RISK_WORDS:
        if w < 0:
            for m in re.finditer(re.escape(t), text):
                low_spans.append((m.start(), m.end()))
                l += -w
    h = 0.0
    for t, w in RISK_WORDS:
        if w > 0:
            for m in re.finditer(re.escape(t), text):
                if any(s <= m.start() < e for s, e in low_spans):
                    continue   # "风险不大"内的"风险"不计高风险
                # "涨跌停"的"跌停"不计
                if t == "跌停" and text[max(0, m.start() - 1):m.start()] == "涨":
                    continue
                prefix = text[max(0, m.start() - 8):m.start()]
                suffix = text[m.end():m.end() + 8]
                if NEG_RISK_PREFIX.search(prefix) or NEG_RISK_SUFFIX.search(suffix):
                    continue   # "高开低走不可能" / "反制裁" / "行情差时不做" → 否定不计
                h += w
    desc = sum(1 for t in RISK_DESCEND if t in text)

    if l >= 8 and l > h:
        risk = "LOW"
    elif h >= 4 and h > l:
        risk = "HIGH" if not ((desc >= 2 and h < 10) or (desc >= 4 and h < 20)) else "MEDIUM"
    elif h >= 3 and l >= 3:
        risk = "MEDIUM"
    else:
        risk = "MEDIUM"
    ev = [f"{'高' if w>0 else '低'}:{t}" for t, w in RISK_WORDS if t in text][:6]
    conf = min(1.0, abs(h - l) / max(h + l, 1)) if h + l > 0 else 0.0
    return risk, ev, round(conf, 3), f"risk高{h:.0f}/低{l:.0f}/降险{desc}→{risk}"


# ============================== Position Bias：操作倾向（独立轴） ==============================
BIAS = [
    ("AGGRESSIVE", [
        (r"满仓", 2), (r"重仓", 2), (r"大仓位", 2), (r"全仓", 2), (r"all\s*in", 2),
        (r"融资", 1), (r"打地鼠", 1), (r"新建仓(多只)?", 2), (r"主攻", 2),
        (r"坚决看多|坚定看多|坚决做多", 2), (r"盘面有信心|有信心|信号意义", 2),
        (r"坚守(国产)?(算力|科技)", 3), (r"全面回暖|全面进攻", 2), (r"后面几天安全时间", 3), (r"大干|猛干|全力", 1),
        (r"梭哈|梭", 1), (r"上大仓位", 2), (r"大仓位持股", 2), (r"积极做多", 2),
        (r"胜算\d+分(大仓位|半仓以上)?", 2), (r"赌.{0,6}(板块|方向|加强)|豪赌", 2),
    ]),
    ("ADD_ON_DIP", [
        (r"低吸(为主|布局|建仓|核心|强势品种|恐慌低吸|低吸高抛)", 2),
        (r"低吃", 2), (r"逢低", 2), (r"回踩(均线)?(可考虑)?低吸", 2),
        (r"回调(里)?买|回调可加", 2), (r"分批买", 2), (r"越跌越买", 2), (r"恐慌低吸", 2),
        (r"低点买|低接", 2), (r"尾盘拿先手", 2), (r"拿底仓", 2), (r"低吸高抛", 2),
        (r"回踩.*(加仓|确认加仓)", 2), (r"底部加仓|低位(加仓|承接)", 2),
        (r"回踩.*买", 1), (r"补仓", 1), (r"回补", 1), (r"加仓", 1), (r"可加(一|部分)?", 1),
        (r"调整(2天内|内)?修复上冲", 2), (r"修复上冲", 2), (r"再(可以|能)买", 1),
        (r"逢低加", 2), (r"低吸做T", 2), (r"拿回", 1), (r"低吸", 1),
        (r"低吸窗口|最佳低吸窗口", 2), (r"补点|补一下|补仓窗口", 1),
    ]),
    ("HOLD", [
        (r"躺平", 2), (r"持有不动", 3), (r"继续持有", 2), (r"持股(躺平)?", 2),
        (r"拿稳", 2), (r"坚持持有", 2), (r"安心持有", 2), (r"适合持仓", 2),
        (r"没动", 3), (r"留.{0,4}(逆势|相对逆势)", 2), (r"分歧(时)?不卖", 3),
        (r"持有", 1), (r"持仓", 1), (r"格局", 1), (r"拿住", 1), (r"不动", 1),
        (r"不卖", 1), (r"持有为主", 1), (r"持股观察", 1), (r"留着", 1),
    ]),
    ("REDUCE", [
        (r"清仓", 2), (r"仓位回归0", 2), (r"全卖", 2), (r"落袋为安", 2),
        (r"止盈(离场)?", 2), (r"开盘(清仓|卖出)", 2), (r"降低风险敞口|降风险敞口", 3),
        (r"兑现(利润|部分)?", 1), (r"减仓", 1), (r"卖出", 1), (r"离场", 1), (r"减半", 1),
        (r"减0.5成", 1), (r"减1/3|减1/2|减2成", 1), (r"出局", 1), (r"止损", 1),
        (r"卖掉", 1), (r"抛出", 1), (r"降低仓位", 2), (r"减掉", 1), (r"撤仓", 1),
    ]),
    ("CONTROL_POSITION", [
        (r"严格控制仓位", 4), (r"仓位控制", 3), (r"均衡配置", 3), (r"轻仓参考", 3),
        (r"仓位卡在", 2), (r"仓位上限", 2), (r"小仓位(试错)?", 2), (r"0.5成仓(试探)?", 2),
        (r"轻仓", 2), (r"收缩战线", 2), (r"多分仓|分仓", 2), (r"不追高", 2),
        (r"控制(开仓|节奏|欲望)", 2), (r"仓位5成(中枢)?", 3), (r"严格控仓|严控", 2),
        (r"保护本金", 2), (r"行情(好|差)时(多|不)做", 2), (r"不轻易回补", 2),
        (r"控制仓位", 2), (r"仓位小", 2), (r"底仓不丢|聚焦核心", 2), (r"压制位不追", 1),
        (r"仓位(管理)", 1), (r"谨慎", 1), (r"慢慢来", 1), (r"试探", 1), (r"控节奏|控仓", 1),
        (r"仓位1成|一成", 1), (r"底仓", 1), (r"兑现部分", 1), (r"均衡", 1),
        (r"减出|平出|观望", 1), (r"能砸就砸", 1), (r"控制好仓位", 2), (r"参考仓位", 1),
        (r"控仓位", 1), (r"低吸1成|1成参考", 2),
    ]),
    ("WAIT", [
        (r"空仓(等待|观望)?", 2), (r"观望(为主)?", 2), (r"等待(确定性)?节点", 2),
        (r"等(周五|今晚|落地|结果|确认|业绩|讲话|揭晓|答案|消息|止跌)", 2),
        (r"等.{0,10}(爆量|极致|波段低点)", 2), (r"等.{0,12}(触发|出现|时候)", 2), (r"会空仓才是祖师爷", 2), (r"休息(也没毛病)?", 2),
        (r"调整节奏", 2), (r"防守思维", 2), (r"不急于|不急", 1), (r"先不动", 1),
        (r"再等等|先等等", 1), (r"静观", 1), (r"按兵不动", 1), (r"等(行情|机会|时候)", 1),
        (r"左侧寻底", 1), (r"等尾盘|等次日|等(尾盘|次日)机会", 2), (r"等待", 1),
        (r"触发再出|低吸场景触发", 2), (r"揭晓答案", 1), (r"倒计时", 1), (r"再出", 1), (r"观察", 1),
    ]),
]

def _parse_bias(text):
    # 条件句：未确认的操作意图弱化
    clauses = _split_sentences(text)
    scores = {name: 0.0 for name, _ in BIAS}
    evs = {name: [] for name, _ in BIAS}
    for c in clauses:
        # 体系/教学句跳过
        if any(m in c for m in SYSTEM_DESC_MARKERS):
            continue
        cond = any(m in c for m in CONDITION_MARKERS)
        mult = 0.3 if cond else 1.0
        hold_neg = any(k in c for k in ("最头疼", "不想", "不持股", "别持股", "不愿持有"))
        for name, pats in BIAS:
            for pat, w in pats:
                for m in re.finditer(pat, c):
                    ww = w * mult
                    if name == "HOLD" and hold_neg:
                        ww = 0.0   # "持股是当下最头疼的情况" → 非持有
                    # 操作词否定："暂不加仓"/"先不动买" → 不算操作意图
                    if ww and name != "CONTROL_POSITION" and name != "WAIT":
                        pfx = c[max(0, m.start() - 6):m.start()]
                        if re.search(r"(暂不|先不|不要|别|不用|不必|不肯)", pfx):
                            ww = 0.0
                    if ww == 0:
                        continue
                    scores[name] += ww
                    s = max(0, m.start() - 6)
                    evs[name].append(f"{pat}:{c[s:m.end()+8]}")
    total = sum(scores.values())
    if total == 0:
        return "UNKNOWN", [], 0.0, "bias无信号→UNKNOWN"
    top = max(scores, key=scores.get)
    ties = [k for k, v in scores.items() if v == scores[top]]
    bias = "CONTROL_POSITION" if len(ties) > 1 else top
    conf = scores[top] / max(total, 1)
    explain = "bias：" + ", ".join(f"{k}={v:.0f}" for k, v in sorted(scores.items(), key=lambda kv: -kv[1]) if v > 0)
    return bias, evs[top][:4], round(conf, 3), explain


# ============================== 主入口 ==============================
def parse_market_view(raw_text):
    text = (raw_text or "").strip()
    if not text:
        return _unknown_result("空输入→UNKNOWN")

    # ---- 无观点 ----
    for p in NO_VIEW_PATTERNS:
        if p in text:
            return _unknown_result(f"无观点信号「{p}」→UNKNOWN (MV-4)")

    # ---- scope（句子级） ----
    sents = _split_sentences(text)
    mkt_sents = [s for s in sents if _sentence_market_score(s) > 0]
    stk_sents = [s for s in sents if _sentence_stock_score(s) >= 1]
    if not mkt_sents and not stk_sents:
        scope = "UNKNOWN"
    elif not mkt_sents:
        scope = "STOCK_ONLY"
    elif stk_sents:
        scope = "MIXED"
    else:
        scope = "MARKET"

    if scope in ("STOCK_ONLY", "UNKNOWN"):
        return _unknown_result(
            f"view_scope={scope}（市场句{len(mkt_sents)}/个股句{len(stk_sents)}）→三轴UNKNOWN，排除 (MV-4)")

    # ---- 三轴独立 ----
    direction, dir_ev, dir_conf, dir_exp = _parse_direction(text)
    risk, risk_ev, risk_conf, risk_exp = _parse_risk(text)
    bias, bias_ev, bias_conf, bias_exp = _parse_bias(text)

    return {
        "view_scope": scope,
        "market_direction": direction,
        "market_score": DIRECTION_SCORE_MAP[direction],
        "risk_level": risk,
        "position_bias": bias,
        "direction_evidence": dir_ev[:4],
        "risk_evidence": risk_ev,
        "bias_evidence": bias_ev,
        "confidence": {"direction": dir_conf, "risk": risk_conf, "bias": bias_conf},
        "exclude_from_market_consensus": False,
        "explain": f"scope={scope}(市句{len(mkt_sents)}/股句{len(stk_sents)}); {dir_exp}; {risk_exp}; {bias_exp}",
    }


def _unknown_result(reason):
    scope = "UNKNOWN"
    if "STOCK_ONLY" in reason:
        scope = "STOCK_ONLY"
    return {
        "view_scope": scope, "market_direction": "UNKNOWN", "market_score": None,
        "risk_level": "UNKNOWN", "position_bias": "UNKNOWN",
        "direction_evidence": [], "risk_evidence": [], "bias_evidence": [],
        "confidence": {"direction": 0.0, "risk": 0.0, "bias": 0.0},
        "exclude_from_market_consensus": True,
        "explain": reason,
    }


def load_daily_view_text(db_path, analyst_id, view_date):
    import sqlite3
    db = sqlite3.connect(db_path)
    rows = db.execute(
        "SELECT view_type, content FROM analyst_daily_views WHERE analyst_id=? AND view_date=? ORDER BY view_type",
        (analyst_id, view_date)).fetchall()
    db.close()
    if not rows:
        return None
    parts = [f"[{vt}] {c}" for vt, c in rows if c]
    return " ￭SEP￭ ".join(parts) if parts else None


if __name__ == "__main__":
    import json, sys
    if len(sys.argv) >= 2:
        print(json.dumps(parse_market_view(sys.argv[1]), ensure_ascii=False, indent=2))
    else:
        db = "/home/windfall/workspace/research-archive-platform/data/analyst_consensus.db"
        a, d = "gelan", "2026-08-26"
        raw = load_daily_view_text(db, a, d)
        print(f"=== {a} {d} ===")
        print(json.dumps(parse_market_view(raw), ensure_ascii=False, indent=2))
