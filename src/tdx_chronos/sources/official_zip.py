"""TDX 官方 .day zip 文件解析器（v1.1 Sprint 2）

§四.B schema (32 bytes/record · struct '<IIIIIfII'):
  - date:     uint32  (YYYYMMDD)
  - open:     int32   (价·×100)
  - high:     int32   (价·×100)
  - low:      int32   (价·×100)
  - close:    int32   (价·×100)
  - amount:   float32 (成交额·元·含小数位)
  - vol:      int32   (成交量·股)
  - reserved: int32   (TDX 内部状态· v1.1 不解析语义· 保留原值)

§四.D 输出 DataFrame 字段 (Parquet schema):
  date:        uint32  (YYYYMMDD)
  open:        float64 (÷100)
  high:        float64 (÷100)
  low:         float64 (÷100)
  close:       float64 (÷100)
  amount:      float64 (元)
  vol:         int32   (股)
  reserved:    int32   (原始值· 已实测: 0 / 1175 / 4816 / 65536 等多种形态)
  symbol:      string  (e.g. 'sh600000')
  market:      string  ('sh' / 'sz' / 'bj')
  source_zip:  string  ('hsjday.zip' / 'bjlday.zip' / ...)
  ingested_at: timestamp (UTC· 文件解析时间)

§四.D Parquet 命名: sh600000.parquet · sz300750.parquet · bj920193.parquet
"""
from __future__ import annotations

import logging
import struct
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional, Union

import pandas as pd

from tqdm import tqdm

# 32 bytes / record · little-endian · §四.B
DAY_STRUCT = struct.Struct("<IIIIIfII")

# Sentinel for unknown source_zip when calling single-file parse
DEFAULT_SOURCE_ZIP = "hsjday.zip"

logger = logging.getLogger(__name__)


@dataclass
class BatchSummary:
    """parse_hsjday_dir 运行总结

    Attributes:
        total_files:      出入文件数 (12,256)
        parsed_ok:        解析成功数
        parsed_failed:    解析失败数 (异常 · 记录到 download_log)
        elapsed_seconds:  总耗时
        bytes_read:       总输入字节
        parquet_bytes:    总输出字节 (磁盘占用)
        start_at:         起始时间 (UTC)
        end_at:           结束时间 (UTC)
    """

    total_files: int
    parsed_ok: int
    parsed_failed: int
    elapsed_seconds: float
    bytes_read: int
    parquet_bytes: int
    start_at: datetime
    end_at: datetime


@dataclass
class ParseResult:
    """解析单个 .day 文件的结果

    Attributes:
        symbol:        e.g. 'sh600000'
        market:        'sh' / 'sz' / 'bj'
        record_count:  解析成功记录数
        first_date:    上市首日 (YYYYMMDD)
        last_date:     最后交易日 (YYYYMMDD)
        df:            解析后 DataFrame (§四.D schema)
    """

    symbol: str
    market: str
    record_count: int
    first_date: int
    last_date: int
    df: pd.DataFrame


