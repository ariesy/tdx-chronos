"""TDX-chronos · TdxGpRecordReader (v1.1 Sprint 4b D1)

§四.7 股本 .dat 完整 13B records 解析器 (取代 Sprint 4a D2 简化版)

13B record layout (Sprint 4a D2 实证):
  uint8   type    (1-48 变动类型 · v1.1 不解释语义)
  uint32  date    (YYYYMMDD)
  uint32  value_1 (类型相关 uint32 · 含义待 Sprint 7 验证)
  uint32  value_2 (类型相关 uint32 · 含义待 Sprint 7 验证)

公开 API:
- TdxGpRecordReader.parse_file(path) -> GpRecordsFile
- TdxGpRecordReader.iter_quarters(raw_dir) -> Iterator[GpRecordsFile]
- TdxGpRecordReader.run_full_parse(raw_dir, output_dir, db_path)
    -> BatchParseSummary

输出 Parquet 格式:
  columns = ['type', 'date', 'value_1', 'value_2', 'market', 'code']
  index = RangeIndex (0..N-1) · 不索引 code (跨文件)

v1.1 决策:
  - 全部 7,580 文件合并为 1 大 Parquet (跨文件字典压缩, 类似 Sprint 4a D3 优化)
  - 节省: 1 个大 file 字典复用, 估值 200-400 MB
  - meta.db gp_metadata 升级 (含 record_count 实际)

用法:
    >>> from tdx_chronos.fin.tdxgp_record import TdxGpRecordReader
    >>> from pathlib import Path
    >>> info = TdxGpRecordReader.parse_file(
    ...     'tests/fixtures/fin/gp/gpsh600519.dat'
    ... )
    >>> info.record_count
    27032
    >>> info.type_distribution
    {1: 104, 3: 2000, 4: 1252, ...}
"""
from __future__ import annotations

import struct
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

RECORD_SIZE = 13
RECORD_FORMAT = "<B I I I"  # type + date + value_1 + value_2
MARKETS = ("sh", "sz", "bj")

# Parquet 输出 codec
PARQUET_CODEC = "zstd"
PARQUET_LEVEL = 3


@dataclass
class GpRecordsFile:
    """单股本 .dat 完整 records 解析结果

    Attributes:
        file_path:    完整路径
        market:       'sh' | 'sz' | 'bj' (从文件名)
        code:         6 位股票代码
        record_count: 13B records 总数
        type_distribution: {type: count} · 1-48 分布
        first_date:   最早 date (YYYYMMDD)
        last_date:    最晚 date (YYYYMMDD)
        parse_ok:     True/False
        error:        失败原因
    """

    file_path: Path
    market: str
    code: str
    record_count: int
    type_distribution: Dict[int, int] = field(default_factory=dict)
    first_date: Optional[int] = None
    last_date: Optional[int] = None
    parse_ok: bool = True
    error: Optional[str] = None


@dataclass
class BatchParseSummary:
    """批量解析总结"""

    raw_dir: Path
    output_path: Path
    start_at: datetime
    end_at: datetime
    results: List[GpRecordsFile]
    output_rows: int = 0
    output_bytes: int = 0

    @property
    def total_files(self) -> int:
        return len(self.results)

    @property
    def parsed_ok(self) -> int:
        return sum(1 for r in self.results if r.parse_ok)

    @property
    def parsed_failed(self) -> int:
        return sum(1 for r in self.results if not r.parse_ok)

    @property
    def total_records(self) -> int:
        return sum(r.record_count for r in self.results if r.parse_ok)

    @property
    def error_rate(self) -> float:
        return self.parsed_failed / self.total_files if self.total_files else 0.0

    @property
    def total_seconds(self) -> float:
        return (self.end_at - self.start_at).total_seconds()

    def by_market(self) -> dict:
        """按 market 统计 (parsed_ok only)"""
        stats: Dict[str, int] = {"sh": 0, "sz": 0, "bj": 0, "?": 0}
        for r in self.results:
            if r.parse_ok:
                stats[r.market] = stats.get(r.market, 0) + 1
        return stats


