"""TDX-chronos · TdxGpReader (v1.1 Sprint 4a D2 简化版)

§四.7 股本 .dat 解析器 (基础结构 + 元信息)

文件结构 (Sprint 4a D2 实证修正):
  **N records × 13 bytes · NO header / NO footer**

record (13 bytes):
  uint8   type        (变动类型 1-48 · v1.1 不解释语义)
  uint32  date        (YYYYMMDD)
  uint32  field1      (类型相关数据 · 类型 1=季末快照, 类型 3+=其他)
  uint32  field2      (类型相关数据 · 常为 0)

v1.1 简化策略:
  - 不解析每条 record 的 type 字段语义 (需要 tdx schema 完整文档, 通达信未公开)
  - 只提取文件级元信息: file_size, record_count, market, code
  - meta.db gp_metadata 表 (Sprint 4a 末)
  - 错误率报表 (损坏文件 / 截断文件)
  - 完整 record 解析 = v2.0 (待 tdx 公开 schema)

设计:
  - 不依赖 vendor/mootdx · 直接文件大小除以 13 验证
  - 公开 API: parse_file / iter_quarters / run_full_parse
  - meta.db 新增 gp_metadata 表

用法:
    >>> from tdx_chronos.fin.tdxgp import TdxGpReader
    >>> info = TdxGpReader.parse_file('gpsh600519.dat')
    >>> info.file_size
    351416
    >>> info.record_count
    27032
    >>> info.market
    'sh'
    >>> info.code
    '600519'
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional

RECORD_SIZE = 13  # 13B records (1B type + 4B date + 4B field1 + 4B field2)

# 文件名 pattern: gp{market}{code6}.dat
MARKETS = ("sh", "sz", "bj")


@dataclass
class GpFileInfo:
    """单股本 .dat 文件元信息

    Attributes:
        file_path:    完整路径
        file_size:    文件大小 (bytes)
        record_count: 13B record 数量
        market:       'sh' | 'sz' | 'bj' (从文件名解析)
        code:         6 位股票代码 (从文件名解析)
        first_date:   最早 type=1 季末记录日期 (YYYYMMDD, 可选)
        last_date:    最晚 type=1 季末记录日期 (YYYYMMDD, 可选)
        parse_ok:     True if structure 验证通过
        error:        失败原因 (parse_ok=True 时 None)
    """

    file_path: Path
    file_size: int
    record_count: int
    market: str
    code: str
    parse_ok: bool
    first_date: Optional[int] = None
    last_date: Optional[int] = None
    error: Optional[str] = None


class TdxGpReader:
    """§四.7 股本 .dat 元信息解析器 (v1.1 Sprint 4a D2 简化版)

    公开 API:
        parse_file(path) -> GpFileInfo
        iter_quarters(raw_dir) -> Iterator[GpFileInfo]
        run_full_parse(raw_dir, db_path) -> BatchSummary
    """

    # ---------------------------------------------------------------------
    # 单文件解析
    # ---------------------------------------------------------------------

    @staticmethod
    def parse_file(path: str | Path, sample_dates: bool = True) -> GpFileInfo:
        """单 .dat → GpFileInfo (元信息)

        Args:
            path:          gp{market}{code}.dat 文件路径
            sample_dates:  True=扫 type=1 季末记录找首末日期 (略慢)

        Returns:
            GpFileInfo · parse_ok=True 成功 / False 失败
        """
        path = Path(path)
        if not path.exists():
            return GpFileInfo(
                file_path=path,
                file_size=0,
                record_count=0,
                market="?",
                code="?",
                parse_ok=False,
                error="file not found",
            )

        file_size = path.stat().st_size
        market, code = TdxGpReader._parse_filename(path.name)

        # 13B records · 无 header/footer
        if file_size == 0:
            return GpFileInfo(
                file_path=path,
                file_size=0,
                record_count=0,
                market=market,
                code=code,
                parse_ok=False,
                error="empty file",
            )

        if file_size % RECORD_SIZE != 0:
            return GpFileInfo(
                file_path=path,
                file_size=file_size,
                record_count=0,
                market=market,
                code=code,
                parse_ok=False,
                error=(
                    f"size not aligned: {file_size} % {RECORD_SIZE} = {file_size % RECORD_SIZE}"
                ),
            )

        record_count = file_size // RECORD_SIZE

        # 抽 type=1 季末首末日期 (sampling)
        first_date = None
        last_date = None
        if sample_dates and record_count > 0:
            try:
                with open(path, "rb") as f:
                    # 找首个 type=1
                    for i in range(min(record_count, 200)):
                        r = f.read(RECORD_SIZE)
                        if r[0] == 1:
                            first_date = struct.unpack("<I", r[1:5])[0]
                            break
                    # 找末个 type=1 (从末尾倒数)
                    f.seek(-RECORD_SIZE * 200, 2)  # 200 records from end
                    tail = f.read(RECORD_SIZE * 200)
                    for i in range(len(tail) // RECORD_SIZE):
                        r = tail[i * RECORD_SIZE:(i + 1) * RECORD_SIZE]
                        if r[0] == 1:
                            last_date = struct.unpack("<I", r[1:5])[0]
            except Exception:
                pass  # date sampling 失败不影响 parse_ok

        return GpFileInfo(
            file_path=path,
            file_size=file_size,
            record_count=record_count,
            market=market,
            code=code,
            parse_ok=True,
            first_date=first_date,
            last_date=last_date,
        )

    @staticmethod
    def _parse_filename(name: str) -> tuple[str, str]:
        """gp{market}{code6}.dat → (market, code)

        Returns:
            (market, code) · 文件名不匹配时返回 ('?', '?')
        """
        if not name.startswith("gp") or not name.endswith(".dat"):
            return "?", "?"
        stem = name[2:-4]
        if len(stem) < 8:
            return "?", "?"
        market = stem[:2]
        code = stem[2:]
        if market not in MARKETS:
            return "?", "?"
        if not code.isdigit() or len(code) != 6:
            return "?", "?"
        return market, code

    # ---------------------------------------------------------------------
    # 批量 + meta.db
    # ---------------------------------------------------------------------

    @staticmethod
    def iter_quarters(raw_dir: Path) -> Iterator[GpFileInfo]:
        """遍历 raw_dir 下所有 gp*.dat · yield GpFileInfo"""
        raw_dir = Path(raw_dir)
        for path in sorted(raw_dir.glob("gp*.dat")):
            yield TdxGpReader.parse_file(path)

    @staticmethod
    def run_full_parse(raw_dir: Path, db_path: Path) -> "BatchSummary":
        """遍历所有股本 .dat + 写 meta.db gp_metadata 表 + 错误率报表

        Args:
            raw_dir:  tdxgp 解压目录
            db_path:  meta.db 路径

        Returns:
            BatchSummary
        """
        from datetime import datetime, timezone
        from tdx_chronos.meta.db import MetaDB

        start_at = datetime.now(timezone.utc)
        results: List[GpFileInfo] = list(TdxGpReader.iter_quarters(raw_dir))

        db = MetaDB(db_path)
        try:
            db.init_schema()
            for info in results:
                db.record_gp_metadata(
                    file_path=str(info.file_path),
                    file_size=info.file_size,
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
        return BatchSummary(
            raw_dir=raw_dir,
            start_at=start_at,
            end_at=end_at,
            results=results,
        )


@dataclass
class BatchSummary:
    """批量解析总结"""

    raw_dir: Path
    start_at: "datetime"
    end_at: "datetime"
    results: List[GpFileInfo]

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
    def total_size(self) -> int:
        return sum(r.file_size for r in self.results)

    @property
    def total_records(self) -> int:
        return sum(r.record_count for r in self.results if r.parse_ok)

    @property
    def total_seconds(self) -> float:
        return (self.end_at - self.start_at).total_seconds()

    def by_market(self) -> dict:
        """按 market 统计 (parsed_ok only)"""
        stats = {"sh": 0, "sz": 0, "bj": 0, "?": 0}
        for r in self.results:
            if r.parse_ok:
                stats[r.market] = stats.get(r.market, 0) + 1
        return stats

    def error_rate(self) -> float:
        """失败率 (0.0-1.0)"""
        return self.parsed_failed / self.total_files if self.total_files else 0.0