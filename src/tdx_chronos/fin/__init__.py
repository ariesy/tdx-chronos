"""Sprint 4a · tdx-chronos 财务数据子包

包含:
- tdxfin.py   · 通达信 .dat 财务季报解析器
- columns.py  · 581 字段名 (从 vendor/mootdx/financial/columns.py 复制独立维护)

Schema 真相 (2026-07-04 Sprint 4a D1 实证):
- .dat header (4+4+2+12 = 22 bytes):
    <h  uint16  magic=1
    <I  uint32  report_date (YYYYMMDD)
    <H  uint16  max_count (stocks)
    <3L padding (12 bytes)
- stock header (14 bytes): <6s1c1L
    6s  code (ascii)
    1c  ?
    1L  offset into .dat body
- stock data: <{N}f where N = 581 (columns.py)

Phase 1 PoC 文档写的「264 字段」是错的 · 实际 581 字段
"""
from .columns import columns  # noqa: F401
from .tdxfin import TdxFinReader, QuarterData  # noqa: F401
from .tdxgp import TdxGpReader, GpFileInfo, BatchSummary  # noqa: F401

__all__ = [
    "columns",
    "TdxFinReader",
    "QuarterData",
    "TdxGpReader",
    "GpFileInfo",
    "BatchSummary",
]