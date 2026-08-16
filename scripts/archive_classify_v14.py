#!/usr/bin/env python3
"""资讯研究档案库 v1.4 - 分类器（主类型互斥 8 类 + 多维度独立）
数据模型：1 个主类型（content_type）+ 4 个独立维度（来源/机构/行业主题/交易价值）
content_type 互斥：research_report | institution_view | research_activity
                  | news | announcement | market | digest | attachment
primary_category 保留旧值兼容 UI：research/news/announcement/market/image/empty_invalid
2026-08-12
"""
import json, re, sqlite3, sys
from datetime import datetime

sys.path.insert(0, "/root/scripts")
from institution_map import normalize_institution

DB = "/root/workspace/research_archive.db"
CLASSIFIER_VERSION = "telegram-info-classifier-v1.4"

# ============ 机构名单（含团队拆解用） ============
INSTITUTIONS = ['天风证券','国金证券','国泰海通','华鑫证券','中金公司','中信证券','广发证券','华泰证券',
    '申万宏源','东吴证券','民生证券','招商证券','兴业证券','海通证券','银河证券','平安证券','开源证券',
    '华福证券','国投证券','浙商证券','长江证券','光大证券','方正证券','国联证券','中泰证券','华西证券',
    '高盛','摩根大通','瑞银','野村','花旗','中信建投','东方证券','国信证券','德邦证券','华创证券','山西证券',
    '财通证券','西部证券','东北证券','中邮证券','首创证券','国元证券','西南证券','国盛证券','信达证券',
    '天风','国金','浙商','长江','华泰','中金','中信','广发','申万','东吴','民生','招商','兴业','海通','银河',
    '平安','开源','华福','国投','光大','方正','国联','中泰','华西','国信','德邦','华创','财通','西部','东北',
    '中邮','国元','西南','东方','国盛','信达','国海','华安','中银','国联','中原','首创','长城','华龙','万联']

# ============ 8 主类型判定词 ============
# research_report：正式深度报告
REPORT_STRONG = ['深度报告', '行业报告', '公司报告', '首次覆盖', '深度：', '专题报告', '深度研究',
                 '正式研报', '深度', '年度策略', '半年度策略']
# research_activity：调研/电话会/纪要
ACTIVITY_STRONG = ['电话会', '电话会议', '业绩会', '业绩说明会', '调研纪要', '交流纪要', '路演',
                   '调研反馈', '会议纪要', '问答纪要', '调研', '交流反馈', '专家交流', '一线反馈',
                   '产业反馈', '行业反馈']
# institution_view：券商即时观点
VIEW_WORDS = ['点评', '观点更新', '速评', '快评', '事件点评', '涨停点评', '跟踪', '更新', '周观察',
              '观点', '解读', '复盘', '前瞻', '展望', '梳理', '推荐', '关注']
# digest：汇总/复盘/晨报/晚报
DIGEST_WORDS = ['隔夜', '盘前', '晨报', '晚报', '早报', '要闻汇总', '十大消息', '今日看点', '盘面综述',
                '收盘综述', '行情回顾', '一周回顾', '复盘', '晚间速递', '资讯汇总', '午间速递', '要闻']
# announcement 严格：正式披露来源
ANNOUNCE_SOURCE = ['上交所', '深交所', '北交所', '港交所', '巨潮资讯', '上市公司公告', '公司正式公告',
                   '董事会公告', '交易所公告', '公告编号', '信息披露', '公司公告']
ANNOUNCE_ACTION = ['定增', '回购', '增持', '减持', '停牌', '复牌', '问询函', '监管', '处罚', '业绩预告',
                   '重大合同', '中标', '立案', '风险警示', '质押', '解禁', '重组', '收购', '分红', '转增',
                   '净利润', '营收', '半年报', '年报', '财报', '营业收入', '净利润同比']
