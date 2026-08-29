# P1.4 Revision 持久化验收报告

- ✅ **G1_rerun_0duplicate** — recent=[{'run_id': 10, 'inserted': 0, 'hash': '24e470236701e0e1'}, {'run_id': 9, 'inserted': 336, 'hash': '24e470236701e0e1'}]
- ✅ **G2_revision_no_contiguous** — logicals=335, non_contiguous=0
- ✅ **G3_old_new_hash** — modified=99, missing_hash=0
- ✅ **G4_changed_fields_parseable** — unparseable=0
- ✅ **G5_role_keeps_semantics** — role_rows=99, semantic_broken=0
- ✅ **G6_severe_payload_replay** — severe_modified=0, broken=0; added_payload_missing=0, removed_payload_missing=0
- ✅ **G7_no_physical_overwrite** — events_hash=478a7c4f712b8bce (基线 478a7c4f712b8bce); positions_hash=8826975fa9b8fb14 (基线 8826975fa9b8fb14)
- ✅ **A1_orphan_revision** — orphan=0
- ✅ **A2_source_lineage** — snapshots=2, null_snapshot_id=0, dangling=0
**Gates: PASS**
**Audit: PASS**
**Overall: PASS**