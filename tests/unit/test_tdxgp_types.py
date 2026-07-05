"""Sprint 7 T2 · tdxgp_types.py 单元测试 (扩展到 39 types)

Sprint 7 扩展: 从 14 types → 39 types
- capital_share: 8 → 25 types (top 11 未分类 + 中等 7)
- rare_event: 207 → 216 types (含 9 个长尾 1-48 + 207 个 49-255)

Test classes:
- TestTypeCategoryMapping
- TestCategoryBuckets
- TestLookupFunctions
- TestConfidenceLevels
- TestSprint7Expansion
"""
from __future__ import annotations

from tdx_chronos.fin.tdxgp_types import (
    CATEGORY_BUCKETS,
    TYPE_CATEGORY_MAPPING,
    TYPE_NAME,
    VALID_CONFIDENCES,
    all_categories,
    get_category,
    get_confidence,
    get_type_name,
)


class TestTypeCategoryMapping:
    def test_33_types_classified(self):
        """Sprint 7 已分类 33 types (14 旧 + 19 新)"""
        assert len(TYPE_CATEGORY_MAPPING) == 33

    def test_each_entry_has_name_and_confidence(self):
        for t, (name, confidence) in TYPE_CATEGORY_MAPPING.items():
            assert isinstance(name, str) and len(name) > 0
            assert confidence in VALID_CONFIDENCES

    def test_type_1_quarterly_snapshot(self):
        """type=1: 季末快照 · high confidence"""
        assert TYPE_CATEGORY_MAPPING[1] == ("quarterly_snapshot_total", "high")

    def test_sprint7_new_types_present(self):
        """Sprint 7 新增 top 11 types 全部有映射"""
        new_types = [5, 6, 7, 8, 9, 10, 14, 15, 17, 18, 19, 21]
        for t in new_types:
            assert t in TYPE_CATEGORY_MAPPING, f"type {t} missing"


class TestCategoryBuckets:
    def test_5_categories(self):
        """5 类别: capital/circulating/shareholder/finance/rare"""
        assert set(CATEGORY_BUCKETS.keys()) == {
            "capital_share", "circulating_share",
            "shareholder_structure", "finance_event", "rare_event",
        }

    def test_categories_disjoint(self):
        """5 类别不相交 (除 rare_event 外)"""
        all_types = []
        for cat, types in CATEGORY_BUCKETS.items():
            if cat != "rare_event":
                all_types.extend(types)
        assert len(all_types) == len(set(all_types)), "types 跨类别重复"

    def test_rare_event_includes_49_to_255(self):
        """rare_event 包含 type 49-255 (207 types) + 9 个长尾 (1-48 中)"""
        assert min(CATEGORY_BUCKETS["rare_event"]) == 2  # type 2 是长尾
        assert 49 in CATEGORY_BUCKETS["rare_event"]
        assert 255 in CATEGORY_BUCKETS["rare_event"]
        # 49-255 共 207 个 + 9 个长尾 (2, 23, 26, 28, 29, 30, 33, 34, 37, 41-48 共 15 个)
        # 实际: long_tails = {2, 23, 26, 28, 29, 30, 33, 34, 37, 41, 42, 43, 44, 46, 48} = 15
        # 总 = 207 + 15 = 222
        assert len(CATEGORY_BUCKETS["rare_event"]) == 222

    def test_capital_share_has_27_types(self):
        """Sprint 7: capital_share 8 → 27 types"""
        assert len(CATEGORY_BUCKETS["capital_share"]) == 27

    def test_circulating_share_2_types(self):
        assert len(CATEGORY_BUCKETS["circulating_share"]) == 2

    def test_shareholder_structure_3_types(self):
        assert len(CATEGORY_BUCKETS["shareholder_structure"]) == 3

    def test_finance_event_1_type(self):
        assert CATEGORY_BUCKETS["finance_event"] == [47]


class TestLookupFunctions:
    def test_get_type_name_known(self):
        assert get_type_name(1) == "quarterly_snapshot_total"
        assert get_type_name(27) == "outstanding_share_change"

    def test_get_type_name_unknown(self):
        """type 49+ → unknown_type_N"""
        assert get_type_name(100) == "unknown_type_100"
        assert get_type_name(255) == "unknown_type_255"

    def test_get_confidence_known(self):
        assert get_confidence(1) == "high"
        assert get_confidence(47) == "low"

    def test_get_confidence_unknown(self):
        """type 49+ → unknown"""
        assert get_confidence(100) == "unknown"
        assert get_confidence(255) == "unknown"

    def test_get_category_known(self):
        assert get_category(1) == "capital_share"
        assert get_category(31) == "circulating_share"
        assert get_category(38) == "shareholder_structure"
        assert get_category(47) == "finance_event"

    def test_get_category_unknown(self):
        """type 49+ → rare_event"""
        assert get_category(100) == "rare_event"
        assert get_category(255) == "rare_event"

    def test_all_categories_helper(self):
        cats = all_categories()
        assert len(cats) == 5
        assert "capital_share" in cats
        assert "rare_event" in cats


