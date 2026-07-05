"""Sprint 6 T2 · to_categorized(category) 单元测试

Test classes:
- TestToCategorizedBasic     · 5 category 过滤
- TestToCategorizedCode       · 单 code 过滤 (茅台 600519)
- TestToCategorizedErrors     · 错误处理
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
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

    def test_rare_event_empty_in_clean_data(self):
        """clean data (gpcw 过滤后) 只有 type 1-48 · rare_event (49-255) 为空"""
        df = TdxGpRecordReader.to_categorized(RECORDS_PATH, "rare_event")
        # Sprint 6 摸排真相: 修 bug 后 type 49-255 仅 1 records (data/gp/.dat metadata 残留)
        assert len(df) <= 100  # 几乎为 0 (gpcw 误识别修复后的清理效果)

    def test_total_records_matches_full_data(self):
        """4 大类 + rare_event = 总 records (Sprint 6 修 bug 后)

        注意: type 1-48 中有 28 个 type 未归入 4 大类 (e.g. type 2, 4-10 等)
        Sprint 6 v1.1 不解释这些 type · 所以总和 < 120.3M 是预期
        """
        total = 0
        for cat in ("capital_share", "circulating_share", "shareholder_structure",
                    "finance_event", "rare_event"):
            df = TdxGpRecordReader.to_categorized(RECORDS_PATH, cat)
            total += len(df)
        # Sprint 6 实证: 83.1M (14 types 已分类 · 占 1-48 总 120.3M 的 69%)
        # 剩余 37M (28 types · 未分类) 留 v2.0 验证
        assert total >= 80_000_000 and total <= 90_000_000

    def test_capital_share_dominates_4_categories(self):
        """capital_share 在 4 类别中应最大"""
        cat_sizes = {}
        for cat in ("capital_share", "circulating_share", "shareholder_structure",
                    "finance_event"):
            cat_sizes[cat] = len(TdxGpRecordReader.to_categorized(
                RECORDS_PATH, cat
            ))
        # capital_share 应 >= shareholder_structure (8 types vs 3 types)
        assert cat_sizes["capital_share"] >= cat_sizes["shareholder_structure"]


# ---------------------------------------------------------------------
# TestToCategorizedCode
# ---------------------------------------------------------------------
class TestToCategorizedCode:
    def test_maotai_capital_share(self):
        """茅台 (600519) capital_share 过滤"""
        df = TdxGpRecordReader.to_categorized(
            RECORDS_PATH, "capital_share", code="600519"
        )
        assert (df["code"] == "600519").all()
        # 茅台 8 types 总和应 >= 10000
        assert len(df) >= 10_000
        # 8 types 都应出现
        assert df["type"].nunique() == 8

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