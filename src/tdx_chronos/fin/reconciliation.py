"""Sprint 8 T3 · 财务三表勾稽

会计恒等式验证 (3 大勾稽):
  1. BalanceSheetEquation (BS):
     资产总计 ≈ 负债合计 + 所有者权益合计
     (通达信数据已严格勾稽, 误差 < 0.01%)

  2. CashflowReconciliation (CF):
     五、现金及现金等价物净增加额 ≈
     经营+投资+筹资现金流量净额 + 汇率变动 + 其他原因对现金的影响

  3. IncomeToBalanceSheet (IS-BS):
     净利润 ≈ 利润总额 - 所得税 + 影响净利润的其他科目
     (检查利润表内部勾稽)

设计目标 (Sprint 8 T3):
  1. 提供 ReconciliationReport (passed + checks + tolerance)
  2. 提供 reconcile_quarter(df) 单 quarter
  3. 提供 reconcile_quarters(parquet_path) 跨 quarter
  4. 容差 ±0.1% (财务数据正常误差)
  5. 异常 quarter 标记 + breakdown

Usage:
    >>> from tdx_chronos.fin.reconciliation import reconcile_quarter
    >>> df = pd.read_parquet('gpcw20251231.parquet')
    >>> report = reconcile_quarter(df)
    >>> report.passed
    True
    >>> report.total_stocks
    5529
    >>> report.failed_count
    0
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd


# ---------------------------------------------------------------------
# 容差 (默认 0.1% · 财务数据正常四舍五入误差)
# ---------------------------------------------------------------------
DEFAULT_TOLERANCE = 0.001  # 0.1%


# ---------------------------------------------------------------------
# Check 结果
# ---------------------------------------------------------------------
@dataclass
class CheckResult:
    """单个勾稽检查结果

    Attributes:
        name:           检查名 (e.g. "balance_sheet_equation")
        description:    描述 (e.g. "资产 = 负债 + 所有者权益")
        total_stocks:   总股票数
        passed_stocks:  通过的股票数
        failed_stocks:  失败的股票数 (容差外)
        mean_diff:      平均差异 (绝对值)
        max_diff:       最大差异 (绝对值)
        max_diff_ratio: 最大差异比例 (abs(diff) / abs(baseline))
        passed:         True if (failed_stocks == 0)
    """
    name: str
    description: str
    total_stocks: int
    passed_stocks: int
    failed_stocks: int
    mean_diff: float
    max_diff: float
    max_diff_ratio: float
    passed: bool

    @property
    def pass_rate(self) -> float:
        """通过率 (0-1)"""
        if self.total_stocks == 0:
            return 0.0
        return self.passed_stocks / self.total_stocks


# ---------------------------------------------------------------------
# Reconciliation Report
# ---------------------------------------------------------------------
@dataclass
class ReconciliationReport:
    """三表勾稽报告

    Attributes:
        report_date:    YYYYMMDD int (0 = unknown)
        total_stocks:   总股票数 (valid: 字段非零)
        passed:         True if 所有 checks 都 passed
        checks:         各 check 结果列表
        tolerance:      容差 (default 0.001)
    """
    report_date: int
    total_stocks: int
    passed: bool
    checks: List[CheckResult]
    tolerance: float = DEFAULT_TOLERANCE

    @property
    def failed_count(self) -> int:
        """失败的 check 数"""
        return sum(1 for c in self.checks if not c.passed)

    @property
    def all_pass_rates(self) -> List[float]:
        """所有 check 的通过率"""
        return [c.pass_rate for c in self.checks]

    def summary(self) -> str:
        """单行摘要"""
        lines = [f"ReconciliationReport({self.report_date}): "
                 f"{'PASS' if self.passed else 'FAIL'} · "
                 f"{self.total_stocks} stocks · "
                 f"{len(self.checks)} checks"]
        for c in self.checks:
            status = "✓" if c.passed else "✗"
            lines.append(
                f"  {status} {c.name}: {c.passed_stocks}/{c.total_stocks} "
                f"({c.pass_rate*100:.2f}%) · max_diff_ratio={c.max_diff_ratio:.4f}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------
# 单个 Check 实现
# ---------------------------------------------------------------------

def _check_balance_sheet_equation(
    df: pd.DataFrame, tolerance: float
) -> CheckResult:
    """勾稽 1: 资产 = 负债 + 所有者权益

    字段: 资产总计 / 负债合计 / 所有者权益（或股东权益）合计
    容差: tolerance (default 0.1%)
    """
    asset = df["资产总计"]
    liability = df["负债合计"]
    equity = df["所有者权益（或股东权益）合计"]

    # 有效样本 (3 个字段都非零)
    valid = (asset != 0) & (liability != 0) & (equity != 0)
    sub = df[valid]

    if len(sub) == 0:
        return CheckResult(
            name="balance_sheet_equation",
            description="资产 = 负债 + 所有者权益",
            total_stocks=0, passed_stocks=0, failed_stocks=0,
            mean_diff=0.0, max_diff=0.0, max_diff_ratio=0.0,
            passed=True,
        )

    # 差异: 资产 - 负债 - 权益
    diff = (asset[valid] - liability[valid] - equity[valid]).abs()
    ratio = diff / asset[valid].abs().replace(0, pd.NA)

    passed_mask = ratio <= tolerance
    passed_count = int(passed_mask.sum())
    failed_count = len(sub) - passed_count

    return CheckResult(
        name="balance_sheet_equation",
        description="资产 = 负债 + 所有者权益",
        total_stocks=len(sub),
        passed_stocks=passed_count,
        failed_stocks=failed_count,
        mean_diff=float(diff.mean()),
        max_diff=float(diff.max()),
        max_diff_ratio=float(ratio.max()) if hasattr(ratio, 'max') else 0.0,
        passed=(failed_count == 0),
    )


def _check_cashflow_reconciliation(
    df: pd.DataFrame, tolerance: float
) -> CheckResult:
    """勾稽 2: 现金净增加 = 经营+投资+筹资净额 + 汇率变动 + 其他原因

    字段: 五、现金及现金等价物净增加额
         + 经营活动产生的现金流量净额
         + 投资活动产生的现金流量净额
         + 筹资活动产生的现金流量净额
         + 四、汇率变动对现金的影响
         + 四(2)、其他原因对现金的影响
    容差: tolerance (default 0.1%)
    """
    net_increase = df["五、现金及现金等价物净增加额"]
    operating = df["经营活动产生的现金流量净额"]
    investing = df["投资活动产生的现金流量净额"]
    financing = df["筹资活动产生的现金流量净额"]
    fx_impact = df["四、汇率变动对现金的影响"]
    other_impact = df["四(2)、其他原因对现金的影响"]

    # 有效样本 (现金净增加非零)
    valid = net_increase != 0
    sub = df[valid]

    if len(sub) == 0:
        return CheckResult(
            name="cashflow_reconciliation",
            description="现金净增加 = 经营+投资+筹资净额 + 汇率 + 其他",
            total_stocks=0, passed_stocks=0, failed_stocks=0,
            mean_diff=0.0, max_diff=0.0, max_diff_ratio=0.0,
            passed=True,
        )

    # 计算三表 + 汇率 + 其他 之和 vs 现金净增加
    cf_sum = (operating[valid] + investing[valid] + financing[valid]
              + fx_impact[valid] + other_impact[valid])
    diff = (cf_sum - net_increase[valid]).abs()
    ratio = diff / net_increase[valid].abs().replace(0, pd.NA)

    passed_mask = ratio <= tolerance
    passed_count = int(passed_mask.sum())
    failed_count = len(sub) - passed_count

    return CheckResult(
        name="cashflow_reconciliation",
        description="现金净增加 = 经营+投资+筹资净额 + 汇率 + 其他",
        total_stocks=len(sub),
        passed_stocks=passed_count,
        failed_stocks=failed_count,
        mean_diff=float(diff.mean()),
        max_diff=float(diff.max()),
        max_diff_ratio=float(ratio.max()) if hasattr(ratio, 'max') else 0.0,
        passed=(failed_count == 0),
    )


def _check_income_to_balance_sheet(
    df: pd.DataFrame, tolerance: float
) -> CheckResult:
    """勾稽 3: 利润表内部勾稽 · 净利润 = 利润总额 - 所得税 + 影响净利润的其他科目

    字段: 五、净利润 / 四、利润总额 / 减：所得税 / 加：影响净利润的其他科目
    容差: tolerance (default 0.1%)
    """
    net_profit = df["五、净利润"]
    total_profit = df["四、利润总额"]
    income_tax = df["减：所得税"]
    other_impact = df["加：影响净利润的其他科目"]

    # 有效样本
    valid = net_profit != 0
    sub = df[valid]

    if len(sub) == 0:
        return CheckResult(
            name="income_to_balance_sheet",
            description="净利润 = 利润总额 - 所得税 + 影响净利润的其他科目",
            total_stocks=0, passed_stocks=0, failed_stocks=0,
            mean_diff=0.0, max_diff=0.0, max_diff_ratio=0.0,
            passed=True,
        )

    # 验证: 净利润 ≈ 利润总额 - 所得税 + 其他影响
    expected = total_profit[valid] - income_tax[valid] + other_impact[valid]
    diff = (expected - net_profit[valid]).abs()
    ratio = diff / net_profit[valid].abs().replace(0, pd.NA)

    passed_mask = ratio <= tolerance
    passed_count = int(passed_mask.sum())
    failed_count = len(sub) - passed_count

    return CheckResult(
        name="income_to_balance_sheet",
        description="净利润 = 利润总额 - 所得税 + 影响净利润的其他科目",
        total_stocks=len(sub),
        passed_stocks=passed_count,
        failed_stocks=failed_count,
        mean_diff=float(diff.mean()),
        max_diff=float(diff.max()),
        max_diff_ratio=float(ratio.max()) if hasattr(ratio, 'max') else 0.0,
        passed=(failed_count == 0),
    )


# ---------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------

def reconcile_quarter(
    df: pd.DataFrame,
    report_date: int = 0,
    tolerance: float = DEFAULT_TOLERANCE,
) -> ReconciliationReport:
    """对单个 quarter 的 df 跑全套三表勾稽

    Args:
        df:          财务季度 DataFrame (index='code', 585 columns)
        report_date: YYYYMMDD (0 = unknown)
        tolerance:   容差 (default 0.1%)

    Returns:
        ReconciliationReport
    """
    checks = [
        _check_balance_sheet_equation(df, tolerance),
        _check_cashflow_reconciliation(df, tolerance),
        _check_income_to_balance_sheet(df, tolerance),
    ]

    total_stocks = max(c.total_stocks for c in checks) if checks else 0
    all_passed = all(c.passed for c in checks)

    return ReconciliationReport(
        report_date=report_date,
        total_stocks=total_stocks,
        passed=all_passed,
        checks=checks,
        tolerance=tolerance,
    )


def reconcile_quarters(
    parquet_path: str | "Path",
    tolerance: float = DEFAULT_TOLERANCE,
) -> List[ReconciliationReport]:
    """跨所有 quarters (parquet path 是目录) 跑勾稽

    Args:
        parquet_path: 包含 gpcw*.parquet 的目录
        tolerance:    容差

    Returns:
        List[ReconciliationReport] · 跳过空 parquet (placeholder quarter)
    """
    from pathlib import Path
    base = Path(parquet_path)
    files = sorted(base.glob("gpcw*.parquet"))
    reports = []
    for f in files:
        df = pd.read_parquet(f)
        # 跳过空 parquet (placeholder quarter · 0 stocks / 0 cols)
        if len(df) == 0 or "资产总计" not in df.columns:
            continue
        # 从文件名提取 report_date
        try:
            rd = int(f.stem.replace("gpcw", ""))
        except ValueError:
            rd = 0
        reports.append(reconcile_quarter(df, report_date=rd, tolerance=tolerance))
    return reports