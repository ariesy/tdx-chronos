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

import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional, Union

import pandas as pd

# 32 bytes / record · little-endian · §四.B
DAY_STRUCT = struct.Struct("<IIIIIfII")

# Sentinel for unknown source_zip when calling single-file parse
DEFAULT_SOURCE_ZIP = "hsjday.zip"


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