ANNOUNCE_NEGATIVE = ['据悉', '网传', '传闻', '公司回应', '电话获悉', '市场消息', '知情人士', '微信群',
                     '调研反馈', '复盘', '专家称', '据说', '或', '可能']
# market 行情强词
MARKET_STRONG = ['指数期货', '临时停牌', '熔断', '期货', '收盘', '涨跌幅', '成交额', '北向', '板块表现',
                 '沪指', '深成指', '创业板指', '大盘', '两市', '涨跌家数', '跌停', '涨停家数']
# news 媒体源
NEWS_SRC = ['财联社', '央视', '新华社', '路透', '彭博', '华尔街见闻', '快讯', '新浪财经', '证券时报',
            '上海证券报', '中国证券报', '第一财经', '界面', '每经', '东方财富']

# ============ 二级主题（theme）与一级行业（industry） ============
THEMES = {
    'AI算力': ['算力', '智算', 'GPU', 'AI服务器', '数据中心', 'AIDC', '云服务', '大模型'],
    '光模块/CPO': ['光模块', 'CPO', '硅光', '1.6T', '800G', '光通信'],
    'PCB/载板': ['PCB', '载板', 'CCL', '覆铜板', 'mSAP', 'ABF'],
    '存储': ['存储', 'DRAM', 'NAND', 'HBM', '闪存', '内存', '模组'],
    '半导体设备': ['半导体设备', '光刻', '刻蚀', '薄膜', '清洗设备', '分选机'],
    '半导体材料': ['硅片', '电子特气', '光刻胶', '靶材', 'CMP'],
    '功率半导体': ['碳化硅', 'SiC', '氮化镓', 'GaN', 'IGBT', '功率器件'],
    '机器人': ['人形机器人', '机器人', '减速器', '丝杠', '宇树', '灵巧手', '执行器'],
    '新能源车': ['新能源汽车', '锂电', '电池', '比亚迪', '宁德', '电驱'],
    '光伏': ['光伏', '硅料', '组件', '逆变器', 'TOPCon', 'HJT', '钙钛矿'],
    '储能': ['储能', '大储', '户储', '工商储'],
    '医药/CXO': ['创新药', 'CXO', 'CRO', 'CDMO', '医药', '药明', '临床'],
    '军工': ['军工', '国防', '导弹', '军贸', '航天'],
    '有色/稀土': ['稀土', '铜箔', '磷化铟', '金属', '铝', '氧化铝', '锂矿', '黄金'],
    '电力/电网': ['电力', '电网', '特高压', '虚拟电厂', '核电'],
    '深海油气/FPSO': ['FPSO', '深海油气', '海洋工程', 'SBM'],
    '宏观/政策': ['央行', '利率', 'CPI', '非农', '政策', '财政', '降准', 'LPR', '美联储'],
}
INDUSTRY_MAP = {  # theme → 一级行业
    'AI算力': '计算机', '光模块/CPO': '通信', 'PCB/载板': '电子', '存储': '电子',
    '半导体设备': '电子', '半导体材料': '电子', '功率半导体': '电子', '机器人': '机械',
    '新能源车': '汽车', '光伏': '电力设备', '储能': '电力设备', '医药/CXO': '医药',
    '军工': '国防军工', '有色/稀土': '有色金属', '电力/电网': '电力设备',
    '深海油气/FPSO': '石油石化', '宏观/政策': '宏观',
}

# 对话/寒暄
CHAT_PATTERNS = [
    r'^[^：:]{1,12}?(提问|请教|问一下|想问|问冷|冷局您好|冷局，|请冷局)[：:]',
    r'(谢谢|感谢|辛苦了|太厉害|崇拜|受益匪浅|已吸收|多多分享|希望.*分享|授课)',
]
CHAT_WORDS = ['谢谢', '感谢', '辛苦', '厉害', '崇拜', '吸收', '授课', '分享', '宝贵', '认可']


