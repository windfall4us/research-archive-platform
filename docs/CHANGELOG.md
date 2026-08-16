# CHANGELOG

## v2.3.4e - Observation Lock 观察锁定期（2026-08-14）
**进入锁定期：冻结全部模型/算法/状态机/交易接口，只做必要修复 + 日报积累。**

### 变更内容
- **市场环境标签**：日报头部 + `research_system_snapshot.market_regime` 增加强势/震荡/弱势判定（研究池等权代理：涨跌家数比例 + 近5日 vs 前20日趋势 + 涨停近似），为 v2.4 判断「RS 在何种市场有效」提供数据基础
- **观察日报浏览器入口**：`observation_index.html` + 单日 `observation_report_YYYY-MM-DD.html`（reports.wmsora.vip 可看）
- **质量监控页去重**：移除「研究验证」块内旧「RS 分层有效性（T+3）」板块（v2.1 遗留），保留观察仪表盘新版超集（T+1/3/5 三周期）
- **机构未匹配列表排版修复**：新增 `.arc-unmatched-row` flex 布局（tag 固定 200px 列 + 计数完整显示），替代误用的 5 列 timeline grid
- 日报文件三处归档：md（`/root/workspace/observation_reports/`）+ html（报告站）+ `/var/log/research-obs.log`

### 观察指标（每日日报自动记录）
1. **RS 分层稳定性**（T+1/T+3/T+5/T+10/T+20 三周期 + 命中率）
2. **RS 四维贡献**（事件/模型/技术/资金平均分 × 命中率——⚠️ research_scores 仅保留最近 2 日快照，历史四维待 v2.3.4c 快照机制积累）
3. **Graph 增益**（同 RS 档内 GS高 vs GS低 对比——RS70-79：19.5% vs 10.84%，样本少待积累）
4. **Confidence 修正价值**（同 RS 档内高/低认可度对比 + maxDD 风险端）
5. **十大模型真实贡献**（样本/T+5/T+20/maxDD/命中率，含回撤质量）

### v2.4 启动条件
- 验证样本 ≥200 ✅（801）· T+5 完整 ≥100 ⏳（18）· T+20 数据 ⏳ · 覆盖 20 交易日 ⏳ · **多个市场环境** ⏳（今日起逐日记录）· snapshot 完整 ✅ · 日报连续记录 ✅

---

## v2.3.4c - Validation Snapshot 完整化（2026-08-14）
- `research_validation` 增加 3 快照字段：`model_snapshot_json`（当时模型状态）/ `event_snapshot_json`（当时事件状态）/ `graph_snapshot_json`（当时图谱状态）
- 回填脚本 `archive_validation_snapshot_v234c.py`（每日 21:40 兜底）+ validate_v21 升级（新样本自动带快照）
- 建立「解释当时为什么给这个分」能力：避免 look-ahead bias，v2.4 三轨实验的历史锚点

## v2.3.4b - 观察指标深化（2026-08-14）
- `archive_obs_v234.py` 增加 Event Momentum 分层（80+/60-79/<60 × 命中率）+ 十模型贡献统计（当前模型 × 验证表现）
- ⚠️ 生存偏差警示：模型贡献样本是「经筛选入池」股票，非全市场，命中率偏高是筛选结果

## v2.3.4 - 图谱统计优化（2026-08-14）
- Industry Contribution Score（一级行业贡献拆分，AI算力 27%/光模块 13%）
- Graph Centrality（股票研究中心度：事件30+机构25+文档20+行业15+传播10）
- 机构研究雷达（机构 → 行业分布，判断提前覆盖主题）
- Research Confidence（研究对象可信度：质量50+机构15+传播8+事件5+股票3）
- GS 时间趋势（event_momentum 历史桶按天聚合 + ↑/→/↓）
- 前端研究图谱 tab：热门主题（GS+趋势）/ 核心股票（中心度）/ 核心机构 / 行业地图（贡献①②③）

## v2.3.3 - 研究图谱融合（2026-08-14）
- `research_graph_relation` 边表（5382 条）：document/industry/event/stock/institution 5 实体互连
- Graph Score = 机构×4 + 文档×3 + 事件×2 + 股票×2 + 行业×1（辅助指标，不进 RS）
- `/api/graph`：map（研究地图）/ entity（五维详情）/ code（股票图谱）
- ⚠️ SQLite TEXT affinity：股票代码前导零被吞，图谱内部统一 int 化

## v2.3.2 - 行业实体化（2026-08-14）
- `industry_entity`（50 实体：一级 10 + 二级 40，aliases 同义词）+ `industry_entity_relation`（386 关系）
- Industry Momentum 热度 = 对象+机构+事件×2+最高RS×0.4+最高Momentum×0.2
- 行业追踪 tab 升级为行业实体中心（热门行业网格 + 行业详情 + 子行业下钻）