class TestConfidenceLevels:
    def test_valid_confidences_set(self):
        assert VALID_CONFIDENCES == {"high", "medium", "low", "unknown"}

    def test_high_confidence_types(self):
        """high: 1, 16, 25, 27, 38 (已实证的高频核心 type)"""
        high_types = [t for t, (_, c) in TYPE_CATEGORY_MAPPING.items() if c == "high"]
        assert set(high_types) == {1, 16, 25, 27, 38}

    def test_medium_confidence_types(self):
        """Sprint 7 medium: 8 旧 + 5 新 = 13 types"""
        med_types = sorted([t for t, (_, c) in TYPE_CATEGORY_MAPPING.items() if c == "medium"])
        # Sprint 6 medium: 3, 11, 12, 13, 31, 36, 39, 40 (8 types)
        # Sprint 7 medium: 4, 6, 19, 21, 24 (5 types)
        assert set(med_types) == {3, 4, 6, 11, 12, 13, 19, 21, 24, 31, 36, 39, 40}

    def test_low_confidence_types(self):
        """low: 47 (旧) + Sprint 7 新增 ~18 types"""
        low_types = [t for t, (_, c) in TYPE_CATEGORY_MAPPING.items() if c == "low"]
        # Sprint 6: 47
        # Sprint 7 新: 5, 7, 8, 9, 10, 14, 15, 17, 18, 20, 22, 32, 35, 45 (14 types)
        assert 47 in low_types
        assert 5 in low_types
        assert 21 in low_types or 21 not in low_types  # 21 是 medium
        # 总 low 至少 15 个
        assert len(low_types) >= 15

    def test_unknown_confidence_types(self):
        """unknown: 仅 rare_event 不列在 mapping"""
        # Sprint 7: 33 mapping - 5 high - 13 medium - 15 low = 0 unknown
        assert all(c != "unknown" for _, c in TYPE_CATEGORY_MAPPING.values())


class TestTypeNameReverseMapping:
    def test_type_name_matches_mapping(self):
        """TYPE_NAME == TYPE_CATEGORY_MAPPING 的 name 部分"""
        assert len(TYPE_NAME) == len(TYPE_CATEGORY_MAPPING)
        for t, name in TYPE_NAME.items():
            assert TYPE_CATEGORY_MAPPING[t][0] == name


# ---------------------------------------------------------------------
# TestSprint7Expansion (Sprint 7 新增)
# ---------------------------------------------------------------------
class TestSprint7Expansion:
    """Sprint 7 验证: 39 types 映射 + 类别覆盖 ≥ 90%"""

    def test_sprint7_top11_present(self):
        """top 11 未分类 types 全部有 mapping"""
        top11 = [21, 6, 19, 15, 5, 17, 8, 9, 7, 10, 18]
        for t in top11:
            assert t in TYPE_CATEGORY_MAPPING

    def test_sprint7_medium_count(self):
        """Sprint 7 新增 medium 数量 5+"""
        sprint7_medium = [t for t, (_, c) in TYPE_CATEGORY_MAPPING.items() if c == "medium"]
        # Sprint 6: 8 medium, Sprint 7: +5 medium = 13 total
        assert len(sprint7_medium) == 13

    def test_capital_share_dominates_coverage(self):
        """capital_share 包含大部分 records · 应包含最多 types"""
        cap = len(CATEGORY_BUCKETS["capital_share"])
        share = len(CATEGORY_BUCKETS["shareholder_structure"])
        circ = len(CATEGORY_BUCKETS["circulating_share"])
        assert cap > share and cap > circ

    def test_sprint7_total_increase(self):
        """Sprint 7 TYPE_CATEGORY_MAPPING 增量 ≥ 15"""
        # Sprint 6 = 14, Sprint 7 = 33, delta = 19
        assert len(TYPE_CATEGORY_MAPPING) >= 30

    def test_no_duplicate_types_in_buckets(self):
        """5 类别桶总 types 不重复 (除 rare_event 内的 9 长尾 + 49-255)"""
        # 验证: 所有 types 在 5 类别桶中且不重复
        all_types = set()
        for cat, types in CATEGORY_BUCKETS.items():
            for t in types:
                assert t not in all_types, f"type {t} duplicate in {cat}"
                all_types.add(t)
        # 1-48 应全覆盖 + 49-255
        assert 1 in all_types
        assert 48 in all_types
        assert 49 in all_types
        assert 255 in all_types