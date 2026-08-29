# P1.3 Position 差异审计：Parser-only / direction-only

> 口径 B：position_snapshots 只由 Parser 确认 HOLD+POSITION_STATE 生成 HOLDING；
> direction=持有 仅作审计 evidence，不落库。

## 1. 四集合关系
- hold(Parser POSITION_STATE, A股): **124**  → 已落库 HOLDING
- direction=持有（全量 **201**，A股 **185**）
- union(hold∪direction): **229**（不采用）
- inter(hold∩direction): **96**（不采用）
- **Parser-only**（hold 有 / direction 无）: **28**
- **direction-only**（direction 有 / hold 无，抽查对象）: **105**（A股 89 + 非A股 16）
- both（交集）: **96**

## 2. direction-only 105 条语义分类（Parser 未判 POSITION_STATE 的原因分布）
| 分类 | 条数 | 说明 |
|---|---:|---|
| 其他 | 32 | 无法归入以上 |
| 纯持仓确认 | 25 | 明确持仓（持有/持股/底仓/可留）→ 疑似 Parser 漏判 HOLD/POSITION_STATE |
| 观察/计划 | 18 | 观察/跟踪/为主 类 |
| 纯条件/计划 | 11 | 无持仓动词的条件/计划句 |
| 卖出/减仓 | 11 | direction=持有 但 action 主语义是卖出（方向与动作冲突）→ 采编标记 vs action 语义不一致 |
| 条件+持仓 | 6 | 持仓句带条件加/减仓（如'底仓持有，等突破再加'）→ gap A 场景：条件事件可能挤掉了主 HOLD 的 POSITION_STATE |
| 减/卖+持仓或条件 | 1 | 含减/卖语义但保留持仓（如'部分减仓止盈，放量突破则小幅加仓'）→ Parser 可能只出 CONDITIONAL/EXECUTED 交易事件 |
| 减/卖+条件 | 1 | 含减/卖语义且条件化（如'破位价差'）→ 条件卖出，gap B 场景 |

## 3. direction-only 的 Parser 实际输出（为什么没判成 POSITION_STATE）
| Parser 输出 (action/status) | 条数 |
|---|---:|
| WATCH/INTENDED | 65 |
| HOLD/POSITION_STATE | 14 |
| REDUCE/EXECUTED | 12 |
| REDUCE/CONDITIONAL | 7 |
| HOLD/INTENDED | 6 |
| ADD/CONDITIONAL | 5 |
| DO_T/INTENDED | 5 |
| LOW_BUY/INTENDED | 3 |
| ADD/INTENDED | 3 |
| TRIAL/CONDITIONAL | 1 |
| BUY/INTENDED | 1 |
| TRIAL/INTENDED | 1 |

## 4. direction-only 逐条清单（105，resolve 列标非 A 股）