## v2.3.1 - 研究对象中心（2026-08-14）
- `/api/research-documents`：研究对象列表（质量等级/多机构聚合/股票4层补提/事件关联/来源链）
- 机构研究 tab 从消息列表升级为研究对象卡片（质量星 + 机构 + 来源数 + 股票 + 事件）
- 股票补提：库内 → normalized → 正则（A股前缀白名单）→ 名称反查，7→42 个有股票文档

## v2.3.0 - 数据治理层（2026-08-14）
- `research_document` 表：标题规范化 + 多来源归并（相似≥90% + 同股票 + 24h）+ 质量评分（机构30/研报20/股票20/摘要15/重复-20/无来源-30）
- 首跑 560 消息 → 471 文档（合并 88 重复）

## v2.2.3 - 数据质量监控 + 行业画像（2026-08-13/14）
- `archive_quality_check_v223.py`（每日 21:30 健康报告，退出码 0/2）
- 行业追踪 v2.2.3 行业画像（同义词展开 + 事件/重点股票/资讯四段）→ v2.3.2 被行业实体化取代

## v2.2.2 - 研究队列股票级聚合（2026-08-13，冻结 Schema）
- `/api/watchpool` 按 stock_code 聚合（底层事件×股票不删数据）
- 50 事件行 → 34 股票，统计口径改为股票级
- watchpool 五条规则：热度双门槛 / 机构确认 / 排除风险 / 排除ST / 上限50

## v2.2.1 - Stability Observation（2026-08-12 起）
**运行阶段定义，非功能版本。代码冻结，参数冻结。**

### 变更内容
- 系统进入 2-4 周稳定观察期（约 20 个交易日）
- 冻结：Event Momentum / Research Score 权重 / 十大模型评分 / 交易状态机
- 简报增强（体验优化，非功能）：
  - 3️⃣ 研究变化：昨日关注 → 今日变化（RS 前日→今日 + change_reason）
  - 4️⃣ 🔴 持仓相关：持仓股 RS/事件/热度/机构（仅研究信息，无买卖建议）
- 文档新增：VERSION.md / CHANGELOG.md / 观察期说明
- Skill 增加运行模式标记（stability_observation）

### 观察目标（2-4 周后评估）
1. **RS 分层有效性**：高 RS 是否长期优于低 RS（T+1/T+3/T+5 命中率）
2. **因子贡献**：事件/模型/技术/资金哪个贡献最大
3. **人工效率**：简报是否减少 ≥50% 人工研究时间

### 退出条件
- 收集 200+ 真实验证样本（多市场环境、多行业）
- 数据满足后进入 v2.3 Research Feedback Optimization

---

## v2.2 - Hermes Research Agent（2026-08-12）
- skill `research-daily-brief`：每日 09:00 研究简报推送 Telegram
- 简报格式：🔥驾驶舱 → 升温事件 → 重点研究 → 研究变化 → 持仓相关 → 风险观察 → 验证统计
- 安全边界：只读研究数据，无买卖/仓位建议

## v2.1 - Research Validation
- research_validation 表：T+1/T+3/T+5 + 最大涨幅/回撤 + 命中率
- 验证引擎 + 历史回填 + 演示回放
- 每日 cron 自动累积

## v2.0 - Event Driven Research Terminal
- 今日研究驾驶舱（cockpit API）
- Research Summary 自动生成
- 研究队列（原观察池更名）

## v1.9.1 - Research Evolution
- 每日快照 + score_change + change_reason + research_state
- 趋势迷你曲线 + 变化原因抽屉

## v1.9 - Research Score
- 事件30 + 十模型35 + 技术20 + 资金15
- 解释层 + 缺失条件 + 状态映射

## v1.8.x - Event Watch Pool / Stock Catalyst
- event_watch_pool 52 候选 + 状态机
- /api/stocks/events 个股事件催化

## v1.7 - Event Momentum
- event_momentum 小时快照 + 六维热度 + 触发点

## v1.6 - Event-Stock Intelligence
- event_stock_relation 829 条映射 + 持仓标记

## v1.6.1 - Propagation Timeline
- 传播链时间轴 + lead_time 指标

## v1.5 - 事件语义层
- 语义事件 75 + 角色分层 + 评分 + 状态

## v1.4.2 - 来源可信库
- message_role + 来源聚合 + 主展示优先级

## v1.4 - 分类重构
- 8 主类型互斥 + 公告收紧 + 事件聚类雏形

## v1.3 - 资讯分类库
- 分类/归并/API 基础
