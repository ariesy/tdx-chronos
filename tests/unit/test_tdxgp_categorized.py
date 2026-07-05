"""Sprint 6 T2 · to_categorized(category) 单元测试

Test classes:
- TestToCategorizedBasic     · 5 category 过滤
- TestToCategorizedCode       · 单 code 过滤 (茅台 600519)
- TestToCategorizedErrors     · 错误处理
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from tdx_chronos.fin.tdxgp_record import TdxGpRecordReader


# 真实 records.parquet (Sprint 4b D1 + Sprint 6 修 bug)
RECORDS_PATH = Path("/app/tdx-chronos/data/gp/records.parquet")


# ---------------------------------------------------------------------
# TestToCategorizedBasic
# ---------------------------------------------------------------------
class TestToCategorizedBasic:
    def test_capital_share_has_data(self):
        df = TdxGpRecordReader.to_categorized(RECORDS_PATH, "capital_share")
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 1_000_000  # capital_share 应有 8000 万+
        assert "type_name" in df.columns

    def test_circulating_share_has_data(self):
        df = TdxGpRecordReader.to_categorized(RECORDS_PATH, "circulating_share")
        assert len(df) > 1_000_000  # ~450 万

    def test_shareholder_structure_has_data(self):
        df = TdxGpRecordReader.to_categorized(RECORDS_PATH, "shareholder_structure")
        assert len(df) > 1_000_000  # ~2000 万

    def test_finance_event_smaller(self):
        df = TdxGpRecordReader.to_categorized(RECORDS_PATH, "finance_event")
        # type=47 only ~570K
        assert len(df) > 100_000

    def test_rare_event_includes_long_tails(self):
        """Sprint 7: rare_event 包含 49-255 + 15 个长尾 (1-48 < 100K)"""
        df = TdxGpRecordReader.to_categorized(RECORDS_PATH, "rare_event")
        # Sprint 7: rare_event 包含 9 个长尾 (2, 23, 26, 28, 29, 30, 33, 34, 37)
        # + 6 个 (41, 42, 43, 44, 46, 48) + 49-255 (1 个)
        # 总 ~750K records
        assert len(df) >= 500_000, f"too small: {len(df):,}"
        assert len(df) <= 2_000_000, f"too large: {len(df):,}"

    def test_total_records_matches_full_data(self):
        """Sprint 7: 4 大类 + rare_event 总 records 验证

        实现要点: 单次 read_table + pc.is_in 过滤 · 不重复加载 parquet
        Sprint 7: 33 types 已分类 · rare_event 222 types
        """
        import pyarrow.parquet as pq
        import pyarrow.compute as pc
        from tdx_chronos.fin.tdxgp_types import CATEGORY_BUCKETS

        # 单次 read · 5 次 is_in
        table = pq.read_table(RECORDS_PATH, columns=["type"])
        total = 0
        for cat, types in CATEGORY_BUCKETS.items():
            mask = pc.is_in(table.column("type"), value_set=pa.array(types))
            cat_count = pc.sum(mask.cast("int64")).as_py()
            total += cat_count

        # Sprint 7 实证: 4 categories 已分类 ~119.5M + rare_event ~750K ≈ 120.3M
        assert total >= 119_000_000, f"total too small: {total:,}"
        assert total <= 121_000_000, f"total too large: {total:,}"

    def test_capital_share_dominates_4_categories(self):
        """capital_share 在 4 类别中应最大 (内存安全版)"""
        import pyarrow.parquet as pq
        import pyarrow.compute as pc
        from tdx_chronos.fin.tdxgp_types import CATEGORY_BUCKETS

        table = pq.read_table(RECORDS_PATH, columns=["type"])
        cat_sizes = {}
        for cat in ("capital_share", "circulating_share", "shareholder_structure",
                    "finance_event"):
            types = CATEGORY_BUCKETS[cat]
            mask = pc.is_in(table.column("type"), value_set=pa.array(types))
            cat_sizes[cat] = pc.sum(mask.cast("int64")).as_py()
        # capital_share 应 >= shareholder_structure (8 types vs 3 types)
        assert cat_sizes["capital_share"] >= cat_sizes["shareholder_structure"]
        # sanity: 4 大类都应有 > 100K records
        assert all(v > 100_000 for v in cat_sizes.values())


# ---------------------------------------------------------------------
# TestToCategorizedCode
# ---------------------------------------------------------------------
class TestToCategorizedCode:
    def test_maotai_capital_share(self):
        """Sprint 7: 茅台 (600519) capital_share 过滤 (27 types)"""
        df = TdxGpRecordReader.to_categorized(
            RECORDS_PATH, "capital_share", code="600519"
        )
        assert (df["code"] == "600519").all()
        # 茅台 capital_share 27 types 总和应 >= 10K
        assert len(df) >= 10_000
        # Sprint 7: 27 types 都可能出现 (不一定是全部)
        assert df["type"].nunique() >= 8  # Sprint 6 + Sprint 7 扩展

    def test_maotai_quarterly_snapshot_type1(self):
        """茅台 type=1 (季末快照) 104 records"""
        df = TdxGpRecordReader.to_categorized(
            RECORDS_PATH, "capital_share", code="600519"
        )
        type1 = df[df["type"] == 1]
        assert len(type1) == 104  # Sprint 4b D1 实证

    def test_type_name_field_added(self):
        df = TdxGpRecordReader.to_categorized(
            RECORDS_PATH, "capital_share", code="600519"
        )
        # type=1 → quarterly_snapshot_total
        sample = df[df["type"] == 1].head(1)
        assert sample["type_name"].iloc[0] == "quarterly_snapshot_total"


# ---------------------------------------------------------------------
# TestToCategorizedErrors
# ---------------------------------------------------------------------
class TestToCategorizedErrors:
    def test_invalid_category_raises(self):
        with pytest.raises(ValueError, match="Unknown category"):
            TdxGpRecordReader.to_categorized(RECORDS_PATH, "invalid_cat")

    def test_missing_path_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            TdxGpRecordReader.to_categorized(tmp_path / "missing.parquet", "capital_share")