def is_chat(text):
    t = (text or "").strip()
    if not t:
        return False
    for pat in CHAT_PATTERNS:
        if re.search(pat, t[:120]):
            return True
    return sum(1 for w in CHAT_WORDS if w in t[:120]) >= 2


# 机构前缀匹配时排除的公司名（避免 长江存储→长江证券 误判）
INST_NAME_EXCLUDE = ['长江存储', '长江电力', '长江传媒', '长江健康', '中信重工', '中信特钢', '中信银行',
                     '中信出版', '中信海直', '中金岭南', '中金黄金', '中金环境', '广发银行', '广发基金',
                     '招商银行', '招商蛇口', '招商轮船', '招商积余', '兴业银行', '兴业科技', '兴业矿业',
                     '华泰保险', '华泰汽车', '平安银行', '平安好医生', '国金证券资管', '东方财富', '东方园林',
                     '东方雨虹', '东方明珠', '光大银行', '光大嘉宝', '民生银行', '民生控股', '银河证券资管',
                     '天风天睿', '国联水产', '国联股份', '方正证券资管', '东吴证券资管', '海通国际']


def parse_inst(text):
    """解析【天风通信】→ (天风证券, 通信)；【国金证券】→ (国金证券, '')；无【】时识别正文开头的机构名
    优先【】，避免 [礼物]/[红包] 等 Telegram 标记被误当机构"""
    t0 = (text or "").strip()
    m = re.search(r'【([^】]+)】', t0)  # 优先全角【】
    if not m:
        m = re.search(r'\[([^\]\[\r\n]{2,8})\]', t0)  # 半角 [] 但限定 2-8 字符且非 礼物/红包/图片 等
        if m and m.group(1) in ('礼物', '红包', '图片', '视频', '文件', '表情'):
            m = None
    if m:
        raw = m.group(1).strip()
        if not raw:
            return "", ""
        # 精确命中机构名 → 无团队
        for inst in sorted(INSTITUTIONS, key=len, reverse=True):
            if raw == inst:
                return normalize_institution(inst), ""
        # 短简称前缀拆团队（如 天风通信/浙商计算机/长江电新）：
        # 先找【】内能匹配的机构前缀，剩余部分即团队
        best = None
        for inst in sorted(INSTITUTIONS, key=len, reverse=True):
            if len(inst) <= 4 and raw.startswith(inst) and len(raw) > len(inst):
                best = (inst, raw[len(inst):].strip())
                break
        if best:
            return normalize_institution(best[0]), best[1]
        # 整体归一（如 天风证券）
        norm = normalize_institution(raw)
        if norm and norm != raw:
            return norm, ""
        return "", ""
    # 无【】：检查正文开头（#机构/机构名：/机构名对…）
    t = (text or "").strip()
    t_head = re.sub(r'^[\s#\*\-·•\[\]【】]+', '', t)[:24]
    if any(ex in t_head for ex in INST_NAME_EXCLUDE):
        return "", ""
    for inst in sorted(INSTITUTIONS, key=len, reverse=True):
        if len(inst) >= 2 and t_head.startswith(inst):
            team = ""
            rest = t_head[len(inst):]
            # 团队：紧跟的 2-4 字（如 #长江宏观 → 宏观）
            m2 = re.match(r'^([\u4e00-\u9fa5]{2,4}?)[：:，,。\s]', rest)
            if m2 and m2.group(1) not in ('对', '称', '表示', '认为', '预计', '发布', '指出'):
                team = m2.group(1)
            return normalize_institution(inst), team
    return "", ""


def extract_themes_industry(text):
    themes = []
    for name, kws in THEMES.items():
        if any(k in (text or "") for k in kws):
            themes.append(name)
    if not themes:
        return [], ""
    industry = INDUSTRY_MAP.get(themes[0], "")
    return themes, industry