| # | 分析师 | 日期 | 标的 | action | 分类 | resolve | Parser 输出 |
|---|---|---|---|---|---|---|---|
| 1 | 老樊 | 2026-08-14 | 药明康德 | 不在卖点结构上出，等回落贴近中期均线组再打试错仓 | 纯条件/计划 | STOCK | TRIAL/CONDITIONAL/CONDITIONAL |
| 2 | 老樊 | 2026-08-17 | 芯原股份 | 乖离买点底仓继续拿，突破买点出现前仓位不变 | 条件+持仓 | STOCK | WATCH/INTENDED/TODAY |
| 3 | 老樊 | 2026-08-17 | 中石科技 | 连板行情不能继续再考虑止盈，目前可留 | 减/卖+持仓或条件 | STOCK | REDUCE/CONDITIONAL/CONDITIONAL |
| 4 | 老樊 | 2026-08-17 | 生益科技 | 已打底仓可留，后续绿盘加仓等突破买点结构 | 条件+持仓 | STOCK | BUY/INTENDED/TODAY; ADD/CONDITIONAL/CONDITIONAL |
| 5 | 老樊 | 2026-08-17 | 国瓷材料 | 策略暂时无变化 | 其他 | THEME | HOLD/POSITION_STATE/CURRENT_STATE |
| 6 | 老樊 | 2026-08-17 | 长鑫科技 | 持仓跟踪，泡沫阶段注意节奏 | 纯持仓确认 | STOCK | WATCH/INTENDED/TODAY |
| 7 | 老樊 | 2026-08-17 | 有研硅(688432) | 继续持有 | 纯持仓确认 | STOCK | HOLD/INTENDED/TODAY |
| 8 | 老樊 | 2026-08-18 | 芯原股份 | 底仓可拿，短期股价继续磨 | 纯持仓确认 | STOCK | WATCH/INTENDED/TODAY |
| 9 | 老樊 | 2026-08-18 | 立昂微 | 用做波段，求稳可减仓防守 | 卖出/减仓 | STOCK | REDUCE/EXECUTED/TODAY |
| 10 | 老樊 | 2026-08-18 | 长飞光纤 | 部分减仓止盈，放量突破则小幅加仓 | 减/卖+条件 | STOCK | REDUCE/EXECUTED/TODAY; ADD/CONDITIONAL/CONDITIONAL |
| 11 | 老樊 | 2026-08-18 | 天孚通信 | 可继续拿，不想承担波动可先止盈部分 | 卖出/减仓 | STOCK | REDUCE/EXECUTED/TODAY |
| 12 | 老樊 | 2026-08-26 | 国瓷材料 | 小底仓可拿，新开仓等股价站回中期均线组 | 条件+持仓 | THEME | WATCH/INTENDED/TODAY |
| 13 | 老樊 | 2026-08-27 | 飞龙股份 | 涨停封板，回踩买点仍可博弈 | 纯条件/计划 | STOCK | WATCH/INTENDED/TODAY |
| 14 | 老樊 | 2026-08-27 | 淮北矿业 | 小仓位博弈，30%乖离附近半仓止盈 | 卖出/减仓 | STOCK | TRIAL/INTENDED/TODAY; REDUCE/EXECUTED/TODAY |
| 15 | 老樊 | 2026-08-28 | 芯原股份 | 圈内乖离买点结构左侧入场，暂不做仓位调整 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 16 | 震哥本尊 | 2026-08-14 | 紫光 | 持有 | 纯持仓确认 | UNKNOWN | HOLD/POSITION_STATE/CURRENT_STATE |
| 17 | 震哥本尊 | 2026-08-26 | 源杰科技 | 有低吸冲高做T | 纯条件/计划 | STOCK | LOW_BUY/INTENDED/TODAY; DO_T/INTENDED/TODAY |
| 18 | 震哥本尊 | 2026-08-26 | 联特科技 | 科技整体修复时有望翻红 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 19 | 震哥本尊 | 2026-08-27 | 中际旭创 | 竞价强，观察延续 | 观察/计划 | STOCK | WATCH/INTENDED/TODAY |
| 20 | 震哥本尊 | 2026-08-27 | 蘅东光 | 继续持有，未动 | 纯持仓确认 | STOCK | HOLD/INTENDED/TODAY |
| 21 | 震哥本尊 | 2026-08-28 | 腾景科技/德科立/光库科技 | 偏格局，盘中看T还是减 | 观察/计划 | COMPOSITE | REDUCE/EXECUTED/TODAY |
| 22 | 天赢居 | 2026-08-14 | 易点天下 | 破线再减仓 | 卖出/减仓 | STOCK | REDUCE/EXECUTED/TODAY |
| 23 | 天赢居 | 2026-08-14 | 三六零 | 回踩55日均线之上就观察为主 | 纯条件/计划 | STOCK | WATCH/INTENDED/CONDITIONAL |
| 24 | 天赢居 | 2026-08-14 | 西部材料 | 继续持股 | 纯持仓确认 | THEME | HOLD/POSITION_STATE/CURRENT_STATE |
| 25 | 天赢居 | 2026-08-14 | 金螳螂(002081) | 不破板继续持有，观察下周一走势 | 条件+持仓 | STOCK | HOLD/INTENDED/FUTURE_PLAN; WATCH/INTENDED/FUTURE_PLAN |
| 26 | 天赢居 | 2026-08-17 | 科创新源(300731) | 分时黄线上继续观察，破位防守 | 观察/计划 | STOCK | WATCH/INTENDED/TODAY |
| 27 | 天赢居 | 2026-08-17 | 药石科技(300725) | 5/8日均线之上可观察，破位或5/8日均线死叉则减出 | 观察/计划 | STOCK | WATCH/INTENDED/TODAY; REDUCE/CONDITIONAL/CONDITIONAL |
| 28 | 天赢居 | 2026-08-17 | 国科微(300672) | 8日均线上可观察 | 观察/计划 | STOCK | WATCH/INTENDED/TODAY |
| 29 | 天赢居 | 2026-08-17 | 东方铁塔(002545) | 线上观察，破位减仓 | 卖出/减仓 | STOCK | WATCH/INTENDED/TODAY; REDUCE/CONDITIONAL/CONDITIONAL |
| 30 | 天赢居 | 2026-08-17 | 利尔化学(002258) | 右侧突破144日均线继续观察，缩量则价差 | 纯条件/计划 | STOCK | WATCH/INTENDED/TODAY |
| 31 | 天赢居 | 2026-08-17 | 顺钠股份(000533) | 21日均线线上持仓观察消化 | 纯持仓确认 | STOCK | WATCH/INTENDED/TODAY |
| 32 | 天赢居 | 2026-08-17 | 太极实业(600667) | 两级支撑分级防守 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 33 | 天赢居 | 2026-08-17 | 金牛化工(600722) | 破位做价差到144日均线附近接回 | 其他 | STOCK | ADD/CONDITIONAL/CONDITIONAL |
| 34 | 天赢居 | 2026-08-17 | 有研新材(688432) | 守住观察 | 观察/计划 | STOCK | WATCH/INTENDED/TODAY |
| 35 | 天赢居 | 2026-08-17 | 元利科技(603217) | 线上持仓 | 纯持仓确认 | STOCK | WATCH/INTENDED/TODAY |
| 36 | 天赢居 | 2026-08-17 | 英维克(002837) | 守8日线 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 37 | 天赢居 | 2026-08-18 | 士兰微 | 做好防守观察 | 观察/计划 | STOCK | WATCH/INTENDED/TODAY |
| 38 | 天赢居 | 2026-08-18 | 欧科亿 | 留意短期消化结构 | 纯持仓确认 | STOCK | WATCH/INTENDED/TODAY |
| 39 | 天赢居 | 2026-08-18 | 恩捷股份 | 顺短期多头均线通道跟踪 | 观察/计划 | STOCK | WATCH/INTENDED/TODAY |
| 40 | 天赢居 | 2026-08-18 | 澜起科技 | 线上跟踪 | 观察/计划 | STOCK | WATCH/INTENDED/TODAY |
| 41 | 天赢居 | 2026-08-18 | 太极实业 | 观察横向平台支撑 | 观察/计划 | STOCK | WATCH/INTENDED/TODAY |
| 42 | 天赢居 | 2026-08-18 | 大金重工 | 底仓继续留意 | 纯持仓确认 | STOCK | WATCH/INTENDED/TODAY |
| 43 | 天赢居 | 2026-08-18 | 西藏珠峰 | 右侧突破55日均线再扩大仓位 | 纯条件/计划 | STOCK | WATCH/INTENDED/TODAY |
| 44 | 天赢居 | 2026-08-18 | 西藏矿业 | 守21日均线，破位减仓 | 卖出/减仓 | STOCK | REDUCE/CONDITIONAL/CONDITIONAL |
| 45 | 天赢居 | 2026-08-18 | 寒锐钴业 | 继续留意 | 纯持仓确认 | STOCK | WATCH/INTENDED/TODAY |
| 46 | 天赢居 | 2026-08-18 | 昆仑万维 | 耐心等待，线上观察反压消化 | 纯条件/计划 | STOCK | WATCH/INTENDED/CONDITIONAL; WATCH/INTENDED/TODAY |
| 47 | 天赢居 | 2026-08-18 | 三六零 | 守住联合支撑观察，守不住做防守 | 观察/计划 | STOCK | WATCH/INTENDED/TODAY |
| 48 | 天赢居 | 2026-08-18 | 奥瑞德 | 短期防守 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 49 | 天赢居 | 2026-08-19 | 青山纸业(600103) | 破位价差；今日到21日线暂不补仓 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 50 | 天赢居 | 2026-08-19 | 三变科技(002112) | 尾盘破55日均线先减仓观察 | 卖出/减仓 | STOCK | REDUCE/CONDITIONAL/CONDITIONAL |
| 51 | 天赢居 | 2026-08-19 | 大连电瓷(002606) | 尾盘站不上紫线短线先减仓 | 卖出/减仓 | STOCK | REDUCE/EXECUTED/TODAY |
| 52 | 天赢居 | 2026-08-19 | 晓程科技(300139) | 守不住46元减仓；30分钟55MA压制可日T（低吸反弹T出） | 卖出/减仓 | STOCK | REDUCE/EXECUTED/TODAY; LOW_BUY/INTENDED/TODAY |
| 53 | 天赢居 | 2026-08-19 | 西藏珠峰(600338) | 60分钟通道下轨破位暂时观望 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 54 | 天赢居 | 2026-08-19 | 兆日科技(300333) | 守60分钟紫线区间底部支撑（8月13日一字板价格） | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 55 | 天赢居 | 2026-08-19 | 信邦智能(301112) | 先守55日均线 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 56 | 天赢居 | 2026-08-26 | 招金黄金 | 破位5日均线做价差，13日均线企稳接回 | 其他 | STOCK | ADD/INTENDED/TODAY |
| 57 | 天赢居 | 2026-08-26 | 天山铝业 | 突破21日均线打开上行空间，激进可适当加仓守紫线 | 纯条件/计划 | STOCK | ADD/INTENDED/TODAY |
| 58 | 天赢居 | 2026-08-26 | 西藏矿业 | 关注冲涨377日均线附近的高抛机会 | 观察/计划 | STOCK | WATCH/INTENDED/TODAY; REDUCE/EXECUTED/TODAY |
| 59 | 天赢居 | 2026-08-26 | 昆仑万维 | 破位144周均线需减持观察 | 卖出/减仓 | STOCK | REDUCE/CONDITIONAL/CONDITIONAL |
| 60 | 天赢居 | 2026-08-26 | 拓尔思/三六零 | 底仓持有，暂不开仓不加仓 | 纯持仓确认 | COMPOSITE | HOLD/POSITION_STATE/CURRENT_STATE |
| 61 | 天赢居 | 2026-08-26 | 厦门钨业 | 关注51.05元一带共振支撑 | 观察/计划 | STOCK | WATCH/INTENDED/TODAY |
| 62 | 天赢居 | 2026-08-26 | 阳光电源/锦浪科技 | 底仓持有观察，不开新仓不加仓 | 纯持仓确认 | COMPOSITE | HOLD/POSITION_STATE/CURRENT_STATE |
| 63 | 天赢居 | 2026-08-27 | 大盘 | 大仓位持股，让利润奔跑 | 纯持仓确认 | MARKET | HOLD/POSITION_STATE/CURRENT_STATE |
| 64 | 天赢居 | 2026-08-27 | 688308澜起科技 | 守住底仓观察，突破55日均线补仓 | 条件+持仓 | STOCK | WATCH/INTENDED/TODAY; ADD/CONDITIONAL/CONDITIONAL |
| 65 | 天赢居 | 2026-08-27 | 301205联特科技 | 观察缺口反压消化 | 观察/计划 | STOCK | WATCH/INTENDED/TODAY |
| 66 | 天赢居 | 2026-08-27 | 300229拓尔思 | 不开新仓不加仓 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 67 | 天赢居 | 2026-08-27 | 601360三六零 | 不开新仓不加仓 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 68 | 天赢居 | 2026-08-28 | 大盘(8月28日策略) | 上升趋势持股，回撤3927-3955良性，方向看3995(233日)→4013-40 | 纯持仓确认 | MARKET | HOLD/POSITION_STATE/CURRENT_STATE; WATCH/INTENDED/TODAY |
| 69 | 天赢居 | 2026-08-28 | 拓斯达(300607) | 看37.8/38.18前高，不能突破高抛价差，突破看缺口 | 纯条件/计划 | STOCK | WATCH/INTENDED/TODAY; REDUCE/CONDITIONAL/CONDITIONAL |
| 70 | 天赢居 | 2026-08-28 | 德邦科技(688035) | 短线阻力144日均线，有效突破企稳可加仓，否则价差 | 纯条件/计划 | STOCK | ADD/CONDITIONAL/CONDITIONAL |
| 71 | 天赢居 | 2026-08-28 | 西藏珠峰(600338) | 破位价差 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 72 | 天赢居 | 2026-08-28 | 西藏矿业(000762) | 破位价差 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 73 | 天赢居 | 2026-08-28 | 晶晨股份(688099) | 守紫线区间底部支撑，上方55日均线95一带 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 74 | 格兰投研 | 2026-08-14 | 中兴通讯 | 震荡降本 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 75 | 格兰投研 | 2026-08-17 | 通富微电 | 已先行，强势跟踪 | 观察/计划 | STOCK | WATCH/INTENDED/TODAY |
| 76 | 格兰投研 | 2026-08-18 | 通富微电 | 继续持有 | 纯持仓确认 | STOCK | HOLD/INTENDED/TODAY |
| 77 | 格兰投研 | 2026-08-18 | 茂莱光学 | 仓位集中，下半年CPO全流程检测设备兑现，波动大但拿住 | 纯持仓确认 | STOCK | REDUCE/EXECUTED/TODAY |
| 78 | 格兰投研 | 2026-08-18 | 深信服 | 配好当防守 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 79 | 格兰投研 | 2026-08-18 | 芯原股份 | 继续持有做T | 纯持仓确认 | STOCK | HOLD/INTENDED/TODAY; DO_T/INTENDED/TODAY |
| 80 | 格兰投研 | 2026-08-19 | 阿里巴巴 | 持有 | 纯持仓确认 | OUT_OF_SCOPE | HOLD/POSITION_STATE/CURRENT_STATE |
| 81 | 格兰投研 | 2026-08-19 | 立讯精密 | 等催化不着急，这位置跌不到哪去了 | 纯条件/计划 | STOCK | WATCH/INTENDED/TODAY |
| 82 | 格兰投研 | 2026-08-26 | 中芯国际 | 继续持有，正T起来 | 纯持仓确认 | STOCK | HOLD/INTENDED/TODAY |
| 83 | 格兰投研 | 2026-08-26 | 新易盛 | 收盘371破了就砍 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 84 | 格兰投研 | 2026-08-26 | 立讯精密 | 低吸了上去了抛 | 其他 | STOCK | LOW_BUY/INTENDED/TODAY |
| 85 | 格兰投研 | 2026-08-26 | 同花顺 | 涨多了把补的抛掉 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 86 | 格兰投研 | 2026-08-27 | 立讯精密 | 重点做好，光模块趋势 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 87 | 格兰投研 | 2026-08-27 | 资源金属 | 持有观察 | 纯持仓确认 | THEME | HOLD/POSITION_STATE/CURRENT_STATE |
| 88 | 游资混江龙 | 2026-08-14 | 海康威视 | 仓位轻可拿一拿，仓位重减仓 | 卖出/减仓 | STOCK | REDUCE/EXECUTED/TODAY |
| 89 | 游资混江龙 | 2026-08-17 | 药明康德 | 沿5日线慢慢飘 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 90 | 游资混江龙 | 2026-08-18 | 中远海特 | 底仓不要丢，可反复做T，等突破爆发点 | 条件+持仓 | STOCK | DO_T/INTENDED/TODAY |
| 91 | 游资混江龙 | 2026-08-18 | 风范股份 | 以零轴为支撑，破零轴收不回来彻底跑路 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 92 | 游资混江龙 | 2026-08-26 | 海康威视/美的集团/卫星化学/中国船舶 | 拿着筹码继续看 | 纯持仓确认 | COMPOSITE | HOLD/POSITION_STATE/CURRENT_STATE |
| 93 | 游资混江龙 | 2026-08-28 | 药明康德 | 大赚(8月交易计划总结) | 观察/计划 | STOCK | WATCH/INTENDED/TODAY |
| 94 | 游资混江龙 | 2026-08-28 | 卫星化学 | 大赚35个点浮盈 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 95 | 游资混江龙 | 2026-08-28 | 美的集团 | 小赚 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 96 | 游资混江龙 | 2026-08-28 | 景旺电子 | 赚 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 97 | 游资混江龙 | 2026-08-28 | 长鑫科技 | 赚十几个点 | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 98 | 游资混江龙 | 2026-08-28 | 桐昆股份 | 浮盈40点自己决定，不追涨（化工更好票多） | 其他 | STOCK | WATCH/INTENDED/TODAY |
| 99 | 妖股刺客 | 2026-08-17 | 日科化学 | 减的部分接回来了 | 其他 | STOCK | REDUCE/EXECUTED/TODAY; ADD/INTENDED/TODAY |
| 100 | 妖股刺客 | 2026-08-28 | 生益科技 | 科技没问题，关注 | 观察/计划 | STOCK | WATCH/INTENDED/TODAY |
| 101 | 李梦尘 | 2026-08-17 | 中际旭创/新易盛/东山精密/光迅科技 | 核心持有方向 | 纯持仓确认 | COMPOSITE | HOLD/POSITION_STATE/CURRENT_STATE |
| 102 | 李梦尘 | 2026-08-26 | 特高压（2只） | 持有，明天再看 | 纯持仓确认 | THEME | HOLD/POSITION_STATE/CURRENT_STATE; WATCH/INTENDED/FUTURE_PLAN |
| 103 | 李梦尘 | 2026-08-26 | 燕子家族 | 持有观察 | 纯持仓确认 | THEME | HOLD/POSITION_STATE/CURRENT_STATE |
| 104 | 李梦尘 | 2026-08-28 | 硅微粉/硅片/靶材/折叠屏/冷液/电源 | 打地鼠模式，电源偏恶心，剩余子弹不动 | 其他 | THEME | DO_T/INTENDED/TODAY; HOLD/POSITION_STATE/CURRENT_STATE |
| 105 | 一线天渔哥 | 2026-08-28 | 湖南白银 | 滚动操作，跟踪 | 观察/计划 | STOCK | DO_T/INTENDED/TODAY; WATCH/INTENDED/TODAY |

