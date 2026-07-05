"""Sprint 6 T1 · tdxgp_types.py 单元测试

Test classes:
- TestTypeCategoryMapping
- TestCategoryBuckets
- TestLookupFunctions
- TestConfidenceLevels
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
    def test_14_types_classified(self):
        """Sprint 6 已分类 14 types (1,3,11,12,13,16,25,27,31,36,38,39,40,47)"""
        assert len(TYPE_CATEGORY_MAPPING) == 14

    def test_each_entry_has_name_and_confidence(self):
        for t, (name, confidence) in TYPE_CATEGORY_MAPPING.items():
            assert isinstance(name, str) and len(name) > 0
            assert confidence in VALID_CONFIDENCES

    def test_type_1_quarterly_snapshot(self):
        """type=1: 季末快照 · high confidence"""
        assert TYPE_CATEGORY_MAPPING[1] == ("quarterly_snapshot_total", "high")


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

    def test_rare_event_is_49_to_255(self):
        """rare_event = type 49-255 (207 types)"""
        assert min(CATEGORY_BUCKETS["rare_event"]) == 49
        assert max(CATEGORY_BUCKETS["rare_event"]) == 255
        assert len(CATEGORY_BUCKETS["rare_event"]) == 207

    def test_capital_share_has_8_types(self):
        """capital_share 8 types"""
        assert len(CATEGORY_BUCKETS["capital_share"]) == 8

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
        """medium: 3, 11, 12, 13, 31, 36, 39, 40"""
        med_types = [t for t, (_, c) in TYPE_CATEGORY_MAPPING.items() if c == "medium"]
        assert set(med_types) == {3, 11, 12, 13, 31, 36, 39, 40}

    def test_low_confidence_types(self):
        """low: 47 (近期每日数据 · 推测)"""
        low_types = [t for t, (_, c) in TYPE_CATEGORY_MAPPING.items() if c == "low"]
        assert low_types == [47]


class TestTypeNameReverseMapping:
    def test_type_name_matches_mapping(self):
        """TYPE_NAME == TYPE_CATEGORY_MAPPING 的 name 部分"""
        assert len(TYPE_NAME) == len(TYPE_CATEGORY_MAPPING)
        for t, name in TYPE_NAME.items():
            assert TYPE_CATEGORY_MAPPING[t][0] == name