class OfficialZipParser:
    """TDX .day zip → Parquet 解析器

    v1.1 主路径入口 (Sprint 2 末稳定 · Sprint 3b 全量运用):
      - parse_day_file: 单 .day → DataFrame
      - iter_day_files:  yield 全部 .day 路径
      - parse_to_parquet: 单文件 → Parquet 写盘

    用法:
      >>> parser = OfficialZipParser()
      >>> result = parser.parse_day_file(Path('tests/fixtures/day/sh/sh600000.day'))
      >>> result.df[['date', 'open', 'high', 'low', 'close']].head(3)
    """

    def __init__(self, source_zip: str = DEFAULT_SOURCE_ZIP):
        self.source_zip = source_zip

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def parse_day_file(self, day_path: Path) -> ParseResult:
        """解析单个 .day 文件 → ParseResult

        Args:
            day_path: .day 文件路径 (e.g. sh/lday/sh600000.day)
                      目录前缀 sh/sz/bj 用于推导 market

        Returns:
            ParseResult 包含 DataFrame (按 §四.D schema)

        Raises:
            ValueError: 文件路径不包含合法 sh/sz/bj 目录前缀
            struct.error: 文件大小不是 32 字节倍数
        """
        day_path = Path(day_path)
        symbol, market = self._symbol_and_market_from_path(day_path)

        raw = day_path.read_bytes()
        record_count = len(raw) // DAY_STRUCT.size
        records = DAY_STRUCT.iter_unpack(raw)

        df = self._records_to_df(records, symbol, market)

        return ParseResult(
            symbol=symbol,
            market=market,
            record_count=record_count,
            first_date=int(df["date"].iloc[0]) if len(df) else 0,
            last_date=int(df["date"].iloc[-1]) if len(df) else 0,
            df=df,
        )

    def iter_day_files(
        self, hsjday_raw_dir: Union[str, Path]
    ) -> Iterator[Path]:
        """流式遍历 hsjday_raw/{sh,sz,bj}/lday/*.day

        Args:
            hsjday_raw_dir: 顶层目录 (内含 sh/sz/bj 子目录)

        Yields:
            .day 文件路径 · 按字典序
        """
        root = Path(hsjday_raw_dir)
        for market_dir in sorted(root.iterdir()):
            if not market_dir.is_dir():
                continue
            market_name = market_dir.name  # 'sh' / 'sz' / 'bj'
            if market_name not in {"sh", "sz", "bj"}:
                continue
            lday = market_dir / "lday"
            if not lday.is_dir():
                continue
            for day_file in sorted(lday.glob("*.day")):
                yield day_file

    def parse_to_parquet(
        self,
        day_path: Path,
        output_dir: Path,
    ) -> Path:
        """单 .day → Parquet (§四.D 命名)

        Args:
            day_path:   e.g. sh/lday/sh600000.day
            output_dir: 根目录 (内含 sh/sz/bj 子目录)

        Returns:
            写出 Parquet 路径 · e.g. output_dir/sh/sh600000.parquet
        """
        result = self.parse_day_file(day_path)
        market = result.market
        symbol = result.symbol

        target = Path(output_dir) / market / f"{symbol}.parquet"
        target.parent.mkdir(parents=True, exist_ok=True)
        result.df.to_parquet(target, index=False)
        return target

    # ---------------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------------

    def _records_to_df(
        self,
        records: Iterator[tuple],
        symbol: str,
        market: str,
    ) -> pd.DataFrame:
        """struct 解出 records → DataFrame (§四.D schema)"""
        rows = []
        for date, op, hi, lo, cl, amount, vol, reserved in records:
            rows.append(
                {
                    "date": date,            # uint32 YYYYMMDD
                    "open": op / 100.0,      # float64
                    "high": hi / 100.0,
                    "low": lo / 100.0,
                    "close": cl / 100.0,
                    "amount": float(amount), # float64
                    "vol": int(vol),         # int32 股
                    "reserved": int(reserved),  # 原始 int32 · 不解释语义
                    "symbol": symbol,
                    "market": market,
                    "source_zip": self.source_zip,
                    "ingested_at": datetime.now(timezone.utc),
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _symbol_and_market_from_path(day_path: Path) -> tuple[str, str]:
        """从 .day 路径推导 (symbol, market)

        Args:
            day_path: sh/lday/sh600000.day → ('sh600000', 'sh')
                      sz/lday/sz300750.day → ('sz300750', 'sz')

        Returns:
            (symbol, market)

        Raises:
            ValueError: 路径不包含 sh/sz/bj 目录
        """
        parts = day_path.parts
        # sh/sz/bj 标记在路径中的某一段
        market = None
        for p in parts:
            if p in {"sh", "sz", "bj"}:
                market = p
                break
        if market is None:
            raise ValueError(
                f"Cannot infer market from path: {day_path} "
                f"(no sh/sz/bj segment)"
            )
        symbol = day_path.stem  # 'sh600000' / 'sz300750' / 'bj920193'
        return symbol, market


# ---------------------------------------------------------------------
# Batch API (Sprint 2 D2 上午 · 流式全量处理)
# ---------------------------------------------------------------------

def parse_hsjday_dir(
    raw_dir: Union[str, Path],
    output_dir: Union[str, Path],
    db: Optional["MetaDB"] = None,  # type: ignore[name-defined]  # forward ref
    show_progress: bool = True,
) -> Iterator[ParseResult]:
    """流式遍历 hsjday_raw/{sh,sz,bj}/lday/*.day · 解析 + 写 Parquet + 写 meta.db

    设计原则:
    - Generator yield (内存友好 · 12,256 不全驻)
    - 单线程 (v1.1 简化 · Sprint 6 重试化减后再并行化考虑)
    - tqdm 进度条
    - 坏文件不 crash · 记录到 download_log (parse_status='failed')

    Args:
        raw_dir:        顶层 (e.g. /tmp/tdx_data/day/hsjday_raw)
        output_dir:     Parquet 根 (e.g. /app/tdx-chronos/data/parquet)
        db:             可选 MetaDB · 提供则同步写 symbol_metadata + download_log
        show_progress:  tqdm 进度条

    Yields:
        ParseResult · 解析 .day 后 (含 df + 元数据)

    Raises:
        (不抛 · 异常文件被记录到 download_log)
    """
    parser = OfficialZipParser()
    raw_dir = Path(raw_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = list(parser.iter_day_files(raw_dir))
    iterator = (
        tqdm(files, desc="Parsing .day", unit="file")
        if show_progress
        else files
    )

    for day_path in iterator:
        try:
            result = parser.parse_day_file(day_path)
            target = output_dir / result.market / f"{result.symbol}.parquet"
            target.parent.mkdir(parents=True, exist_ok=True)
            result.df.to_parquet(target, index=False)
            if db is not None:
                db.record_symbol(
                    symbol=result.symbol,
                    market=result.market,
                    first_listing_date=result.first_date,
                    record_count=result.record_count,
                    source_zip=parser.source_zip,
                    parquet_path=str(target),
                )
            yield result
        except Exception as exc:
            logger.error("Failed to parse %s: %s", day_path, exc)
            if db is not None:
                db.record_download(
                    zip_name=parser.source_zip,
                    mirror=None,
                    size_bytes=day_path.stat().st_size
                    if day_path.exists() else None,
                    sha256=None,
                    parse_status="failed",
                    error_msg=str(exc)[:500],
                )
            # 失败仍然 yield 一个错误标记 · 调用方可计数
            yield ParseResult(
                symbol=day_path.stem,
                market="?",
                record_count=0,
                first_date=0,
                last_date=0,
                df=pd.DataFrame(),
            )


def run_full_parse(
    raw_dir: Union[str, Path],
    output_dir: Union[str, Path],
    db_path: Union[str, Path],
    show_progress: bool = True,
) -> BatchSummary:
    """一键全量跑 (Sprint 2 D2 上午主入口)

    用法:
        >>> summary = run_full_parse(
        ...     '/tmp/tdx_data/day/hsjday_raw',
        ...     '/app/tdx-chronos/data/parquet',
        ...     '/app/tdx-chronos/data/meta/meta.db',
        ... )
        >>> summary.parsed_ok
        12256
    """
    from tdx_chronos.meta.db import MetaDB  # 避免循环引用

    start = time.monotonic()
    start_at = datetime.now(timezone.utc)
    bytes_read = 0
    parquet_bytes = 0
    parsed_ok = 0
    parsed_failed = 0

    with MetaDB(db_path) as db:
        db.init_schema()
        for result in parse_hsjday_dir(
            raw_dir, output_dir, db=db, show_progress=show_progress,
        ):
            if result.market == "?":
                parsed_failed += 1
            else:
                parsed_ok += 1
                # 累计磁盘用量
                target = (
                    Path(output_dir) / result.market
                    / f"{result.symbol}.parquet"
                )
                if target.exists():
                    parquet_bytes += target.stat().st_size
                # 累计输入字节
                src = Path(raw_dir) / result.market / "lday" / f"{result.symbol}.day"
                if src.exists():
                    bytes_read += src.stat().st_size

    elapsed = time.monotonic() - start
    return BatchSummary(
        total_files=parsed_ok + parsed_failed,
        parsed_ok=parsed_ok,
        parsed_failed=parsed_failed,
        elapsed_seconds=elapsed,
        bytes_read=bytes_read,
        parquet_bytes=parquet_bytes,
        start_at=start_at,
        end_at=datetime.now(timezone.utc),
    )
