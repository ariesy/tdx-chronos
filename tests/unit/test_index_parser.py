"""Sprint 4b D2 · index_parser.py 单元测试

5 指数 .day → Parquet

Test classes:
- TestIndexCodes         · 5 指数常量
- TestIndexParseFile      · 单 .day → pd.DataFrame
- TestIndexParseAll       · parse_all + Parquet 落盘
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from tdx_chronos.sources.index_parser import (
    INDEX_CODES,
    IndexParser,
)


# ---------------------------------------------------------------------
# TestIndexCodes
# ---------------------------------------------------------------------
class TestIndexCodes:
    def test_five_main_indices(self):
        """§四.5 5 主要指数"""
        assert len(INDEX_CODES) == 5

    def test_index_codes_unique_ds_code(self):
        ds_codes = {c["ds_code"] for c in INDEX_CODES}
        assert len(ds_codes) == 5  # all unique

    def test_index_codes_well_known(self):
        """5 指数 well-known: 上证/沪深300/深证/创业板/科创50"""
        names = {c["name"] for c in INDEX_CODES}
        assert "上证综指" in names
        assert "沪深300" in names
        assert "深证成指" in names
        assert "创业板指" in names
        assert "科创50" in names


# ---------------------------------------------------------------------
# TestIndexParseFile
# ---------------------------------------------------------------------
class TestIndexParseFile:
    def test_shanghai_composite_columns(self):
        """上证综指 8+ cols (复用 OfficialZipParser 标准列)"""
        path = Path("/app/tdx-chronos/data/snapshot/2026-07-04/raw/sh/lday/sh000001.day")
        df = IndexParser.parse_file(path)
        assert isinstance(df, pd.DataFrame)
        assert df.shape[0] == 8674
        for col in ("date", "open", "high", "low", "close", "amount", "vol", "reserved"):
            assert col in df.columns

    def test_hs300_record_count(self):
        """沪深 300 5220 records"""
        path = Path("/app/tdx-chronos/data/snapshot/2026-07-04/raw/sh/lday/sh000300.day")
        df = IndexParser.parse_file(path)
        assert df.shape[0] == 5220

    def test_kechuang50_first_date(self):
        """科创 50 首日 2019-12-31 (开板)"""
        path = Path("/app/tdx-chronos/data/snapshot/2026-07-04/raw/sh/lday/sh000688.day")
        df = IndexParser.parse_file(path)
        assert int(df["date"].min()) == 20191231


# ---------------------------------------------------------------------
# TestIndexParseAll
# ---------------------------------------------------------------------
class TestIndexParseAll:
    def test_parse_all_writes_parquet(self, tmp_path):
        """5 指数全解析 → 1 Parquet"""
        out = tmp_path / "indices.parquet"
        summary = IndexParser.parse_all(
            raw_dir=Path("/app/tdx-chronos/data/snapshot/2026-07-04/raw"),
            output_path=out,
        )
        assert summary.parsed_ok == 5
        assert summary.output_rows == 28004
        assert out.exists()

        # 验证 Parquet 可读
        table = pq.read_table(out)
        assert table.num_rows == 28004
        assert "ds_code" in table.column_names
        assert "name" in table.column_names

    def test_parse_all_5_indices(self):
        """5 指数全部成功 (真数据源)"""
        from tdx_chronos.sources.index_parser import IndexParser as IP
        summary = IP.parse_all(
            raw_dir=Path("/app/tdx-chronos/data/snapshot/2026-07-04/raw"),
            output_path=Path("/tmp/test_indices.parquet"),
        )
        assert summary.parsed_ok == 5
        for spec in INDEX_CODES:
            ds = spec["ds_code"]
            assert summary.results[ds]["parse_ok"] is True
            assert summary.results[ds]["record_count"] > 100