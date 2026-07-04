"""TDX-chronos · IndexParser (v1.1 Sprint 4b D2)

§四.5 / §四.B 5 主要指数 .day → Parquet

5 主要指数:
  - sh000001.SH  上证综指 (shzsday.zip)
  - sh000300.SH  沪深 300  (tdxzs_day.zip)
  - sz399001.SZ  深证成指 (szzsday.zip)
  - sz399006.SZ  创业板指 (tdxzs_day.zip)
  - sh000688.SH  科创 50   (tdxzs_day.zip)

格式: 32B/record = struct('<IIIIIfII') (DAY_STRUCT from official_zip)

公开 API:
- INDEX_CODES · 5 指数 (market, code, display_name)
- IndexParser.parse_file(path) -> pd.DataFrame
- IndexParser.parse_all(raw_dir, output_path) -> IndexParseSummary
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from tdx_chronos.sources.official_zip import DAY_STRUCT, OfficialZipParser

# 5 主要指数 (market, code, display_name)
INDEX_CODES: List[dict] = [
    {"market": "sh", "code": "000001", "name": "上证综指", "ds_code": "000001.SH"},
    {"market": "sh", "code": "000300", "name": "沪深300",  "ds_code": "000300.SH"},
    {"market": "sz", "code": "399001", "name": "深证成指", "ds_code": "399001.SZ"},
    {"market": "sz", "code": "399006", "name": "创业板指", "ds_code": "399006.SZ"},
    {"market": "sh", "code": "000688", "name": "科创50",   "ds_code": "000688.SH"},
]

PARQUET_CODEC = "zstd"
PARQUET_LEVEL = 3


@dataclass
class IndexParseSummary:
    """5 指数解析总结"""

    raw_dir: Path
    output_path: Path
    start_at: datetime
    end_at: datetime
    results: Dict[str, dict] = field(default_factory=dict)
    output_rows: int = 0
    output_bytes: int = 0

    @property
    def parsed_ok(self) -> int:
        return sum(1 for r in self.results.values() if r["parse_ok"])

    @property
    def total_records(self) -> int:
        return sum(r["record_count"] for r in self.results.values() if r["parse_ok"])

    @property
    def total_seconds(self) -> float:
        return (self.end_at - self.start_at).total_seconds()


class IndexParser:
    """§四.5 5 主要指数 .day → 1 Parquet"""

    @staticmethod
    def find_index_path(raw_dir: Path, market: str, code: str) -> Path:
        """raw/{sh,sz}/lday/{market}{code}.day · 兜底多个路径"""
        raw_dir = Path(raw_dir)
        candidates = [
            raw_dir / market / "lday" / f"{market}{code}.day",
            raw_dir / market / f"{market}{code}.day",
        ]
        for p in candidates:
            if p.exists():
                return p
        return candidates[0]  # 不存在 · 留给调用方处理

    @staticmethod
    def parse_file(path: Path) -> pd.DataFrame:
        """单 .day → pd.DataFrame (复用 OfficialZipParser.parse_day_file)"""
        parser = OfficialZipParser()
        result = parser.parse_day_file(Path(path))
        # ParseResult 含 DataFrame 或 None (失败)
        if hasattr(result, "df"):
            return result.df
        # fallback: 手动 unpack
        data = Path(path).read_bytes()
        n = len(data) // DAY_STRUCT.size
        dates, opens, highs, lows, closes, amounts, volumes, reserved = [], [], [], [], [], [], [], []
        for i in range(n):
            r = DAY_STRUCT.unpack_from(data, i * DAY_STRUCT.size)
            dates.append(r[0])
            opens.append(r[1])
            highs.append(r[2])
            lows.append(r[3])
            closes.append(r[4])
            amounts.append(r[5])
            volumes.append(r[6])
            reserved.append(r[7])
        return pd.DataFrame({
            "date": dates,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "amount": amounts,
            "volume": volumes,
            "reserved": reserved,
        })

    @staticmethod
    def parse_all(raw_dir: Path, output_path: Path) -> IndexParseSummary:
        """5 指数全部解析 → 1 大 Parquet (zstd)

        Args:
            raw_dir:      snapshot/{date}/raw
            output_path:   data/index/indices.parquet

        Returns:
            IndexParseSummary
        """
        raw_dir = Path(raw_dir)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        start_at = datetime.now(timezone.utc)

        all_dfs: List[pd.DataFrame] = []
        results: Dict[str, dict] = {}

        for spec in INDEX_CODES:
            market, code, name, ds_code = (
                spec["market"], spec["code"], spec["name"], spec["ds_code"],
            )
            path = IndexParser.find_index_path(raw_dir, market, code)
            if not path.exists():
                results[ds_code] = {
                    "name": name,
                    "path": str(path),
                    "parse_ok": False,
                    "record_count": 0,
                    "first_date": None,
                    "last_date": None,
                    "error": "file not found",
                }
                continue
            try:
                df = IndexParser.parse_file(path)
                df = df.copy()
                df["market"] = market
                df["code"] = code
                df["ds_code"] = ds_code
                df["name"] = name
                all_dfs.append(df)
                results[ds_code] = {
                    "name": name,
                    "path": str(path),
                    "parse_ok": True,
                    "record_count": len(df),
                    "first_date": int(df["date"].min()) if len(df) else None,
                    "last_date": int(df["date"].max()) if len(df) else None,
                    "error": None,
                }
            except Exception as e:
                results[ds_code] = {
                    "name": name,
                    "path": str(path),
                    "parse_ok": False,
                    "record_count": 0,
                    "first_date": None,
                    "last_date": None,
                    "error": f"parse failed: {e}",
                }

        if all_dfs:
            combined = pd.concat(all_dfs, ignore_index=True)
            # 简化列: 复用 K 线格式 + 加 ds_code/name
            table = pa.Table.from_pandas(combined, preserve_index=False)
            pq.write_table(
                table, output_path,
                compression=PARQUET_CODEC,
                compression_level=PARQUET_LEVEL,
            )
            output_rows = combined.shape[0]
            output_bytes = output_path.stat().st_size
        else:
            output_rows = 0
            output_bytes = 0

        end_at = datetime.now(timezone.utc)
        return IndexParseSummary(
            raw_dir=raw_dir,
            output_path=output_path,
            start_at=start_at,
            end_at=end_at,
            results=results,
            output_rows=output_rows,
            output_bytes=output_bytes,
        )