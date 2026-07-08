"""TDX-chronos · TdxFinReader (v1.1 Sprint 4a D1)

§四.C .dat 财务解析器 schema (Phase 1 PoC 真相 + 2026-07-04 Sprint 4a 实证修正)

文件结构:
  Header (22 bytes):
    uint16 magic=1        offset 0
    uint32 report_date    offset 2   YYYYMMDD
    uint16 max_count      offset 6   stocks in this .dat
    uint32[3] padding     offset 8   (12 bytes · 含义未公开)
  Stock items (max_count * 14 bytes):
    uint8[6] code         ascii · '000001' / 'sh600519' 等
    uint8    ?            unknown
    uint32   offset       into .dat body
  Stock data (per stock):
    uint32[N] floats      N = 581 (column count from columns.py)
    顺序与 columns.py 严格对应 · 起始是 ['报告日期','基本每股收益',...]

修正记录:
  Phase 1 PoC 文档写的「264 字段 × 4 = 1056 B/stock」是错的 (sina/old data)
  v1.1 实测: gpcw20260331.dat = 12.96 MB · 5,524 stocks · 581 floats/stock
    = 5,524 × (14 + 581×4) = 5,524 × 2,338 = 12.91 MB ✓

设计:
  - 不依赖 vendor/mootdx · 直接 struct 二进制拆 .dat
  - 字段名复用 fin/columns.py (从 vendor 复制独立维护)
  - 返回 pd.DataFrame (index=code · columns=581 中文 + report_date)
  - 支持 .dat 直接读 / .zip 解压读
  - placeholder 164B zip 检测 (未来季占位) → 跳过

用法:
    >>> from tdx_chronos.fin.tdxfin import TdxFinReader
    >>> df = TdxFinReader.to_data('gpcw20260331.dat')
    >>> df.shape
    (5524, 582)  # 5524 stocks × (581 floats + report_date)
"""
from __future__ import annotations

import re
import struct
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from .columns import columns

HEADER_PACK_FORMAT = "<hIH3L"  # 20 bytes: magic h, date I, count H, 3xL padding
STOCK_HEADER_PACK_FORMAT = "<6s1c1L"  # 11 bytes: code, ?, offset

# Phase 1 PoC 文档「264 字段」是错的 · v1.1 Sprint 4a D1 实测:
#   gpcw20251231.dat: 5529 stocks · 584 floats/stock
#   gpcw20260331.dat: 5524 stocks · 584 floats/stock
#   1 stock = 11 byte header + 584 floats × 4 = 2347 bytes
# 584 字段 vs columns.py 581 字段 → 末尾 3 字段 columns.py 缺失
ACTUAL_FIELDS_PER_STOCK = 584  # rows[2:586] 的 floats

# columns.py 581 = 1 'report_date' + 580 中文 字段名
# 实际 .dat 1 stock = 1 code + 1 report_date + 584 floats = 586 elements
# rows[1:] = 1 report_date + 584 floats = 585 columns
# columns.py 已经含 'report_date' · 还需补 584 - 580 = 4 未知字段
TAIL_UNKNOWN_COLUMNS = [
    f"_col{i+582}" for i in range(ACTUAL_FIELDS_PER_STOCK - (len(columns) - 1))
]  # ['_col582', '_col583', '_col584', '_col585'] = 4 未知字段

# 164B placeholder zip detection (未来季 · 未披露)
PLACEHOLDER_ZIP_SIZE = 164
PLACEHOLDER_DAT_SIZE = 20  # 占位 .dat 仅 20 字节


@dataclass
class IncrementalSummary:
    """T2 · parse_quarters_incremental 返回值"""
    skipped: int
    parsed: int
    failed: int
    elapsed_seconds: float


@dataclass
class QuarterData:
    """一个季度的财务数据 + 元数据

    Attributes:
        df:            解析后的 DataFrame (index=code · 5524 × 582)
        report_date:   YYYYMMDD int
        raw_path:      原始 .dat/.zip 路径
        is_placeholder: True if 164B zip (未来季)
    """

    df: pd.DataFrame
    report_date: int
    raw_path: Path
    is_placeholder: bool