## 4b. direction-only 中非 A_SHARE 的 16 条（direction=持有 但标的不构成 A 股，本就不该进 snapshots）
| # | 分析师 | 标的 | action | resolve |
|---|---|---|---|---|
| 1 | 老樊 | 国瓷材料 | 策略暂时无变化 | THEME |
| 2 | 老樊 | 国瓷材料 | 小底仓可拿，新开仓等股价站回中期均线组 | THEME |
| 3 | 震哥本尊 | 紫光 | 持有 | UNKNOWN |
| 4 | 震哥本尊 | 腾景科技/德科立/光库科技 | 偏格局，盘中看T还是减 | COMPOSITE |
| 5 | 天赢居 | 西部材料 | 继续持股 | THEME |
| 6 | 天赢居 | 拓尔思/三六零 | 底仓持有，暂不开仓不加仓 | COMPOSITE |
| 7 | 天赢居 | 阳光电源/锦浪科技 | 底仓持有观察，不开新仓不加仓 | COMPOSITE |
| 8 | 天赢居 | 大盘 | 大仓位持股，让利润奔跑 | MARKET |
| 9 | 天赢居 | 大盘(8月28日策略) | 上升趋势持股，回撤3927-3955良性，方向看3995(233日)→4013- | MARKET |
| 10 | 格兰投研 | 阿里巴巴 | 持有 | OUT_OF_SCOPE |
| 11 | 格兰投研 | 资源金属 | 持有观察 | THEME |
| 12 | 游资混江龙 | 海康威视/美的集团/卫星化学/中国船舶 | 拿着筹码继续看 | COMPOSITE |
| 13 | 李梦尘 | 中际旭创/新易盛/东山精密/光迅科技 | 核心持有方向 | COMPOSITE |
| 14 | 李梦尘 | 特高压（2只） | 持有，明天再看 | THEME |
| 15 | 李梦尘 | 燕子家族 | 持有观察 | THEME |
| 16 | 李梦尘 | 硅微粉/硅片/靶材/折叠屏/冷液/电源 | 打地鼠模式，电源偏恶心，剩余子弹不动 | THEME |