class TdxGpRecordReader:
    """§四.7 股本 .dat 完整 records 解析器

    设计: 全部 13B records 装 pd.DataFrame → 写 1 大 Parquet
    """

    @staticmethod
    def parse_file(path: str | Path) -> GpRecordsFile:
        """单 .dat → GpRecordsFile (含完整 record 统计)

        Args:
            path: gp{market}{code}.dat 文件路径

        Returns:
            GpRecordsFile
        """
        path = Path(path)
        if not path.exists():
            return GpRecordsFile(
                file_path=path,
                market="?",
                code="?",
                record_count=0,
                parse_ok=False,
                error="file not found",
            )

        file_size = path.stat().st_size
        if file_size == 0:
            return GpRecordsFile(
                file_path=path,
                market="?",
                code="?",
                record_count=0,
                parse_ok=False,
                error="empty file",
            )
        if file_size % RECORD_SIZE != 0:
            market, code = TdxGpReader._parse_filename_static(path.name)
            return GpRecordsFile(
                file_path=path,
                market=market,
                code=code,
                record_count=0,
                parse_ok=False,
                error=f"size {file_size} % {RECORD_SIZE} = {file_size % RECORD_SIZE}",
            )

        market, code = TdxGpReader._parse_filename_static(path.name)
        record_count = file_size // RECORD_SIZE

        # 解析全部 records · 统计 type + 找 first/last date
        type_counter: Counter = Counter()
        first_date = None
        last_date = None

        with open(path, "rb") as f:
            for _ in range(record_count):
                r = f.read(RECORD_SIZE)
                if len(r) < RECORD_SIZE:
                    break
                type_, date, _v1, _v2 = struct.unpack(RECORD_FORMAT, r)
                type_counter[type_] += 1
                if date > 0:  # skip date=0 placeholders
                    if first_date is None or date < first_date:
                        first_date = date
                    if last_date is None or date > last_date:
                        last_date = date

        return GpRecordsFile(
            file_path=path,
            market=market,
            code=code,
            record_count=record_count,
            type_distribution=dict(type_counter),
            first_date=first_date,
            last_date=last_date,
            parse_ok=True,
        )

    @staticmethod
    def _build_table_from_bytes(
        data: bytes,
        market: str,
        code: str,
    ) -> pa.Table:
        """bytes → pyarrow.Table (全 records · 流式高效)"""
        n = len(data) // RECORD_SIZE
        types_array = []
        dates_array = []
        values_1_array = []
        values_2_array = []
        markets_array = []
        codes_array = []

        for i in range(n):
            r = data[i * RECORD_SIZE:(i + 1) * RECORD_SIZE]
            t, d, v1, v2 = struct.unpack(RECORD_FORMAT, r)
            types_array.append(t)
            dates_array.append(d)
            values_1_array.append(v1)
            values_2_array.append(v2)
            markets_array.append(market)
            codes_array.append(code)

        return pa.table({
            "type": types_array,
            "date": dates_array,
            "value_1": values_1_array,
            "value_2": values_2_array,
            "market": markets_array,
            "code": codes_array,
        })

    @staticmethod
    def _build_dataframe_from_bytes(
        data: bytes,
        market: str,
        code: str,
    ) -> pd.DataFrame:
        """bytes → pd.DataFrame (legacy / 测试用)"""
        table = TdxGpRecordReader._build_table_from_bytes(data, market, code)
        return table.to_pandas()

    @staticmethod
    def iter_quarters(raw_dir: Path) -> Iterator[GpRecordsFile]:
        """遍历 raw_dir 下所有 gp*.dat · yield GpRecordsFile"""
        raw_dir = Path(raw_dir)
        for path in sorted(raw_dir.glob("gp*.dat")):
            yield TdxGpRecordReader.parse_file(path)

    @staticmethod
    def run_full_parse(
        raw_dir: Path,
        output_path: Path,
        db_path: Optional[Path] = None,
        max_files: Optional[int] = None,
    ) -> BatchParseSummary:
        """遍历所有股本 .dat · 全部 records 合并 → 1 大 Parquet

        Args:
            raw_dir:      tdxgp 解压目录
            output_path:   1 大 Parquet 路径 (e.g. data/gp/records.parquet)
            db_path:      meta.db 路径 (写 gp_metadata record_count 升级)
            max_files:    Optional 上限 · 测试用

        Returns:
            BatchParseSummary

        实现: 流式 ParquetWriter · 避免 17 GB 内存 spike
        """
        from tdx_chronos.meta.db import MetaDB

        raw_dir = Path(raw_dir)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        start_at = datetime.now(timezone.utc)

        # 1. parse metadata
        results: List[GpRecordsFile] = []
        output_rows = 0
        output_writer = None
        output_schema = None

        try:
            for i, info in enumerate(TdxGpRecordReader.iter_quarters(raw_dir)):
                if max_files and i >= max_files:
                    break
                results.append(info)
                if not info.parse_ok:
                    continue
                # 读 + build table
                try:
                    table = TdxGpRecordReader._build_table_from_bytes(
                        info.file_path.read_bytes(),
                        info.market, info.code,
                    )
                    if output_writer is None:
                        output_schema = table.schema
                        output_writer = pq.ParquetWriter(
                            output_path,
                            output_schema,
                            compression=PARQUET_CODEC,
                            compression_level=PARQUET_LEVEL,
                        )
                    output_writer.write_table(table)
                    output_rows += table.num_rows
                except Exception as e:
                    info.parse_ok = False
                    info.error = f"build table failed: {e}"
        finally:
            if output_writer is not None:
                output_writer.close()

        output_bytes = output_path.stat().st_size if output_path.exists() else 0

        # 2. 更新 meta.db (gp_metadata 升级)
        if db_path is not None:
            db = MetaDB(db_path)
            try:
                db.init_schema()
                for info in results:
                    db.record_gp_metadata(
                        file_path=str(info.file_path),
                        file_size=info.file_path.stat().st_size if info.file_path.exists() else 0,
                        record_count=info.record_count,
                        market=info.market,
                        code=info.code,
                        first_date=info.first_date,
                        last_date=info.last_date,
                        parse_ok=info.parse_ok,
                        error=info.error,
                    )
            finally:
                db.close()

        end_at = datetime.now(timezone.utc)
        return BatchParseSummary(
            raw_dir=raw_dir,
            output_path=output_path,
            start_at=start_at,
            end_at=end_at,
            results=results,
            output_rows=output_rows,
            output_bytes=output_bytes,
        )


# 委托给 tdxgp._parse_filename_static (避免重复)
class TdxGpReader:
    """占位 · 委托 _parse_filename_static"""
    @staticmethod
    def _parse_filename_static(name: str) -> tuple[str, str]:
        from .tdxgp import TdxGpReader as _R
        return _R._parse_filename(name)