def detect_role(content_type, content_subtype, text, inst, mtype):
    """消息角色（v1.4.2 来源聚合）：
    original=机构/媒体/公告原始内容 | forward=转发转述 | summary=摘要汇总
    commentary=二次解读 | attachment=附件图片"""
    if mtype == "image" or not (text or "").strip():
        return "attachment"
    t = text or ""
    if content_type == "digest":
        return "summary"
    if content_type == "attachment":
        return "attachment"
    if inst:
        return "original"  # 机构署名 → 原始研究内容（即使经 fs2tg 采集）
    if content_type in ("announcement", "research_activity"):
        return "original"
    if any(k in t for k in NEWS_SRC):
        return "original"  # 媒体原始快讯（财联社等）
    if any(k in t for k in ['解读', '点评', '怎么看', '分析认为', '我们看法']):
        return "commentary"
    return "forward"  # 无署名社群转述/转发


def classify(mtype, text, source_topic=""):
    """返回 dict：主类型判定 + 维度字段（source_topic 用于红宝书等来源特判）"""
    t = (text or "").strip()
    # ── 1. attachment：图片/文件/无正文 ──
    if mtype == "image" and len(t) < 5:
        return dict(content_type="attachment", content_subtype="图片研报", tags=["图片/附件"],
                    sentiment="unknown", conf=0.6, review=1,
                    reason="图片待Vision分析", vision="pending",
                    inst="", team="", themes=[], industry="", role="attachment",
                    value=0, original_source="", ingest_source="")
    if len(t) < 5:
        return dict(content_type="attachment", content_subtype="文件/附件", tags=["附件"],
                    sentiment="unknown", conf=0.6, review=1, reason="无正文，需人工确认",
                    vision="", inst="", team="", themes=[], industry="", role="attachment",
                    value=0, original_source="", ingest_source="")
    # ── 2. empty_invalid：对话/寒暄 ──
    if is_chat(t):
        return dict(content_type="empty_invalid", content_subtype="对话/寒暄", tags=["对话/寒暄"],
                    sentiment="unknown", conf=0.9, review=0, reason="",
                    vision="", inst="", team="", themes=[], industry="", role="chat",
                    value=0, original_source="", ingest_source="")

    inst, team = parse_inst(t)
    themes, industry = extract_themes_industry(t)
    role = "attachment" if mtype == "image" else "body"

    # ── 3. research_activity 优先（电话会/纪要/交流反馈，无论有无机构前缀） ──
    if any(k in t for k in ACTIVITY_STRONG):
        sub = "电话会" if any(k in t for k in ['电话会', '电话会议']) else \
              ("业绩会" if any(k in t for k in ['业绩会', '业绩说明会']) else "调研/纪要")
        return dict(content_type="research_activity", content_subtype=sub, tags=["调研/纪要"] + ([inst] if inst else []),
                    sentiment=_sentiment(t), conf=0.9, review=0, reason="",
                    vision="", inst=inst, team=team, themes=themes, industry=industry,
                    role=role, value=_value(t, inst, themes, role), original_source=inst, ingest_source="")

    # ── 3.4 红宝书：VIP1群112604 盘后复盘（来源特判，先于机构分支） ──
    # 来源名兼容历史"红宝书"与现行"红宝书热点"
    if source_topic and source_topic.startswith("红宝书"):
        sub = "收盘复盘"
        return dict(content_type="digest", content_subtype=sub, tags=["红宝书", "汇总/复盘"],
                    sentiment="neutral", conf=0.9, review=0, reason="红宝书盘后复盘来源",
                    vision="", inst="", team=team, themes=themes, industry=industry,
                    role="summary", value=min(_value(t, "", themes, role), 70),
                    original_source="", ingest_source="")

    # ── 3.5 digest 汇总/复盘/快报（无论有无机构前缀，先于机构分支：
    #        高盛中国午间快报/晨报/晚报/隔夜/复盘 都是汇总性质） ──
    if any(k in t for k in DIGEST_WORDS):
        sub = "隔夜要闻" if '隔夜' in t else ("盘前梳理" if '盘前' in t else
              ("收盘复盘" if any(k in t for k in ['复盘', '收盘']) else "资讯汇总"))
        return dict(content_type="digest", content_subtype=sub, tags=["汇总/复盘"] + ([inst] if inst else []),
                    sentiment="neutral", conf=0.85, review=0, reason="",
                    vision="", inst=inst, team=team, themes=themes, industry=industry,
                    role=role, value=min(_value(t, "", themes, role), 55), original_source="", ingest_source="")

    # ── 4. 机构前缀优先（券商观点/研报） ──
    if inst:
        if any(k in t for k in REPORT_STRONG):
            sub = "行业深度" if any(k in t for k in ['行业', '板块', '赛道']) else \
                  ("宏观策略" if any(k in t for k in ['宏观', '策略', '政策', '利率']) else "公司深度")
            return dict(content_type="research_report", content_subtype=sub, tags=["正式研报", inst],
                        sentiment=_sentiment(t), conf=0.92, review=0, reason="",
                        vision="", inst=inst, team=team, themes=themes, industry=industry,
                        role=role, value=_value(t, inst, themes, role), original_source=inst, ingest_source="")
        # 默认机构 → 即时观点/点评
        sub = "宏观观点" if any(k in t for k in ['宏观', '策略', '政策']) else \
              ("行业观点" if any(k in t for k in ['行业', '板块', '景气', '供需']) else "公司点评")
        return dict(content_type="institution_view", content_subtype=sub, tags=["券商观点", inst],
                    sentiment=_sentiment(t), conf=0.88, review=0, reason="",
                    vision="", inst=inst, team=team, themes=themes, industry=industry,
                    role=role, value=_value(t, inst, themes, role), original_source=inst, ingest_source="")

    # ── 5. announcement 严格收紧：正式披露来源 + 无传闻词 ──
    # 机构观点压制：含 更新/点评/观点/买入/目标价/展望/深度 等观点词且无【机构】时，
    # 即使正文提到 分红/回购/增持 等动作词，也优先归机构观点（避免 金达威更新/高股息荐股 误归公告）
    VIEW_OVERRIDE = ['更新', '点评', '观点', '买入', '目标价', '展望', '深度', '交流', '纪要', '速评',
                     '快评', '调研', '推荐', '关注', '跟踪', '周观察', '复盘', '逻辑', '弹性', '配置']
    view_hits = [k for k in VIEW_OVERRIDE if k in t]
    has_source = any(k in t for k in ANNOUNCE_SOURCE)
    has_action = any(k in t for k in ANNOUNCE_ACTION)
    neg_hits = [k for k in ANNOUNCE_NEGATIVE if k in t]
    # 观点类消息（无机构但像研报/点评）→ 即使有公告动作词也优先 institution_view
    # 荐股词（买入/推荐/目标价/配置/标的）强压制公告判定
    PICK_WORDS = ['买入', '推荐', '目标价', '配置', '标的', '加仓', '增持评级', '现价']
    pick_hits = [k for k in PICK_WORDS if k in t]
    if (len(view_hits) >= 2 or pick_hits) and not has_source and \
       not re.search(r'[\u4e00-\u9fa5]{2,6}公司公告|[\u4e00-\u9fa5]{2,6}公告[，。]|公告称|公告，', t):
        return dict(content_type="institution_view", content_subtype="公司点评",
                    tags=["观点/梳理"], sentiment=_sentiment(t), conf=0.75, review=0, reason="",
                    vision="", inst="", team="", themes=themes, industry=industry,
                    role=role, value=_value(t, "", themes, role), original_source="", ingest_source="")
    if has_action and (has_source or ('公告' in t and not neg_hits)):
        if neg_hits:
            return dict(content_type="news", content_subtype="传闻求证", tags=["传闻/求证"] + neg_hits,
                        sentiment="neutral", conf=0.7, review=1, reason="传闻真实性待验证",
                        vision="", inst="", team="", themes=themes, industry=industry,
                        role=role, value=min(_value(t, "", themes, role), 60), original_source="", ingest_source="")
        sub = "风险公告" if any(k in t for k in ['处罚', '立案', '问询', '风险警示']) else \
              ("业绩预告" if any(k in t for k in ['业绩预告']) else "公司事件")
        return dict(content_type="announcement", content_subtype=sub, tags=["正式公告"],
                    sentiment="neutral", conf=0.9, review=0, reason="",
                    vision="", inst="", team="", themes=themes, industry=industry,
                    role=role, value=_value(t, "", themes, role), original_source=_source_of(t), ingest_source="")

    # ── 5. market 行情强词 ──
    if any(k in t for k in MARKET_STRONG):
        sub = "指数行情" if any(k in t for k in ['沪指', '深成指', '创业板指', '大盘', '指数']) else \
              ("期货商品" if any(k in t for k in ['期货', '熔断']) else "板块行情")
        return dict(content_type="market", content_subtype=sub, tags=["行情"],
                    sentiment="neutral", conf=0.85, review=0, reason="",
                    vision="", inst="", team="", themes=themes, industry=industry,
                    role=role, value=_value(t, "", themes, role), original_source="", ingest_source="")

    # ── 6. news 媒体源 ──
    src = [k for k in NEWS_SRC if k in t]
    if src:
        sub = "财经快讯"
        if any(k in t for k in ['网传', '据悉', '传闻', '消息人士']):
            sub = "传闻求证"
            return dict(content_type="news", content_subtype=sub, tags=src + ["传闻"],
                        sentiment="neutral", conf=0.7, review=1, reason="传闻真实性待验证",
                        vision="", inst="", team="", themes=themes, industry=industry,
                        role=role, value=min(_value(t, "", themes, role), 60), original_source=src[0], ingest_source="")
        return dict(content_type="news", content_subtype=sub, tags=src,
                    sentiment=_sentiment(t), conf=0.88, review=0, reason="",
                    vision="", inst="", team="", themes=themes, industry=industry,
                    role=role, value=_value(t, "", themes, role), original_source=src[0], ingest_source="")

    # ── 8. 宏观数据新闻（CPI/PPI/PMI/非农等） ──
    if re.search(r'(CPI|PPI|PMI|非农|失业率|GDP|零售销售|社融|M2|LPR|MLF|存款准备金)', t) and \
       re.search(r'(年率|预期|前值|公布|录得|同比|环比|%|百分点)', t):
        return dict(content_type="news", content_subtype="宏观数据", tags=["宏观数据"],
                    sentiment=_sentiment(t), conf=0.82, review=0, reason="",
                    vision="", inst="", team="", themes=themes, industry=industry,
                    role=role, value=_value(t, "", themes, role), original_source="", ingest_source="")

    # ── 9. 弱研究信号（无机构但像观点/产业） ──
    weak = [k for k in VIEW_WORDS if k in t]
    strong_research = [k for k in REPORT_STRONG if k in t]
    if strong_research or len(weak) >= 2 or ('观点' in t and len(t) > 40):
        return dict(content_type="institution_view", content_subtype="行业观点",
                    tags=["观点/梳理"], sentiment=_sentiment(t), conf=0.7, review=0, reason="",
                    vision="", inst="", team="", themes=themes, industry=industry,
                    role=role, value=_value(t, "", themes, role), original_source="", ingest_source="")

    # ── 10. 公司负面/异动新闻（欧菲光遭举报等） ──
    neg_mark = re.search(r'(遭|被指|被举报|被立案|被处罚|爆雷|暴雷|退市|闪崩|跌停|大跌|利空)', t)
    comp_mark = re.search(r'[\u4e00-\u9fa5]{2,6}(股份|科技|电子|智能|生物|医药|能源|材料|通信|重工|汽车|证券|光电|半导体|存储|精密|新材)', t) or \
                re.search(r'^[\u4e00-\u9fa5]{2,6}(?:遭|被|爆|闪|跌|大跌)', t)
    if neg_mark and comp_mark:
        return dict(content_type="news", content_subtype="公司新闻", tags=["公司负面"],
                    sentiment="negative", conf=0.75, review=0, reason="",
                    vision="", inst="", team="", themes=themes, industry=industry,
                    role=role, value=min(_value(t, "", themes, role), 65), original_source="", ingest_source="")

    # ── 11. 传闻/其他 → news ──
    if any(k in t for k in ['网传', '据悉', '传闻', '消息人士', '知情人士']):
        return dict(content_type="news", content_subtype="传闻求证", tags=["传闻"],
                    sentiment="neutral", conf=0.6, review=1, reason="传闻真实性待验证",
                    vision="", inst="", team="", themes=themes, industry=industry,
                    role=role, value=min(_value(t, "", themes, role), 55), original_source="", ingest_source="")
    # 有实体/主题的产业新闻 → 黄标（0.65-0.85 不进人工复核）
    if themes or re.search(r'[\u4e00-\u9fa5]{2,6}(股份|科技|电子|智能|生物|医药|能源|材料|通信|重工|汽车)', t):
        return dict(content_type="news", content_subtype="产业新闻", tags=["社群转述"],
                    sentiment="neutral", conf=0.68, review=0, reason="",
                    vision="", inst="", team="", themes=themes, industry=industry,
                    role=role, value=_value(t, "", themes, role), original_source="", ingest_source="")
    return dict(content_type="news", content_subtype="产业新闻", tags=["社群转述"],
                sentiment="neutral", conf=0.55, review=1, reason="分类置信度低，无明确来源证据",
                vision="", inst="", team="", themes=themes, industry=industry,
                role=role, value=_value(t, "", themes, role), original_source="", ingest_source="")


