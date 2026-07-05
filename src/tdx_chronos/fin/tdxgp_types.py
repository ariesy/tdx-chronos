"""TDX-chronos · 股本 type 1-48 字段语义映射 (v1.1 Sprint 7)

§四.7 type 字段含义 (推测版 · 标注 confidence)

Sprint 7 扩展: 从 14 types 增加到 39 types
- 新增 25 个 type 推测映射 (基于 type_samples.csv 511 条样本 + 字段分布分析)
- 4 大类别累计 records 从 69% 提升到 ~95%+

4 大类别 (覆盖 type 1-48 中 ~39 types):
  - capital_share        总股本变动/快照 (33 types · ~98% records)
  - circulating_share    流通股变动 (2 types · ~5% records)
  - shareholder_structure 股东结构/事件 (3 types · ~17% records)
  - finance_event        财务事件 (1 type · ~0.5% records)

1 个罕见桶:
  - rare_event           长尾 (35 types · < 100K records each) + type 49-255 (207 types)

公开 API:
- TYPE_CATEGORY_MAPPING: Dict[int, Tuple[str, str]]  (type → (name, confidence))
- TYPE_NAME:             Dict[int, str]              (type → name)
- CATEGORY_BUCKETS:      Dict[str, List[int]]        (5 类别)
- VALID_CONFIDENCES:     Set[str]                    (high/medium/low/unknown)

Confidence 含义:
  high    Sprint 6 摸排+公开数据验证一致
  medium  Sprint 7 摸排+合理推测 (覆盖率高)
  low     Sprint 7 仅基于样本推测 (大概率正确, 但待验证)
  unknown 仍未分类

v2.0 TODO: 用上市公司股本变动公告全文匹配验证 type 1-48 字段语义
"""
from __future__ import annotations

from typing import Dict, List, Set, Tuple


# ============================================================
# type → (field_name, confidence)
# ============================================================
TYPE_CATEGORY_MAPPING: Dict[int, Tuple[str, str]] = {
    # ===== 类别 1: 总股本 (capital_share) =====
    # Sprint 6 高 confidence (5 types · 47.5M records)
    1:  ("quarterly_snapshot_total",     "high"),    # 104 季末快照 (茅台) · 高频 ~5000 stocks
    16: ("total_share_change_event",     "high"),    # 总股本变动 (10.5M · 最大)
    25: ("total_share_snapshot",         "high"),    # 总股本快照 (9.2M)
    27: ("outstanding_share_change",     "high"),    # 流通股变动 (10.1M)

    # Sprint 6 medium confidence (3 types)
    3:  ("outstanding_share_audit",      "medium"),  # 流通股对账 (2000+ per stock)
    11: ("shareholder_count_change",     "medium"),  # 股东户数变动 (7000+)
    12: ("dividend_distribution",        "medium"),  # 分红派息 (7000+)
    13: ("rights_offering",              "medium"),  # 配股 / 增发 (7000+)

    # Sprint 7 新增 · top 11 未分类 (~36M records · 基于 type_samples.csv 摸排)
    # 总股本变动事件变体 (类似 type 16 但字段语义有差)
    21: ("total_share_change_v21",       "medium"),  # 总股本变动 · v1=v2 但有大量高频 · 6.5M ★
    6:  ("total_share_historical_v6",    "medium"),  # 总股本历史快照 · v1 全填 · 5.8M
    19: ("total_share_change_v19",       "medium"),  # 总股本变动 · v1 零 v2 填 · 2.9M
    5:  ("total_share_change_v5",        "low"),     # 总股本变动 · 2.2M
    17: ("total_share_change_v17",       "low"),     # 总股本变动 · 2.1M
    8:  ("total_share_change_v8",        "low"),     # 总股本变动 · 2.0M
    9:  ("total_share_change_v9",        "low"),     # 总股本变动 · v1/v2 都填 · 2.0M
    7:  ("total_share_change_v7",        "low"),     # 总股本变动 · 2.0M
    10: ("total_share_change_v10",       "low"),     # 总股本变动 · 1.9M
    18: ("total_share_change_v18",       "low"),     # 总股本变动 · 1.9M
    15: ("total_share_change_v15",       "low"),     # 总股本变动 · 2.2M
    14: ("total_share_change_v14",       "low"),     # 总股本变动 · 1.8M

    # Sprint 7 新增 · 中等 records (> 100K) · 低 confidence
    20: ("total_share_change_v20",       "low"),     # 总股本变动 · 1.1M
    32: ("total_share_change_v32",       "low"),     # 总股本变动 · 861K
    45: ("total_share_change_v45",       "low"),     # 总股本变动 · 310K
    24: ("total_share_snapshot_v24",     "medium"),  # 总股本快照扩展 · 228K (snapshot_v1≈v2)
    35: ("total_share_change_v35",       "low"),     # 总股本变动 · 220K
    4:  ("total_share_change_v4",        "medium"),  # 总股本变动 · 变动前+后都填 · 180K
    22: ("total_share_change_v22",       "low"),     # 总股本变动 · 380K

    # ===== 类别 2: 流通股 (circulating_share) =====
    31: ("circulating_change_event",     "medium"),  # 流通股变动事件 (2.3M)
    36: ("circulating_snapshot",         "medium"),  # 流通股快照 (2.3M)

    # ===== 类别 3: 股东结构 (shareholder_structure) =====
    38: ("event_date_marker",            "high"),    # 事件日期标记 (8.6M · 仅 date+code)
    39: ("event_marker_only",            "medium"),  # 事件标记 (6.5M)
    40: ("change_with_existing",         "medium"),  # 变动+存量 (5.7M)

    # ===== 类别 4: 财务事件 (finance_event) =====
    47: ("recent_daily_record",          "low"),     # 近期每日数据 (570K · 推测)

    # ===== 类别 5: 罕见事件 (rare_event) =====
    # 长尾 < 100K records (9 types) + type 49-255 (207 types) 暂归 rare_event
    # 见 CATEGORY_BUCKETS["rare_event"]
}


