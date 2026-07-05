"""Sprint 8 T2 · 财务字段类型分类测试

10 测试覆盖:
  TestSchema:           field_types 模块结构 (3)
  TestPerShare:         每股指标字段 (1)
  TestCategorization:   7 大类分类 (3)
  TestCoverage:         全列覆盖率 (2)
  TestDupFields:        9 dup 字段 _dup2 后缀 (1)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tdx_chronos.fin.field_types import (
    CATEGORY_NAMES,
    FIELD_CATEGORY_MAPPING,
    categorize_columns,
    coverage_by_category,
    get_field_category,
    get_fields_by_category,
)
from tdx_chronos.fin.columns import columns


# ---------------------------------------------------------------------
# TestSchema
# ---------------------------------------------------------------------
class TestSchema:
    def test_module_imports(self):
        """FIELD_CATEGORY_MAPPING + 6+ 公开 API 可导入"""
        assert isinstance(FIELD_CATEGORY_MAPPING, dict)
        assert len(FIELD_CATEGORY_MAPPING) > 0
        # 7 大类
        assert len(CATEGORY_NAMES) == 7
        assert "per_share" in CATEGORY_NAMES
        assert "income_statement" in CATEGORY_NAMES
        assert "balance_sheet" in CATEGORY_NAMES
        assert "cashflow" in CATEGORY_NAMES
        assert "ratio" in CATEGORY_NAMES
        assert "meta" in CATEGORY_NAMES
        assert "unknown" in CATEGORY_NAMES

    def test_categories_have_fields(self):
        """每个 category 至少有 1 个字段"""
        cov = coverage_by_category()
        for cat in CATEGORY_NAMES:
            assert cov[cat] >= 1, f"{cat} has 0 fields"

    def test_unknown_includes_4_tail_columns(self):
        """unknown 类别必含 4 个 _col582-585"""
        unknown_fields = get_fields_by_category("unknown")
        for tail in ["_col582", "_col583", "_col584", "_col585"]:
            assert tail in unknown_fields, f"{tail} not in unknown"


# ---------------------------------------------------------------------
# TestPerShare
# ---------------------------------------------------------------------
class TestPerShare:
    def test_per_share_fields_classified(self):
        """每股指标字段 ≥ 10"""
        ps = get_fields_by_category("per_share")
        assert len(ps) >= 10
        # 关键字段都在
        for f in ["基本每股收益", "每股净资产", "每股未分配利润",
                   "扣非每股收益(单季度财务指标)", "稀释每股收益(元)",
                   "每股经营性现金流(元)"]:
            assert f in ps, f"{f} not in per_share"


# ---------------------------------------------------------------------
# TestCategorization
# ---------------------------------------------------------------------
class TestCategorization:
    def test_balance_sheet_fields_classified(self):
        """资产负债表字段 ≥ 50"""
        bs = get_fields_by_category("balance_sheet")
        assert len(bs) >= 50
        for f in ["货币资金", "应收账款", "存货", "资产总计",
                   "短期借款", "负债合计", "实收资本（或股本）",
                   "所有者权益（或股东权益）合计"]:
            assert f in bs, f"{f} not in balance_sheet"

    def test_income_statement_fields_classified(self):
        """利润表字段 ≥ 20"""
        is_ = get_fields_by_category("income_statement")
        assert len(is_) >= 20
        for f in ["五、净利润", "营业税金及附加", "销售费用",
                   "管理费用", "营业利润", "归属于母公司所有者的净利润"]:
            assert f in is_, f"{f} not in income_statement"

    def test_cashflow_fields_classified(self):
        """现金流量表字段 ≥ 15"""
        cf = get_fields_by_category("cashflow")
        assert len(cf) >= 15
        for f in ["经营活动产生的现金流量净额",
                   "投资活动产生的现金流量净额",
                   "筹资活动产生的现金流量净额",
                   "五、现金及现金等价物净增加额"]:
            assert f in cf, f"{f} not in cashflow"


# ---------------------------------------------------------------------
# TestCoverage
# ---------------------------------------------------------------------
class TestCoverage:
    def test_field_category_coverage_above_85pct(self):
        """对 columns.py 581 字段的覆盖率 >= 85%"""
        covered = sum(1 for c in columns if c in FIELD_CATEGORY_MAPPING)
        coverage = covered / len(columns)
        # Sprint 8 T2 真实数据: 100% (因为我们覆盖了所有 581 + 4 unknown)
        assert coverage >= 0.85, f"coverage {coverage:.2%} < 85%"

    def test_ratio_fields_classified(self):
        """财务比率字段 ≥ 10"""
        ratio = get_fields_by_category("ratio")
        assert len(ratio) >= 10
        for f in ["净资产收益率", "资产负债率(%)",
                   "流动比率(非金融类指标)",
                   "速动比率(非金融类指标)",
                   "销售毛利率(%)(非金融类指标)"]:
            assert f in ratio, f"{f} not in ratio"


# ---------------------------------------------------------------------
# TestDupFields
# ---------------------------------------------------------------------
class TestDupFields:
    def test_dup2_suffix_follows_category(self):
        """9 个 _dup2 字段自动跟随原分类"""
        # 净资产收益率 + _dup2 都是 ratio
        assert get_field_category("净资产收益率") == "ratio"
        assert get_field_category("净资产收益率_dup2") == "ratio"

        # 财务费用 + _dup2 都是 income_statement
        assert get_field_category("财务费用") == "income_statement"
        assert get_field_category("财务费用_dup2") == "income_statement"

        # 经营活动现金流量净额 + _dup2 都是 cashflow
        assert get_field_category("经营活动产生的现金流量净额") == "cashflow"
        assert get_field_category("经营活动产生的现金流量净额_dup2") == "cashflow"

        # 归属于母公司所有者的净利润 + _dup2 都是 income_statement
        assert get_field_category("归属于母公司所有者的净利润") == "income_statement"
        assert get_field_category("归属于母公司所有者的净利润_dup2") == "income_statement"


# ---------------------------------------------------------------------
# TestCategorizeColumns (集成 API)
# ---------------------------------------------------------------------
class TestCategorizeColumns:
    def test_categorize_columns_basic(self):
        """批量分类 API"""
        sample = ["基本每股收益", "货币资金", "五、净利润",
                   "经营活动产生的现金流量净额", "_col582"]
        result = categorize_columns(sample)
        assert result["per_share"] == ["基本每股收益"]
        assert result["balance_sheet"] == ["货币资金"]
        assert result["income_statement"] == ["五、净利润"]
        assert result["cashflow"] == ["经营活动产生的现金流量净额"]
        assert result["unknown"] == ["_col582"]

    def test_categorize_columns_empty(self):
        """空 list 返回空 dict"""
        result = categorize_columns([])
        for cat in CATEGORY_NAMES:
            assert result[cat] == []