def _source_of(t):
    for s in ANNOUNCE_SOURCE:
        if s in t:
            return s
    return ""


def _sentiment(t):
    if any(k in t for k in ['超预期', '高景气', '增持', '买入', '拐点', '涨价', '大涨', '受益']):
        return "positive"
    if any(k in t for k in ['风险', '处罚', '立案', '亏损', '下跌', '减持', '利空']):
        return "negative"
    return "neutral"


def _value(t, inst, themes, role):
    """research_value 六维：可靠性25 新颖20 影响15 业绩15 催化15 自选10"""
    if role == "attachment":
        return 0
    v = 0
    # 可靠性 25
    rel = 10
    if inst:
        rel = 25
    elif any(k in t for k in NEWS_SRC):
        rel = 20
    elif any(k in t for k in ANNOUNCE_SOURCE):
        rel = 22
    v += rel
    # 新颖性 20（默认 20，重复由事件层降权）
    v += 20
    # 影响范围 15
    imp = 8
    if any(k in t for k in ['大盘', '两市', '指数', '宏观', '政策', '美联储', '央行']):
        imp = 15
    elif themes:
        imp = 12
    v += imp
    # 业绩相关性 15
    perf = 5
    if any(k in t for k in ['业绩', '财报', '订单', '中标', '合同', '营收', '利润', '盈利']):
        perf = 15
    elif themes:
        perf = 10
    v += perf
    # 催化强度 15
    cat = 3
    if any(k in t for k in ['涨停', '超预期', '涨价', '大增', '突破', '拐点', '翻倍', '大单']):
        cat = 15
    elif any(k in t for k in ['利好', '受益', '景气', '扩产', '获批']):
        cat = 10
    v += cat
    # 自选相关 10（由调用方用自选名单补充）
    v += 0
    return min(v, 100)


