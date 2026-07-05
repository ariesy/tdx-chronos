"""TDX-chronos · 股本 type 1-48 字段语义映射 (v1.1 Sprint 6)

§四.7 type 字段含义 (推测版 · 标注 confidence)

4 大类别 (覆盖 type 1-48):
  - capital_share        总股本变动/快照
  - circulating_share    流通股变动
  - shareholder_structure 股东结构/事件
  - finance_event        财务事件 (近期每日)

1 个罕见桶:
  - rare_event           type 49-255 · 每种 ~5000 records · 单一 unique code
                         (推测为特殊事件 / 大单交易 / 历史遗留)

公开 API:
- TYPE_CATEGORY_MAPPING: Dict[int, Tuple[str, str]]  (type → (name, confidence))
- TYPE_NAME:             Dict[int, str]              (type → name)
- CATEGORY_BUCKETS:      Dict[str, List[int]]        (5 类别)
- VALID_CONFIDENCES:     Set[str]                    (high/medium/low/unknown)

Confidence 含义:
  high    Sprint 6 摸排+公开数据验证一致
  medium  Sprint 6 摸排+合理推测 (需 Sprint 7+ 验证)
  low     Sprint 6 仅基于样本推测 (大概率正确, 但待验证)
  unknown type 49-255 · 暂未分类

v2.0 TODO: 用上市公司股本变动公告全文匹配验证 type 1-48 字段语义
"""
from __future__ import annotations

from typing import Dict, List, Set, Tuple


# ============================================================
# type → (field_name, confidence)
# ============================================================
TYPE_CATEGORY_MAPPING: Dict[int, Tuple[str, str]] = {
    # ===== 类别 1: 总股本 (capital_share) =====
    1:  ("quarterly_snapshot_total",  "high"),     # 104 季末快照 (茅台) · 高频 ~5000 stocks
    3:  ("outstanding_share_audit",   "medium"),   # 流通股对账 (2000+ per stock)
    11: ("shareholder_count_change",  "medium"),   # 股东户数变动 (7000+)
    12: ("dividend_distribution",     "medium"),   # 分红派息 (7000+)
    13: ("rights_offering",           "medium"),   # 配股 / 增发 (7000+)
    16: ("total_share_change_event",  "high"),     # 总股本变动 (10.5M · 最大)
    25: ("total_share_snapshot",      "high"),     # 总股本快照 (9.2M)
    27: ("outstanding_share_change",  "high"),     # 流通股变动 (10.1M)

    # ===== 类别 2: 流通股 (circulating_share) =====
    31: ("circulating_change_event",  "medium"),   # 流通股变动事件 (2.3M)
    36: ("circulating_snapshot",      "medium"),   # 流通股快照 (2.3M)

    # ===== 类别 3: 股东结构 (shareholder_structure) =====
    38: ("event_date_marker",         "high"),     # 事件日期标记 (8.6M · 仅 date+code)
    39: ("event_marker_only",         "medium"),   # 事件标记 (6.5M)
    40: ("change_with_existing",      "medium"),   # 变动+存量 (5.7M)

    # ===== 类别 4: 财务事件 (finance_event) =====
    47: ("recent_daily_record",       "low"),      # 近期每日数据 (570K · 推测)

    # ===== 类别 5: 罕见事件 (rare_event) =====
    # type 49-255 暂归 unknown
    # 单条 entry 不列, 见 CATEGORY_BUCKETS["rare_event"]
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
CATEGORY_BUCKETS: Dict[str, List[int]] = {
    "capital_share":         [1, 3, 11, 12, 13, 16, 25, 27],
    "circulating_share":     [31, 36],
    "shareholder_structure": [38, 39, 40],
    "finance_event":         [47],
    "rare_event":            list(range(49, 256)),  # 207 types · 每种 ~5000 records
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
# Sprint 6 type 1-48 总结
# ============================================================
# 已分类: 1, 3, 11, 12, 13, 16, 25, 27, 31, 36, 38, 39, 40, 47 (14 types · ~80% records)
# 未分类 (罕见但 type ≤ 48): 2, 4-10, 14-15, 17-24, 26, 28-30, 32-35, 37, 41-46, 48
#   · 推测这些是填充/placeholder/special_event
#   · v1.1 暂归 'rare_event' 或 'unknown'
# 未分类 (type 49-255): 全部归 'rare_event'