# P1.3 Position Dual-Track 验收报告

- ✅ **G1_pos_to_holding** — total=124, not_holding=0
- ✅ **G5_a_share_resolvable** — null_code=0, non_EXACT/ALIAS=0
- ✅ **G3_position_lineage** — missing_lineage=0, events_orphan=0
- ✅ **G2_no_auto_buy** — position_state CHECK 强制 HOLDING；events 表 BUY 族总事件数=205（由 P1.2 生成，非 P1.3）
- ✅ **G6_dual_track_coexist** — 并存 37 条: {('ADD', 'EXECUTED'): 2, ('ADD', 'CONDITIONAL'): 3, ('ADD', 'INTENDED'): 3, ('BUY', 'INTENDED'): 1, ('DO_T', 'INTENDED'): 3, ('LOW_BUY', 'INTENDED'): 8, ('LOW_BUY', 'EXECUTED'): 1, ('REDUCE', 'EXECUTED'): 4, ('REDUCE', 'CONDITIONAL'): 5, ('SELL', 'CONDITIONAL'): 1, ('WATCH', 'INTENDED'): 6}
- ✅ **G4_rerun_0new** — recent_runs=[{'run_id': 8, 'inserted_event_count': 0, 'result_hash': '8826975fa9b8fb147804bd502c542e96324ddaf6ca1add7d7045abb850d4ea64', 'parser_version': 'v1.1'}, {'run_id': 7, 'inserted_event_count': 124, 'result_hash': '8826975fa9b8fb147804bd502c542e96324ddaf6ca1add7d7045abb850d4ea64', 'parser_version': 'v1.1'}]
**Overall: PASS**

**Overall: True**