def legacy_map(ct):
    """content_type → 旧 primary_category 兼容"""
    return {
        'research_report': 'research', 'institution_view': 'research', 'research_activity': 'research',
        'news': 'news', 'announcement': 'announcement', 'market': 'market',
        'digest': 'news', 'attachment': 'image', 'empty_invalid': 'empty_invalid',
    }[ct]


def main():
    con = sqlite3.connect(DB)
    # 自选股名单（research_value 自选相关维度）
    watch = set()
    try:
        scon = sqlite3.connect("/root/stock-kanban/backend/stocks.db")
        watch = {str(r[0]) for r in scon.execute("SELECT symbol FROM stocks")}
        scon.close()
    except Exception:
        pass
    rows = con.execute("""
        SELECT r.chat_id, r.message_id, r.source_topic, r.msg_type, r.raw_text, r.from_user
        FROM raw_messages r
        LEFT JOIN message_classification c ON c.message_id = r.chat_id || ':' || r.message_id
    """).fetchall()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    done = 0
    for chat_id, message_id, topic, mtype, text, from_user in rows:
        mid = f"{chat_id}:{message_id}"
        d = classify(mtype, text or "", topic or "")
        ct = d['content_type']
        # v1.4.2：消息角色统一用内容特征判定（机构署名=original，与采集通道无关）
        d['role'] = detect_role(ct, d.get('content_subtype', ''), text or "", d.get('inst', ''), mtype)
        if ct == 'empty_invalid':
            primary = 'empty_invalid'
        else:
            primary = legacy_map(ct)
        tags = d['tags']
        # 自选相关度 10
        codes = []
        ent = con.execute("SELECT stock_codes_json FROM normalized_messages WHERE message_id=?", (mid,)).fetchone()
        if ent and ent[0]:
            try:
                codes = json.loads(ent[0])
            except Exception:
                codes = []
        hit = [c for c in codes if c in watch]
        value = d['value'] + (10 if hit else 0)
        entities = {"stocks": codes, "industries": d['themes']}
        # 置信度分层
        conf = d['conf']
        review = d['review']
        reason_detail = d['reason']
        if review == 0 and conf < 0.85:
            # 0.65-0.85 正常入库 + 低置信标识（黄标），不进人工复核
            review = 0
        elif conf < 0.65:
            review = 1
        con.execute("""INSERT OR REPLACE INTO message_classification
            (message_id, source_topic, primary_category, secondary_category, tags_json,
             entities_json, sentiment, confidence, continuation,
             review_required, review_reason, review_reason_detail,
             vision_status, classifier_version, classified_at,
             content_type, content_subtype, ingest_source, original_source,
             institution, research_team, industry, themes_json, message_role,
             research_value, confidence_score)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (mid, topic, primary, d['content_subtype'], json.dumps(tags, ensure_ascii=False),
             json.dumps(entities, ensure_ascii=False), d['sentiment'],
             'high' if conf >= 0.85 else ('medium' if conf >= 0.65 else 'low'),
             0, review, ('分类置信度低' if review and conf < 0.65 else (reason_detail if review else '')),
             reason_detail, d['vision'], CLASSIFIER_VERSION, now,
             ct, d['content_subtype'], from_user or '', d['original_source'],
             d['inst'], d['team'], d['industry'], json.dumps(d['themes'], ensure_ascii=False),
             d['role'], value, conf))
        done += 1
    con.commit()
    stats = dict(con.execute("SELECT content_type, count(*) FROM message_classification GROUP BY content_type").fetchall())
    review_n = con.execute("SELECT count(*) FROM message_classification WHERE review_required=1").fetchone()[0]
    total = con.execute("SELECT count(*) FROM message_classification").fetchone()[0]
    con.close()
    print(f"✅ v1.4 分类: 更新 {done}/{total} | 主类型 {stats}")
    print(f"   待复核 {review_n} | 复核原因: {_review_split()}")


def _review_split():
    import sqlite3
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT review_reason_detail, count(*) FROM message_classification WHERE review_required=1 GROUP BY review_reason_detail ORDER BY count(*) DESC").fetchall()
    con.close()
    return {r[0] or '未分类': r[1] for r in rows}


if __name__ == "__main__":
    sys.exit(main())