class TdxFinReader:
    """§四.C .dat 财务解析器 (v1.1 Sprint 4a D1)

    公开 API:
        to_data(path, header='zh') -> pd.DataFrame
        parse_quarter(path) -> QuarterData
        iter_quarters(raw_dir, ...) -> Iterator[QuarterData]
        run_full_parse(raw_dir, output_dir, db_path) -> BatchSummary
    """

    # ---------------------------------------------------------------------
    # 单文件解析
    # ---------------------------------------------------------------------

    @staticmethod
    def to_data(path: str | Path, header: str = "zh") -> pd.DataFrame:
        """单 .dat 或 .zip → pd.DataFrame

        Args:
            path:   .dat 直接读  /  .zip 自动解压
            header: 'zh' (581 中文字段 · 默认) / 'en' ('col1','col2',...)

        Returns:
            pd.DataFrame with index=code · 5524 行 × 582 列

        Raises:
            ValueError: 占位文件 (164B zip / 20B dat)
            FileNotFoundError: 文件不存在
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"file not found: {path}")

        # 占位文件检测
        if path.suffix == ".zip" and path.stat().st_size <= PLACEHOLDER_ZIP_SIZE:
            raise ValueError(
                f"placeholder zip ({path.stat().st_size} bytes): "
                f"{path.name} is a future-quarter placeholder"
            )
        if path.suffix == ".dat" and path.stat().st_size <= PLACEHOLDER_DAT_SIZE:
            raise ValueError(
                f"placeholder dat ({path.stat().st_size} bytes): "
                f"{path.name} has no financial data"
            )

        # 解压 .zip 到临时 .dat
        if path.suffix == ".zip":
            with zipfile.ZipFile(path, "r") as zf:
                dat_names = [n for n in zf.namelist() if n.endswith(".dat")]
                if not dat_names:
                    raise ValueError(f"no .dat in zip: {path}")
                with zf.open(dat_names[0]) as zf_dat:
                    dat_bytes = zf_dat.read()
            data_tuple = TdxFinReader._parse_dat_bytes(dat_bytes)
        elif path.suffix == ".dat":
            data_tuple = TdxFinReader._parse_dat_bytes(path.read_bytes())
        else:
            raise ValueError(f"unsupported extension: {path.suffix}")

        # 装 DataFrame
        df = TdxFinReader._results_to_df(data_tuple, header=header)
        return df

    @staticmethod
    def _parse_dat_bytes(data: bytes) -> tuple[int, list[tuple]]:
        """解析 .dat bytes → (report_date, [(code, report_date, *floats), ...])

        Returns:
            (report_date, results)
        """
        header_size = struct.calcsize(HEADER_PACK_FORMAT)
        stock_header_size = struct.calcsize(STOCK_HEADER_PACK_FORMAT)

        # Header
        stock_header = struct.unpack(HEADER_PACK_FORMAT, data[:header_size])
        max_count = stock_header[2]
        report_date = stock_header[1]
        report_size = stock_header[4]  # bytes
        report_fields_count = int(report_size / 4)
        report_pack_format = f"<{report_fields_count}f"
        report_data_size = struct.calcsize(report_pack_format)

        # Stock items
        results: list[tuple] = []
        for stock_idx in range(max_count):
            item_off = header_size + stock_idx * stock_header_size
            si = data[item_off:item_off + stock_header_size]
            stock_item = struct.unpack(STOCK_HEADER_PACK_FORMAT, si)
            code = stock_item[0].decode("utf-8", errors="replace").strip()
            data_offset = stock_item[2]

            # 检查 offset 落在合理范围
            if data_offset + report_data_size > len(data):
                # 数据截断（罕见）· skip
                continue

            info_data = data[data_offset:data_offset + report_data_size]
            cw_info = struct.unpack(report_pack_format, info_data)
            one_record = (code, report_date) + cw_info
            results.append(one_record)

        return report_date, results

    @staticmethod
    def _results_to_df(
        data_tuple: tuple[int, list[tuple]],
        header: str = "zh",
    ) -> pd.DataFrame:
        """(report_date, results) → DataFrame

        Args:
            data_tuple:  _parse_dat_bytes 返回值
            header:      'zh' / 'en'

        Returns:
            pd.DataFrame · index='code'
        """
        _report_date, rows = data_tuple
        if not rows:
            return pd.DataFrame()

        # rows layout: (code, report_date, f1, f2, ..., f584)
        #     → code 作为 index · report_date 在 columns[0] (同名) · 584 floats 在 columns[1:]
        # columns.py 581 + TAIL 3 unknown = 584
        # rows[0] = code  ·  index
        # rows[1] = report_date  ·  columns[0] = 'report_date'
        # rows[2:586] = 584 floats  ·  columns[1:585]
        if header == "zh":
            zh_cols = list(columns) + TAIL_UNKNOWN_COLUMNS  # 584
            # Dedupe: columns.py 有 9 个重名列 (v1.1 vendor 已知问题)
            # 出现 N 次的列加后缀 _dup2, _dup3 ...
            seen = {}
            unique_cols = []
            for c in zh_cols:
                if c in seen:
                    seen[c] += 1
                    unique_cols.append(f"{c}_dup{seen[c]}")
                else:
                    seen[c] = 1
                    unique_cols.append(c)
            # set_index 后 columns 变为 zh_cols[0:584] (无 'code' )
            df = pd.DataFrame(
                data=[r[1:] for r in rows],  # 去掉 code (rows[0])
                columns=unique_cols,
            )
            df.index = pd.Index([r[0] for r in rows], name="code")
        else:
            n_fields = len(rows[0]) - 2
            df_cols = ["report_date"] + [f"col{i+1}" for i in range(n_fields)]
            df = pd.DataFrame(
                data=[r[1:] for r in rows],
                columns=df_cols,
            )
            df.index = pd.Index([r[0] for r in rows], name="code")
        return df

    # ---------------------------------------------------------------------
    # 季度封装
    # ---------------------------------------------------------------------

    @staticmethod
    def parse_quarter(
        path: str | Path,
        output_dir: Path | None = None,
    ) -> QuarterData:
        """单 .dat/.zip → QuarterData (含 DataFrame + 元数据)

        Args:
            path:       .dat 或 .zip 路径
            output_dir: Optional Parquet 输出目录 · 提供则写入 <quarter>.parquet

        Returns:
            QuarterData
        """
        path = Path(path)
        is_placeholder = (
            (path.suffix == ".zip" and path.stat().st_size <= PLACEHOLDER_ZIP_SIZE)
            or (path.suffix == ".dat" and path.stat().st_size <= PLACEHOLDER_DAT_SIZE)
        )
        if is_placeholder:
            return QuarterData(
                df=pd.DataFrame(),
                report_date=0,
                raw_path=path,
                is_placeholder=True,
            )
        df = TdxFinReader.to_data(path)
        # report_date 从 columns 取 · index 0 = report_date
        report_date = int(df["report_date"].iloc[0]) if len(df) > 0 else 0
        if output_dir is not None:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            pq_path = output_dir / f"gpcw{report_date}.parquet"
            df.to_parquet(pq_path, index=True, compression="snappy")
        return QuarterData(
            df=df,
            report_date=report_date,
            raw_path=path,
            is_placeholder=False,
        )

    # ---------------------------------------------------------------------
    # 批量 + meta.db 集成
    # ---------------------------------------------------------------------

    @staticmethod
    def iter_quarters(raw_dir: Path):
        """遍历 raw_dir 下所有 .dat + .zip · yield QuarterData

        Args:
            raw_dir: 解压后的 tdxfin 目录 (Phase 1 PoC 用 raw/)

        Yields:
            QuarterData · 占位文件 is_placeholder=True
        """
        raw_dir = Path(raw_dir)
        # .zip 优先 · .dat 次之
        paths = sorted(raw_dir.glob("gpcw*.zip")) + sorted(raw_dir.glob("gpcw*.dat"))
        for path in paths:
            try:
                yield TdxFinReader.parse_quarter(path)
            except Exception:
                continue

    @staticmethod
    def parse_quarters_incremental(
        raw_dir: Path,
        output_dir: Path,
        db_path: Path,
    ) -> IncrementalSummary:
        """增量解析 raw_dir 下所有 quarter · 跳过已 parse_ok 且 mtime 未变的

        Args:
            raw_dir:   gpcw*.zip / gpcw*.dat 所在目录
            output_dir: Parquet 输出目录
            db_path:   MetaDB 路径

        Returns:
            IncrementalSummary(skipped, parsed, failed, elapsed_seconds)
        """
        import logging
        import time
        from pathlib import Path
        from tdx_chronos.meta.db import MetaDB

        log = logging.getLogger("tdxfin_incr")
        start = time.monotonic()
        raw_dir = Path(raw_dir)
        output_dir = Path(output_dir)
        db_path = Path(db_path)

        db = MetaDB(str(db_path))
        db.init_schema()

        paths = sorted(raw_dir.glob("gpcw*.zip")) + sorted(raw_dir.glob("gpcw*.dat"))
        skipped = 0
        parsed = 0
        failed = 0

        for path in paths:
            report_date = _stem_to_report_date(path.stem)
            if report_date is None:
                continue

            if db.should_skip_quarter(report_date, path):
                log.info("skip %s (already parsed, mtime unchanged)", path.name)
                skipped += 1
                continue

            try:
                qd = TdxFinReader.parse_quarter(path, output_dir=output_dir)
                file_mtime = path.stat().st_mtime if path.exists() else None
                stock_count = len(qd.df) if not qd.df.empty else 0
                db.record_quarter_metadata(
                    report_date=report_date,
                    file_path=str(path),
                    file_size=path.stat().st_size if path.exists() else 0,
                    stock_count=stock_count,
                    parquet_path=str(output_dir / f"gpcw{report_date}.parquet") if not qd.is_placeholder else None,
                    is_placeholder=qd.is_placeholder,
                    parse_ok=(not qd.is_placeholder and stock_count > 0),
                    error=None,
                    file_mtime=file_mtime,
                )
                parsed += 0 if qd.is_placeholder else 1
                log.info("parsed %s → %d stocks", path.name, stock_count)
            except Exception as exc:
                file_mtime = path.stat().st_mtime if path.exists() else None
                db.record_quarter_metadata(
                    report_date=report_date,
                    file_path=str(path),
                    file_size=path.stat().st_size if path.exists() else 0,
                    stock_count=0,
                    parse_ok=False,
                    error=str(exc),
                    file_mtime=file_mtime,
                )
                failed += 1
                log.warning("failed %s: %s", path.name, exc)

        db.close()
        elapsed = time.monotonic() - start
        return IncrementalSummary(
            skipped=skipped, parsed=parsed, failed=failed, elapsed_seconds=elapsed,
        )


def _stem_to_report_date(stem: str) -> Optional[int]:
    """gpcw20260331 → 20260331 · stem 无效返回 None"""
    import re
    m = re.match(r"^gpcw(\d{8})$", stem)
    if m:
        return int(m.group(1))
    return None