## 5. Parser-only 清单（hold 有 / direction 无，供对照）

| # | 分析师 | 日期 | 标的 | direction | action | Parser 输出 |
|---|---|---|---|---|---|---|
| 1 | 老樊 | 2026-08-26 | 顺钠股份 | 短线 | 短线可关注，模型加持有炒作潜力 | WATCH/INTENDED/TODAY; HOLD/POSITION_STATE/CURRENT_STATE |
| 2 | 老樊 | 2026-08-28 | 华正新材 | 观察 | 需反复做T降本，过程考验持股 | DO_T/INTENDED/TODAY; HOLD/POSITION_STATE/CURRENT_STATE |
| 3 | 震哥本尊 | 2026-08-17 | 中际旭创 | 低吸 | 低吸持有 | LOW_BUY/INTENDED/TODAY; HOLD/POSITION_STATE/CURRENT_STATE |
| 4 | 震哥本尊 | 2026-08-18 | 太辰光 | 买入 | 2%多加仓，持有等产能落地业绩放量 | ADD/INTENDED/TODAY; HOLD/POSITION_STATE/CONDITIONAL |
| 5 | 震哥本尊 | 2026-08-26 | 蘅东光 | 低吸 | 低吸持有 | LOW_BUY/INTENDED/TODAY; HOLD/POSITION_STATE/CURRENT_STATE |
| 6 | 天赢居 | 2026-08-14 | 晶晨股份 | 减仓 | 顺21周均线持有观察，破位减出 | HOLD/POSITION_STATE/CURRENT_STATE; REDUCE/CONDITIONAL/CONDITIONAL |
| 7 | 天赢居 | 2026-08-17 | 招金黄金(000506) | 低吸 | 逢低慢慢接回，持有观察，上方5、8日均线交汇短线压制 | ADD/CONDITIONAL/CONDITIONAL; HOLD/POSITION_STATE/CURRENT_STATE |
| 8 | 天赢居 | 2026-08-17 | 天山铝业(002352) | 低吸 | 沿233小时均线或55日均线慢慢接回，持有观察 | ADD/INTENDED/TODAY; HOLD/POSITION_STATE/CURRENT_STATE |
| 9 | 天赢居 | 2026-08-18 | 江波龙 | 低吸 | 低吸后顺8日均线持有观察 | LOW_BUY/INTENDED/TODAY; HOLD/POSITION_STATE/CURRENT_STATE |
| 10 | 天赢居 | 2026-08-18 | 屹唐股份 | 低吸 | 低吸后顺关口持有观察 | LOW_BUY/INTENDED/TODAY; HOLD/POSITION_STATE/CURRENT_STATE |
| 11 | 天赢居 | 2026-08-18 | 沃森生物 | 减仓 | 剩余底仓顺21月均线持有观察 | HOLD/POSITION_STATE/CURRENT_STATE |
| 12 | 天赢居 | 2026-08-19 | 昆仑万维(300418) | 网格 | 377小时/377日均线之间高抛低吸，或右侧沿377日均线持股 | DO_T/INTENDED/TODAY; HOLD/POSITION_STATE/CURRENT_STATE |
| 13 | 天赢居 | 2026-08-26 | 赤峰黄金 | 减仓 | 收回5日均线持股，收不回减持，等13日均线再考虑回补 | HOLD/POSITION_STATE/CONDITIONAL; REDUCE/CONDITIONAL/CONDITIONAL; ADD/CONDITIONAL/CONDITIONAL |
| 14 | 天赢居 | 2026-08-27 | 002532天山铝业 | 观察 | 持有不加仓 | HOLD/POSITION_STATE/CURRENT_STATE |
| 15 | 天赢居 | 2026-08-28 | 600367 | 观察 | 持有观察，下周一能否站稳关键 | HOLD/POSITION_STATE/CURRENT_STATE |
| 16 | 天赢居 | 2026-08-28 | 002648 | 观察 | 持有观察 | HOLD/POSITION_STATE/CURRENT_STATE |
| 17 | 格兰投研 | 2026-08-18 | 海光信息 | 低吸 | 低吸持有 | LOW_BUY/INTENDED/TODAY; HOLD/POSITION_STATE/CURRENT_STATE |
| 18 | 游资混江龙 | 2026-08-18 | 华勤技术 | 低吸 | 控制好仓位持有 | HOLD/POSITION_STATE/CURRENT_STATE |
| 19 | 清北游资 | 2026-08-14 | 国风新材 | 买入 | 三日持股吃肉 | HOLD/POSITION_STATE/CURRENT_STATE |
| 20 | 清北游资 | 2026-08-17 | 共进股份 | 短线 | 秒板不用动，连留断走；09:55换手够还不能回封可考虑出 | HOLD/POSITION_STATE/CURRENT_STATE; SELL/CONDITIONAL/CONDITIONAL |
| 21 | 妖股刺客 | 2026-08-19 | 风华高科(000636) | 买入 | 已低吸，持有待修复 | LOW_BUY/EXECUTED/TODAY; HOLD/POSITION_STATE/CURRENT_STATE |
| 22 | 妖股刺客 | 2026-08-26 | 协鑫能科 | 短线 | 5分钟不涨停就落袋，涨停持有 | REDUCE/EXECUTED/TODAY; HOLD/POSITION_STATE/CURRENT_STATE |
| 23 | 妖股刺客 | 2026-08-27 | 生益科技 | 买入 | 封涨停，中军持有 | HOLD/POSITION_STATE/CURRENT_STATE |
| 24 | 李梦尘 | 2026-08-14 | 有研硅 | 买入 | 回补持有 | ADD/EXECUTED/TODAY; HOLD/POSITION_STATE/CURRENT_STATE |
| 25 | 李梦尘 | 2026-08-19 | 有研新材 | 买入 | 低吸持有，绿吃红T | LOW_BUY/INTENDED/TODAY; HOLD/POSITION_STATE/CURRENT_STATE |
| 26 | 李梦尘 | 2026-08-26 | 联瑞新材 | 低吸 | 尾盘先手买入，持有 | BUY/INTENDED/TODAY; HOLD/POSITION_STATE/CURRENT_STATE |
| 27 | 李梦尘 | 2026-08-27 | 有研硅 | 买入 | 低吃持有 | LOW_BUY/INTENDED/TODAY; HOLD/POSITION_STATE/CURRENT_STATE |
| 28 | 李梦尘 | 2026-08-27 | 有研新材 | 买入 | 低吃持有 | LOW_BUY/INTENDED/TODAY; HOLD/POSITION_STATE/CURRENT_STATE |