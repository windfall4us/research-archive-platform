# 市场共识雷达 · Consensus Snapshot / API Contract

> 版本：v1.0（2026-08-30）　状态：DRAFT → 待验收
> 定位：把「市场共识雷达」（Phase 1~4 冻结算法）作为**自选研判台一级模块**接入。
> 原则：**前端不感知 Phase 1~4 内部数据结构**，只消费一份 daily materialized snapshot；UI 阶段禁止修改底层评分/状态规则（全部只读）。

## 1. 总体架构

```
本机（研究管道，Phase 1~4 已冻结）
  analyst_consensus.db + data/p22b~p43/*.json + reports/market_consensus/*
        │  只读
        ▼
  build_consensus_snapshot.py ──▶ consensus_daily_snapshot.json（单文件、自包含、前端友好）
        │  上传
        ▼
研判台（Next.js watchlist-stock-analysis）
  data/consensus/consensus_daily_snapshot.json   ← 物化快照（唯一数据源）
        │  只读
        ▼
  /api/consensus/overview | themes | stocks | divergence | analysts/:id
        │  fetch
        ▼
  ConsensusPage.tsx（一级模块「共识」）
    ├─ 顶部数据状态栏（数据日期/分析师覆盖/LOW_SIGNAL/INSUFFICIENT_DATA/系统状态）
    ├─ 视图1 共识总览（市场方向/热主题/状态股票分布）
    ├─ 视图2 主题联动（每主题 Heat 四因子/Momentum/分析师覆盖/Trade/Holding/强共识股/分歧股）
    ├─ 视图3 个股状态清单（CONFIRMED→REVERSING→DIVERGING→…排序）
    └─ 视图4 分歧雷达（5 种分歧 + REVERSING 高优先级）
  副产物：每日静态 HTML Snapshot（审计/推送用，非主入口）
```

## 2. Snapshot Schema（consensus_daily_snapshot.json）

```jsonc
{
  "meta": {                        // 数据状态栏 + 审计
    "schema_version": "1.0",
    "generated_at": "ISO8601",
    "dates": ["2026-08-14", ...],  // 覆盖的交易日
    "latest_date": "2026-08-28",
    "n_dates": 8,
    "n_analysts": 10, "analyst_coverage": "10/10",
    "n_themes": 19, "n_stocks": 350, "n_mapped": 337, "n_unmapped": 13,
    "n_stock_events": 934, "n_theme_mentions": 186, "n_positions": 124,
    "system_status": "HEALTHY",
    "signal_warnings": {           // 低样本主题（前端弱化视觉权重）
      "LOW_SIGNAL": ["theme_id", ...],
      "INSUFFICIENT_DATA": ["theme_id", ...]
    },
    "pipeline": {                  // 血缘：各阶段产物版本
      "p21": {"file": "...", "md5": "...", "rows": 8},
      "p22c": {...}, "p23": {...}, "p31": {...}, "p32": {...},
      "p33": {...}, "p41": {...}, "p42": {...}, "p43": {...}
    }
  },
  "overview": {                    // 视图1 共识总览
    "latest_market": {             // 来自 P2.1 all_dates.json days[latest_date]
      "date": "2026-08-28",
      "direction": "BULLISH|NEUTRAL|BEARISH|...",
      "direction_score": 0.0,
      "eligible_analysts": 10,
      "coverage_status": "NORMAL|LOW_COVERAGE|INSUFFICIENT",
      "consensus_level": "HIGH_CONSENSUS|MEDIUM|LOW",
      "dominant_share": 0.0,
      "bullish": 5, "neutral": 3, "bearish": 2,
      "risk": {"distribution": {...}, "dominant": "MEDIUM"},
      "position_bias": {"distribution": {...}, "dominant": "..."}
    },
    "market_history": [            // 8日方向序列（趋势）
      {"date": "...", "direction": "...", "direction_score": 0.0, "eligible": 7}
    ],
    "top_themes": [                // 最新日热度 TOP（heat_score 降序）
      {"theme_id": "...", "theme_name": "...", "heat_score": 25.5,
       "heat_level": "HEATING|...", "momentum_state": "...", "signal_confidence": "..."}
    ],
    "state_distribution": {        // P4.3 状态股票分布
      "CONFIRMED": 19, "DIVERGING": 45, "WEAKENING": 87, "DISCOVERY": 27,
      "REVERSING": 13, "CONFIRMING": 3, "NEUTRAL": 143, "UNMAPPED": 13
    },
    "divergence_counts": {         // P4.2 汇总
      "high_divergence": 37, "analyst_split": 29, "theme_stock_mismatch": 54,
      "view_action_mismatch": 37, "holding_turning_negative": 18
    }
  },
  "themes": {                      // 视图2 主题联动
    "latest": [                    // 最新日 19 主题
      {
        "theme_id": "CYCL_NONFERROUS", "theme_name": "有色",
        "heat_score": 25.5, "heat_level": "HEATING", "heat_status": "VALID",
        "signal_confidence": "HIGH",
        "factors": {               // P2.2C 四因子（原始值，非 100 化）
          "coverage": {"analysts": 4, "eligible": 9, "raw": 0.44, "score": 44.4},
          "mention": {"positive": 3, "neutral": 2, "negative": 0, "net": 3, "score": 42.9},
          "trade": {"directional_value": 3.73, "event_count": 20, "score": 60.0},
          "holding": {"stocks": 6, "analysts": 5, "weighted_support": 5.5, "score": 77.8}
        },
        "momentum": {"state": "HEATING", "delta_1d": 5.2, "delta_3d": 12.1,
                     "observed_state": "HEATING"},
        "analyst_coverage": {"analysts": 4, "eligible": 9},
        "stock_stats": {"strong_consensus": 5, "divergence": 2, "total": 18},
        "top_stocks": [            // 该主题下代表性股票（CONFIRMED 优先）
          {"code": "000506", "name": "招金黄金", "state": "CONFIRMED", "linkage": "CONFIRMED_BULLISH"}
        ]
      }
    ],
    "history": [                   // 每主题 8 日 Heat 序列（迷你趋势）
      {"theme_id": "...", "theme_name": "...",
       "series": [{"date": "...", "heat_score": 20.1, "momentum_state": "..."}]}
    ]
  },
  "stocks": {                      // 视图3 个股状态清单 + 视图6 详情抽屉
    "latest": [                    // 全部 350（含 unmapped）
      {
        "code": "000506", "name": "招金黄金",
        "consensus_state": "STRONG_POSITIVE", "consensus_raw": 3.7,
        "consensus_strength": "STRONG",
        "main_theme": "CYCL_NONFERROUS", "theme_name": "有色",
        "theme_momentum": "HEATING", "theme_heat": 25.5,
        "linkage": "CONFIRMED_BULLISH",
        "cross_layer_state": "CONFIRMED", "state_notes": ["bullish_resonance_low_divergence"],
        "divergence": {            // P4.2 五维
          "consensus_strength": 0.33, "analyst_divergence": 0.0,
          "theme_stock_divergence": 0.0, "view_action_divergence": 0.5,
          "holding_action_divergence": 0.0, "divergence_score": 0.0
        },
        "n_events": 9, "n_analysts": 1, "n_dates": 7,
        "recent_actions": ["HOLD", "ADD", "WATCH"]
      }
    ],
    "detail": {                    // 个股详情抽屉（Action Flow 时间线）
      "000506": {
        "flows": [                 // P3.2 per_analyst_stock_flow 合并
          {"date": "2026-08-14", "analyst_id": "tianyingju", "analyst_name": "天赢居",
           "action_type": "ADD", "stage": "ACCUMULATE", "status": "EXECUTED",
           "temporal": "...", "direction": "+", "event_id": 123}
        ],
        "stage_sequence": ["SCAN", "ENTRY", "ACCUMULATE", "HOLD", "REDUCE"]
      }
    }
  },
  "divergence": {                  // 视图4 分歧雷达
    "reversing": [                 // 高优先级入口（P4.3 REVERSING 13）
      {"code": "...", "name": "...", "theme": "...", "theme_momentum": "...",
       "consensus_state": "...", "linkage": "...", "state_notes": [...]}
    ],
    "categories": {
      "analyst_split": [...],      // P4.2 分析师意见分裂
      "theme_stock_mismatch": [...],   // 主题≠个股
      "view_action_mismatch": [...],   // 观点≠操作
      "holding_turning_negative": [...], // 持仓仍在但动作转负
      "high_divergence": [...]      // 综合 divergence_score≥0.5
    }
  },
  "analysts": {                    // 分析师目录
    "tianyingju": {"name": "天赢居", "style": "SWING", "n_events": 396, "n_positions": 57}
  }
}
```

