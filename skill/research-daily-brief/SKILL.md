---
name: research-daily-brief
description: 生成每日A股事件驱动研究简报（升温事件/重点股票/研究变化/风险）。只读VPS2研究API，不输出买卖建议。
version: 2.2.1
mode: stability_observation
purpose: daily research summary
constraints:
  - no trading advice
  - no score modification
  - no position operation
  - read-only research data
frozen:
  - event_momentum
  - research_score_weights
  - ten_models
  - trade_state_machine
---

# Research Daily Brief（每日研究简报）

## 观察期定位（v2.2.1）
当前处于 2-4 周稳定积累期：积累 T+1/T+3/T+5 真实验证数据，为 v2.3 权重优化做准备。
**不新增功能模块，只做简报体验优化**。重点观察：RS 分层有效性、因子贡献、人工效率。

## 触发条件
- 每日 09:00 cron 自动运行（cron job: research-daily-brief）
- 用户手动要求「研究简报 / 每日研究 / daily brief / 驾驶舱日报」

## 数据源（只读，不修改评分/交易）
所有数据来自 VPS2 资讯研究档案库 API（公网 `https://reports.wmsora.vip/archive/api/`）+ 持仓（`https://vip2.wmsora.vip/api/positions`）：

| 端点 | 用途 |
|---|---|
| `/dashboard/cockpit` | 今日驾驶舱：升温事件 + 每事件最高 RS 股票 + 重点研究列表 |
| `/validation/stats` | 研究验证统计（命中率/RS 分层有效性） |
| `/events?limit=30` | 事件列表（Momentum 排序） |
| `/events?id=N` | 事件详情（传播链/关联个股 RS/角色分层） |
| `/research-score?code=XXX` | 个股评分 + 解释 + 变化原因 |
| `/watchpool` | 研究队列候选 |

## 简报固定格式（Telegram 友好）

```markdown
🔥 今日研究驾驶舱
日期：2026-08-13（数据截至 08-12 收盘 · 事件近24h）

━━━━━━━━━━━━━━━━

1️⃣ 今日升温事件

🔥 AI服务器需求提升
Momentum 86 ↑ · 状态：升温中
机构确认：天风证券 / 国金证券
关联研究股：
  300502 新易盛 RS 87 🎯直接受益
  300308 中际旭创 RS 82

━━━━━━━━━━━━━━━━

2️⃣ 今日重点研究股票

① 太极实业 600667 · RS 82 ✅确认
  事件驱动强 · 5项模型命中
  ⚠️ 风险：技术仍待确认

━━━━━━━━━━━━━━━━

3️⃣ 研究变化

📈 变化：太极实业 RS 76→82（+6）
  原因：+8事件强度提升；+5模型新增命中

━━━━━━━━━━━━━━━━

4️⃣ 🔴 持仓相关

🔴 风华高科 000636 · RS 72 🎯聚焦 · TRIAL
  事件：AI服务器需求提升 🎯直接受益
  热度：🔥64 · 机构5家
  ⚠️ 风险：技术状态偏弱

（仅研究信息 · 不含买卖/仓位建议）

━━━━━━━━━━━━━━━━

5️⃣ 风险观察

⚠️（如有传闻/风险事件，单独列出）

━━━━━━━━━━━━━━━━
📊 验证统计：18 样本 · 命中率 100%
数据时间：2026-08-12 行情 · 事件近24h
```

## 执行步骤
1. 运行 `python3 ~/.hermes/skills/research-daily-brief/scripts/generate_brief.py`（自动拉取全部 API 数据并生成简报 Markdown）
2. 检查输出：如数据为空/异常，重试一次；仍失败则报告错误（不编造数据）
3. 用生成的 Markdown 作为最终回复内容（Telegram 自动推送）

## 安全边界（必须遵守）
- ✅ 只读研究数据（事件/评分/验证/风险）
- ✅ 可输出：研究建议、观察、风险提示
- ❌ 绝不输出：买入/卖出/仓位/止损止盈建议
- ❌ 绝不修改：research_scores / event_watch_pool / positions / 交易状态
- 文案始终带「研究辅助 · 非投资建议」后缀

## 输出样例
见 `examples/brief_sample.md`

## 已知问题
- 数据新鲜度：VPS2 kline 为收盘后更新（~16:00），早间简报使用昨日行情
- 事件标题可能带时间戳前缀（如「:33财联社…」），可截断清洗
- ⚠️ 时区坑（2026-08-13 发现并修复）：research_scores/research_summary.created_at 由 v19/v20 用 `datetime.now()` 写 **VPS 本地时区**（MST/MDT，比北京慢 14-15h），而 raw_messages.date / event_clusters.occurred_date 为**北京时间** → cockpit 按 raw_messages 北京日期过滤 scores 时三板块（hot_events/focus_stocks/rising_stocks）恒为空，早间简报 1/2/3 节全空。已做**显示层修复**：_cockpit() 改用 score_day=max(created_at 日期) / event_day=max(occurred_date) 过滤（VPS2 备份 archive_server.py.bak-20260813）。根治需 v15/v17/v19 统一 BEIJING_TZ（涉及归并窗口/验证对齐，须单独验收后实施）
- ⚠️ 首日基线：评分系统上线首日（08-12）所有股票 score_change=自身分数（「首次评分」），「研究变化」节会显示 +82 等大额变化，属正常现象
- ✅ 2026-08-14 修复「研究变化」原因截断：change_reason 的 label 形如「事件强度提升 +21（事件热度/机构增加）」，旧代码 [:12] 截断到括号中间输出乱码（+21（事）；现先剥离括号后缀与尾部数字再拼 delta（+21事件强度提升）
