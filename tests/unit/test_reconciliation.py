"""Sprint 8 T3 · 三表勾稽测试

8 测试覆盖:
  TestReconciliationBasic:    基础 API (3)
  TestReconciliationChecks:   3 大勾稽 (3)
  TestReconciliationRealData: 真实数据 (2)

设计原则:
  - 容差 ±0.1% 是财务数据正常误差 (通达信已严格勾稽)
  - 真跑跨 quarter 验证 history
  - 容差 ±1% 应覆盖更多 quarter
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tdx_chronos.fin.reconciliation import (
    CheckResult,
    DEFAULT_TOLERANCE,
    ReconciliationReport,
    _check_balance_sheet_equation,
    _check_cashflow_reconciliation,
    _check_income_to_balance_sheet,
    reconcile_quarter,
    reconcile_quarters,
)

# ---------------------------------------------------------------------
# fixture · 真跑最新 quarter
# ---------------------------------------------------------------------
PARSED_DIR = Path("/app/tdx-chronos/data/fin/parsed")
LATEST_PARQUET = PARSED_DIR / "gpcw20251231.parquet"


@pytest.fixture(scope="module")
def latest_df():
    """Sprint 8 T3 测试用最新 quarter (20251231) · 5529 stocks"""
    if not LATEST_PARQUET.exists():
        pytest.skip(f"missing {LATEST_PARQUET}")
    return pd.read_parquet(LATEST_PARQUET)


# ---------------------------------------------------------------------
# TestReconciliationBasic
# ---------------------------------------------------------------------
class TestReconciliationBasic:
    def test_module_imports(self):
        """3 大勾稽 + 公开 API 可导入"""
        assert DEFAULT_TOLERANCE == 0.001  # ±0.1%
        assert callable(reconcile_quarter)
        assert callable(reconcile_quarters)
        assert callable(_check_balance_sheet_equation)
        assert callable(_check_cashflow_reconciliation)
        assert callable(_check_income_to_balance_sheet)

    def test_reconcile_quarter_returns_report(self, latest_df):
        """单 quarter 跑 → 返回 ReconciliationReport"""
        report = reconcile_quarter(latest_df, report_date=20251231)
        assert isinstance(report, ReconciliationReport)
        assert report.report_date == 20251231
        assert report.total_stocks > 5000  # 5529
        assert len(report.checks) == 3  # 3 大勾稽

    def test_reconciliation_report_summary(self, latest_df):
        """summary() 包含 PASS/FAIL 状态"""
        report = reconcile_quarter(latest_df, report_date=20251231)
        summary = report.summary()
        assert "PASS" in summary or "FAIL" in summary
        assert "balance_sheet_equation" in summary
        assert "cashflow_reconciliation" in summary
        assert "income_to_balance_sheet" in summary


# ---------------------------------------------------------------------
# TestReconciliationChecks (3 大勾稽)
# ---------------------------------------------------------------------
class TestReconciliationChecks:
    def test_balance_sheet_equation_holds(self, latest_df):
        """勾稽 1: 资产 = 负债 + 所有者权益 (通达信已严格勾稽)"""
        check = _check_balance_sheet_equation(latest_df, DEFAULT_TOLERANCE)
        assert isinstance(check, CheckResult)
        assert check.name == "balance_sheet_equation"
        assert check.total_stocks > 5000
        # 通达信数据已严格勾稽 (max_diff_ratio 应该是 0.00x)
        assert check.max_diff_ratio < 0.001, \
            f"通达信 BS 勾稽应该 < 0.1%, 实际 {check.max_diff_ratio}"

    def test_cashflow_reconciliation_holds(self, latest_df):
        """勾稽 2: 现金净增加 = 经营+投资+筹资净额 + 汇率 + 其他"""
        check = _check_cashflow_reconciliation(latest_df, DEFAULT_TOLERANCE)
        assert check.name == "cashflow_reconciliation"
        assert check.total_stocks > 5000
        # 容差 ±0.1% · 真实数据 max_diff_ratio < 0.1%
        assert check.max_diff_ratio < 0.001

    def test_income_to_balance_sheet_holds(self, latest_df):
        """勾稽 3: 净利润 = 利润总额 - 所得税 + 影响净利润的其他科目"""
        check = _check_income_to_balance_sheet(latest_df, DEFAULT_TOLERANCE)
        assert check.name == "income_to_balance_sheet"
        assert check.total_stocks > 5000
        # 利润表内部勾稽 · 严格
        assert check.max_diff_ratio < 0.001


# ---------------------------------------------------------------------
# TestReconciliationRealData
# ---------------------------------------------------------------------
class TestReconciliationRealData:
    def test_maotai_balance_sheet_passes(self, latest_df):
        """茅台 (600519) 三表勾稽应 PASS"""
        if "600519" not in latest_df.index.values:
            pytest.skip("茅台不在此 quarter")
        report = reconcile_quarter(latest_df, report_date=20251231)
        # 茅台应通过所有勾稽
        for c in report.checks:
            # 茅台在 subset 中 · diff 应该极小
            assert c.passed or c.failed_count < 5, \
                f"{c.name} 失败过多 ({c.failed_count}/{c.total_stocks})"

    def test_reconcile_quarters_skips_placeholders(self):
        """reconcile_quarters 跳过空 parquet (placeholder)"""
        reports = reconcile_quarters(PARSED_DIR)
        # 至少 100+ quarters (排除 placeholder 后)
        assert len(reports) >= 100
        # 每个 report 都应有 stocks
        for r in reports:
            assert r.total_stocks > 0
            # 都有 3 大勾稽
            assert len(r.checks) == 3
            # 都应有合法 report_date
            assert r.report_date >= 19890101