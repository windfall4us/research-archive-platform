# Phase 1 Data Layer Benchmark（P1.5）

## 1. 输入与版本
- schema_version: 3
- source_snapshots: ['2026-08-27', '2026-08-28']
- ingest_runs: 13 条；parser 版本: [{'parser_version': 'p14-diff-v2', 'c': 3, 'latest': 13}, {'parser_version': 'v1.1', 'c': 10, 'latest': 12}]
- 重跑链路: ingest_consensus_p12.py, ingest_position_p13.py, ingest_revision_p14.py

## 2. 全链路重跑（幂等）
| script | run_id | inserted | skipped | hash | error |
|---|---|---|---|---|---|
| ingest_consensus_p12.py | 14 | 0 | 934 | 478a7c4f712b8bce | 0 |
| ingest_position_p13.py | 15 | 0 | 124 | 8826975fa9b8fb14 | 0 |
| ingest_revision_p14.py | 16 | 0 | 336 | 24e470236701e0e1 | 0 |

## 3. 7 个核心 Gate

| Gate | 判定 | 明细 |
|---|---|---|
| G1_duplicate_ingest | ✅ | [{'script': 'ingest_consensus_p12.py', 'exit': 0, 'run_id': 14, 'inserted': 0, 'skipped': 934, 'hash': '478a7c4f712b8bce', 'error_count': 0}, {'script': 'ingest_position_p13.py', 'exit': 0, 'run_id': 15, 'inserted': 0, 'skipped': 124, 'hash': '8826975fa9b8fb14', 'error_count': 0}, {'script': 'ingest_revision_p14.py', 'exit': 0, 'run_id': 16, 'inserted': 0, 'skipped': 336, 'hash': '24e470236701e0e1', 'error_count': 0}] |
| G2_a_share_resolvable | ✅ | total=937, resolvable=937, by=[('ALIAS', 30), ('EXACT', 907)] |
| G3_false_executed | ✅ | risk_executed=121 (BUY族+SELL族), non_reproducible=0 |
| G4_holding_to_buy | ✅ | position_snapshots not_holding=0, buy_like=0 |
| G5_revision_traceable | ✅ | revisions=336, orphan=0, non_contiguous_logicals=0 |
| G6_source_lineage | ✅ | bad_lineage=0 (events+positions+revisions) |
| G7_repeat_run_consistent | ✅ | {'events': {'pre': '478a7c4f712b8bce', 'post': '478a7c4f712b8bce'}, 'positions': {'pre': '8826975fa9b8fb14', 'post': '8826975fa9b8fb14'}, 'revisions': {'pre': '24e470236701e0e1', 'post': '24e470236701e0e1'}} |

## 4. 辅助审计指标
- A1 行数: {'analyst_stock_events': 937, 'analyst_position_snapshots': 124, 'record_revisions': 336, 'analyst_profiles': 10, 'ingest_runs': 16}
- A2 分层: {'STOCK': 808, 'THEME': 34, 'COMPOSITE': 35, 'MARKET': 9, 'OUT_OF_SCOPE': 11, 'UNKNOWN': 5}
- A3 冲突: {'CLEAR+HOLDING': 0, 'SELL+HOLDING': 1}
- A4 revision severity: {'ROLE': 99, 'SEVERE': 237}
- A5 版本: {'schema_version': 3, 'parser': 'v1.1', 'resolver': 'exact-alias-v1', 'snapshots': ['2026-08-27', '2026-08-28']}

## 5. Data Contract Summary（Phase 1 锁定边界）

- **analyst_stock_events**: 完整事件事实层，存全部 11 类动作（TRADE/OBSERVATION/STATE/COMPOSITE_TACTICAL/UNKNOWN）
- **analyst_position_snapshots**: 日终确认持仓观察值，position_state 仅 HOLDING（CHECK 强制）
- **position_snapshot_derives_buy**: False
- **event_position_dual_track**: 允许并存（ADD/LOW_BUY/REDUCE/SELL + HOLDING 合法；CLEAR+HOLDING 需审计）
- **composite_theme_market_oos**: 不强拆为 A 股个股事件；仅 A_SHARE 落 events/positions
- **revision**: append-only，不物理覆盖历史（old_payload/new_payload 完整回放）
- **security_master**: 独立 DB（security_master.db），只读引用，不复制
- **parser_baseline**: v1.1 LOCKED；Q/R/S gap 走独立版本升级，不在 Phase 2 内修改

## 6. 最终判定

**Overall: GO**
Gate 明细: {'G1_duplicate_ingest': '✅', 'G7_repeat_run_consistent': '✅', 'G2_a_share_resolvable': '✅', 'G3_false_executed': '✅', 'G4_holding_to_buy': '✅', 'G5_revision_traceable': '✅', 'G6_source_lineage': '✅'}

> 已知遗留：P1.2 的 3 条 COMPOSITE 残留单股事件（天赢居 08-28 多标的）建议 Phase 1 冻结后单独评估，不混入本 benchmark。

**Next: Phase 2 — Market Direction + Theme Heat**