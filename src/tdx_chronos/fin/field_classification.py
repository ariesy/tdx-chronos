"""Sprint 8 T4 · 财务报表分类 - 提取子集 API

基于 Sprint 8 T2 已建立的 FIELD_CATEGORY_MAPPING (7 大类),
本模块提供"提取某分类字段子集"的实用 API:

  - extract_income_statement(df)      利润表子集
  - extract_balance_sheet(df)         资产负债表子集
  - extract_cashflow_statement(df)    现金流量表子集
  - extract_per_share_metrics(df)     每股指标子集
  - extract_ratios(df)                财务比率子集
  - extract_meta(df)                  元信息子集
  - extract_unknown(df)               未分类字段 (colXXX + _colXXX)

设计目标 (Sprint 8 T4):
  1. 复用 T2 FIELD_CATEGORY_MAPPING (单源真相)
  2. 子集字段顺序按 columns.py 原顺序 (便于阅读)
  3. 返回新 DataFrame (不修改原 df)
  4. code (index) 保留

Usage:
    >>> from tdx_chronos.fin.field_classification import extract_income_statement
    >>> df = pd.read_parquet('gpcw20251231.parquet')
    >>> is_df = extract_income_statement(df)
    >>> '五、净利润' in is_df.columns
    True
    >>> len(is_df.columns) >= 50
    True
"""
from __future__ import annotations

from typing import Dict, List

import pandas as pd

from .field_types import (
    CATEGORY_NAMES,
    FIELD_CATEGORY_MAPPING,
    categorize_columns,
    get_fields_by_category,
)


# ---------------------------------------------------------------------
# 内部 helpers
# ---------------------------------------------------------------------
def _extract(df: pd.DataFrame, category: str) -> pd.DataFrame:
    """提取某分类字段子集 (按 df 实际列顺序)"""
    if category not in CATEGORY_NAMES:
        raise ValueError(
            f"Unknown category: {category!r}. "
            f"Valid: {CATEGORY_NAMES}"
        )
    # 找该 category 在当前 df 中的字段 (保持原列顺序)
    target_fields = get_fields_by_category(category)
    present = [c for c in df.columns if c in target_fields]
    if not present:
        # 返回空 df 但保留 index
        return df.iloc[:0].copy()
    return df[present].copy()


# ---------------------------------------------------------------------
# 公开 API: 5 大财务报表 + 元信息 + 未知
# ---------------------------------------------------------------------
def extract_income_statement(df: pd.DataFrame) -> pd.DataFrame:
    """提取利润表子集 (~60 fields)"""
    return _extract(df, "income_statement")


def extract_balance_sheet(df: pd.DataFrame) -> pd.DataFrame:
    """提取资产负债表子集 (~123 fields)"""
    return _extract(df, "balance_sheet")


def extract_cashflow_statement(df: pd.DataFrame) -> pd.DataFrame:
    """提取现金流量表子集 (~92 fields)"""
    return _extract(df, "cashflow")


def extract_per_share_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """提取每股指标子集 (~14 fields)"""
    return _extract(df, "per_share")


def extract_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """提取财务比率子集 (~70 fields)"""
    return _extract(df, "ratio")


def extract_meta(df: pd.DataFrame) -> pd.DataFrame:
    """提取元信息子集 (~44 fields · 日期/股东/机构)"""
    return _extract(df, "meta")


def extract_unknown(df: pd.DataFrame) -> pd.DataFrame:
    """提取未分类字段 (~182 fields · colXXX + _colXXX)"""
    return _extract(df, "unknown")


# ---------------------------------------------------------------------
# 公开 API: 字典形式返回所有分类
# ---------------------------------------------------------------------
def extract_all_subsets(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """批量提取所有 7 大类子集

    Returns:
        Dict[category, DataFrame]
    """
    result: Dict[str, pd.DataFrame] = {}
    for cat in CATEGORY_NAMES:
        result[cat] = _extract(df, cat)
    return result


# ---------------------------------------------------------------------
# 公开 API: 字段统计
# ---------------------------------------------------------------------
def subset_stats(df: pd.DataFrame) -> Dict[str, int]:
    """返回当前 df 实际各分类的字段数 (仅在 df 中存在的字段)"""
    categorized = categorize_columns(df.columns.tolist())
    return {cat: len(cols) for cat, cols in categorized.items()}