## 3. API 契约（研判台只读端点）

| 端点 | 返回 | 说明 |
|---|---|---|
| `GET /api/consensus/overview` | `{meta, overview}` | 共识总览（顶部状态栏 + 市场方向 + 热主题 + 状态分布） |
| `GET /api/consensus/themes` | `{meta, themes:{latest, history}}` | 主题联动总览 |
| `GET /api/consensus/themes?theme_id=X` | 该主题 latest + history | 主题详情（前端可复用 latest 数组内对象） |
| `GET /api/consensus/stocks` | `{meta, stocks}` | 个股状态清单（默认 CONFIRMED→REVERSING→DIVERGING→DISCOVERY→WEAKENING→CONFIRMING→NEUTRAL→UNMAPPED 排序） |
| `GET /api/consensus/stocks?code=X` | 单股 latest + detail(flows) | 个股详情（含 Action Flow 抽屉数据） |
| `GET /api/consensus/divergence` | `{meta, divergence}` | 分歧雷达（reversing 优先 + 5 分类） |
| `GET /api/consensus/analysts/:id` | 分析师画像 + 其全部 flows | 分析师动作流 |

实现：Next.js route handler 直接 `readFile(data/consensus/consensus_daily_snapshot.json)` + 按子集返回（快照单文件 ≤ 2MB，无需 DB）。

## 4. 数据状态与信号治理（前端强约束）

- 顶部状态栏固定显示：`数据日期 / 分析师覆盖 N/N / Market Views N / Theme Mentions N / Stock Events N / 更新时间 / 系统状态 HEALTHY|DEGRADED`
- **LOW_SIGNAL / INSUFFICIENT_DATA** 主题：前端必须弱化视觉权重（灰显/降透明度 + 徽标），不得与正常共识同权重渲染。
- 主题 heat 卡必须**同时**显示 `Coverage / Mention / Trade / Holding` 四项贡献（不只要一个 24.9）。
- 状态股票分布为 P4.3 冻结口径；个股列表排序按 state 优先级（用户锁定顺序），非代码序。

## 5. 审计 / 可重建

- `meta.pipeline` 记录每个消费产物的文件、md5、行数 → snapshot 可完全重建、可对照。
- Builder 幂等：输入不变 → 输出 md5 不变（注入 deterministic 排序）。
- Builder 只读消费；**不修改任何 P2~P4 冻结产物**。

## 6. 已知边界（沿用 Freeze Record，前端如实展示）

- 数据为横截面快照（8 交易日），时间转移状态机待样本 15-20 日后升级 v2。
- LAGGING_OR_DISTRIBUTION = 0（样本内无主题升温+个股转负组合）。
- TECH_GENERAL / NEW_ENERGY_ELECTROLYTE 无映射（前端不展示为空洞）。
