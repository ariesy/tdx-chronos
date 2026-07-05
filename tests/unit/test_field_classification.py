"""Sprint 8 T4 · 财务报表分类提取子集测试

5 测试覆盖:
  TestExtractSubsets:   5 大报表提取 (4)
  TestExtractAll:       批量提取 + 统计 (1)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tdx_chronos.fin.field_classification import (
    extract_all_subsets,
    extract_balance_sheet,
    extract_cashflow_statement,
    extract_income_statement,
    extract_meta,
    extract_per_share_metrics,
    extract_ratios,
    extract_unknown,
    subset_stats,
)

# ---------------------------------------------------------------------
# fixture · 真跑最新 quarter
# ---------------------------------------------------------------------
PARSED_DIR = Path("/app/tdx-chronos/data/fin/parsed")
LATEST_PARQUET = PARSED_DIR / "gpcw20251231.parquet"


@pytest.fixture(scope="module")
def latest_df():
    if not LATEST_PARQUET.exists():
        pytest.skip(f"missing {LATEST_PARQUET}")
    return pd.read_parquet(LATEST_PARQUET)


# ---------------------------------------------------------------------
# TestExtractSubsets
# ---------------------------------------------------------------------
class TestExtractSubsets:
    def test_extract_income_statement(self, latest_df):
        """利润表子集 (60 fields)"""
        is_df = extract_income_statement(latest_df)
        assert isinstance(is_df, pd.DataFrame)
        # 字段数 ≥ 50 (利润表)
        assert len(is_df.columns) >= 50
        # 关键字段都在
        for f in ["五、净利润", "营业总收入(万元)", "归属于母公司所有者的净利润",
                   "营业利润", "三、营业利润"]:
            assert f in is_df.columns, f"{f} not in income_statement"
        # code (index) 保留
        assert latest_df.index.name == is_df.index.name
        assert len(is_df) == len(latest_df)

    def test_extract_balance_sheet(self, latest_df):
        """资产负债表子集 (123 fields)"""
        bs_df = extract_balance_sheet(latest_df)
        assert isinstance(bs_df, pd.DataFrame)
        # 字段数 ≥ 100
        assert len(bs_df.columns) >= 100
        # 关键字段
        for f in ["货币资金", "应收账款", "存货", "资产总计",
                   "短期借款", "负债合计",
                   "所有者权益（或股东权益）合计"]:
            assert f in bs_df.columns, f"{f} not in balance_sheet"

    def test_extract_cashflow_statement(self, latest_df):
        """现金流量表子集 (92 fields)"""
        cf_df = extract_cashflow_statement(latest_df)
        assert isinstance(cf_df, pd.DataFrame)
        # 字段数 ≥ 80
        assert len(cf_df.columns) >= 80
        # 关键字段 (含 3 大活动)
        for f in ["经营活动产生的现金流量净额",
                   "投资活动产生的现金流量净额",
                   "筹资活动产生的现金流量净额",
                   "五、现金及现金等价物净增加额"]:
            assert f in cf_df.columns, f"{f} not in cashflow"

    def test_extract_per_share_metrics(self, latest_df):
        """每股指标子集 (14 fields)"""
        ps_df = extract_per_share_metrics(latest_df)
        assert isinstance(ps_df, pd.DataFrame)
        # 字段数 ≥ 10
        assert len(ps_df.columns) >= 10
        # 关键字段
        for f in ["基本每股收益", "扣除非经常性损益每股收益",
                   "每股净资产", "每股未分配利润"]:
            assert f in ps_df.columns, f"{f} not in per_share"


# ---------------------------------------------------------------------
# TestExtractAll
# ---------------------------------------------------------------------
class TestExtractAll:
    def test_subset_stats_and_extract_all(self, latest_df):
        """subset_stats + extract_all_subsets 总和 = 585"""
        stats = subset_stats(latest_df)
        # 7 大类都应有字段
        assert all(stats[cat] >= 1 for cat in stats), \
            f"some category has 0 fields: {stats}"
        # 总和 = df 列数 (含 dup _dup2)
        total = sum(stats.values())
        assert total == len(latest_df.columns), \
            f"sum {total} != df cols {len(latest_df.columns)}"

        # extract_all_subsets 总和也应等于 total
        all_subsets = extract_all_subsets(latest_df)
        extracted_total = sum(len(s.columns) for s in all_subsets.values())
        assert extracted_total == total

        # 茅台 6 大类数据完整 (per_share, income, bs, cf, ratio, meta)
        if "600519" in latest_df.index.values:
            for cat in ["per_share", "income_statement", "balance_sheet",
                         "cashflow", "ratio", "meta"]:
                sub_df = all_subsets[cat]
                # 茅台应在所有子集里
                assert "600519" in sub_df.index.values, \
                    f"{cat} subset missing 茅台"
                # 子集至少有一些非零字段
                nonzero = (sub_df.loc["600519"] != 0).sum()
                assert nonzero > 0, f"{cat} 茅台全 0"