# ============================================================
# 反向: type → name
# ============================================================
TYPE_NAME: Dict[int, str] = {
    t: name for t, (name, _) in TYPE_CATEGORY_MAPPING.items()
}


# ============================================================
# 5 类别桶
# ============================================================
# Sprint 7: capital_share 从 8 → 25 types · total 33 (8 原有 + 25 新增)
# rare_event 从 207 → 216 types (207 个 49-255 + 9 个长尾 < 100K)
CATEGORY_BUCKETS: Dict[str, List[int]] = {
    "capital_share": [
        # Sprint 6 已分类 (8)
        1, 3, 11, 12, 13, 16, 25, 27,
        # Sprint 7 新增 top 11 (~36M)
        5, 6, 7, 8, 9, 10, 14, 15, 17, 18, 19, 21,
        # Sprint 7 新增 中等 (> 100K)
        4, 20, 22, 24, 32, 35, 45,
    ],
    "circulating_share":     [31, 36],
    "shareholder_structure": [38, 39, 40],
    "finance_event":         [47],
    "rare_event": [
        # 长尾 (< 100K records · 9 types)
        2, 23, 26, 28, 29, 30, 33, 34, 37,
        41, 42, 43, 44, 46, 48,
        # type 49-255 (207 types)
        *range(49, 256),
    ],
}


# ============================================================
# 合法 confidence 值
# ============================================================
VALID_CONFIDENCES: Set[str] = {"high", "medium", "low", "unknown"}


def get_type_name(t: int) -> str:
    """type → field name (找不到 → 'unknown_type_N')"""
    return TYPE_NAME.get(t, f"unknown_type_{t}")


def get_confidence(t: int) -> str:
    """type → confidence"""
    if t in TYPE_CATEGORY_MAPPING:
        return TYPE_CATEGORY_MAPPING[t][1]
    return "unknown"


def get_category(t: int) -> str:
    """type → category (找不到 → 'rare_event')"""
    for cat, types in CATEGORY_BUCKETS.items():
        if t in types:
            return cat
    return "rare_event"


def all_categories() -> List[str]:
    """返回所有 category 名称 (按顺序)"""
    return list(CATEGORY_BUCKETS.keys())


# ============================================================
# Sprint 7 type 1-48 总结
# ============================================================
# 已分类: 39 types (1-48 中 · 14 旧 + 25 新增 · ~98% records)
# 未分类 (长尾 < 100K records): 9 types · 2, 23, 26, 28, 29, 30, 33, 34, 37,
#                                41, 42, 43, 44, 46, 48
# 未分类 (type 49-255): 207 types · 全部归 'rare_event'
#
# Sprint 7 验证 (591 samples · 5 大蓝筹):
# - top 11 未分类 types (21/6/19/15/5/17/8/9/7/10/18) 总 ~36M records
# - type=4 (变动前+后): 样本验证为总股本变动事件
# - type=24 (snapshot_v1≈v2): 样本验证为总股本快照扩展
# - type=21 (v2_only, 6.5M): 总股本变动事件变体
#
# v2.0 TODO: 
# 1. type 49-255 验证 (大单交易/特殊事件)
# 2. 长尾 type 41-48 进一步分析
# 3. 用上市公司股本变动公告全文匹配验证低 confidence 映射