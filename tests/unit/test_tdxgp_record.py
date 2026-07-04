"""Sprint 4b D1 · tdxgp_record.py 单元测试

13B records 完整解析 · type 1-48 全部统计

Test classes:
- TestTdxGpRecordParseFile  · 单 .dat → GpRecordsFile (含 type 分布)
- TestTdxGpRecordDataFrame   · 全部 records → pd.DataFrame
- TestTdxGpRecordIter         · iter_quarters
- TestTdxGpRecordFullParse    · run_full_parse + Parquet 落盘
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from tdx_chronos.fin.tdxgp_record import (
    GpRecordsFile,
    RECORD_SIZE,
    TdxGpRecordReader,
)


# ---------------------------------------------------------------------
# TestTdxGpRecordParseFile
# ---------------------------------------------------------------------
class TestTdxGpRecordParseFile:
    def test_maotai_records(self):
        """茅台 gpsh600519.dat: 27032 records · type 1=104 (季末快照)"""
        info = TdxGpRecordReader.parse_file(
            "tests/fixtures/fin/gp/gpsh600519.dat"
        )
        assert info.parse_ok is True
        assert info.record_count == 27032
        # type 1 (季末快照) 应有 104 个
        assert info.type_distribution.get(1) == 104
        # type 47 (近期每日数据) 至少有 1 个
        assert info.type_distribution.get(47, 0) >= 1
        # first date = 2001-12-31 (IPO 后首季末)
        assert info.first_date == 20011231

    def test_maotai_type_coverage(self):
        """type 1-48 都应出现 (至少 1 个)"""
        info = TdxGpRecordReader.parse_file(
            "tests/fixtures/fin/gp/gpsh600519.dat"
        )
        types = set(info.type_distribution.keys())
        # type 1-48 中, 茅台 27 种 type 出现过
        assert len(types) >= 20, f"茅台仅 {len(types)} 种 type"

    def test_first_last_date(self):
        """first_date 早于 last_date"""
        info = TdxGpRecordReader.parse_file(
            "tests/fixtures/fin/gp/gpsh600519.dat"
        )
        assert info.first_date is not None
        assert info.last_date is not None
        assert info.first_date <= info.last_date


# ---------------------------------------------------------------------
# TestTdxGpRecordDataFrame
# ---------------------------------------------------------------------
class TestTdxGpRecordDataFrame:
    def test_build_dataframe_shape(self):
        """build_dataframe_from_bytes 6 cols × N rows"""
        from tdx_chronos.fin.tdxgp_record import TdxGpRecordReader as R
        data = Path("tests/fixtures/fin/gp/gpsh600519.dat").read_bytes()
        df = R._build_dataframe_from_bytes(data, "sh", "600519")
        assert df.shape == (27032, 6)
        assert list(df.columns) == ["type", "date", "value_1", "value_2", "market", "code"]

    def test_build_dataframe_market_code_injection(self):
        """market/code 列正确注入"""
        from tdx_chronos.fin.tdxgp_record import TdxGpRecordReader as R
        data = Path("tests/fixtures/fin/gp/gpbj430017.dat").read_bytes()
        df = R._build_dataframe_from_bytes(data, "bj", "430017")
        assert (df["market"] == "bj").all()
        assert (df["code"] == "430017").all()


# ---------------------------------------------------------------------
# TestTdxGpRecordIter
# ---------------------------------------------------------------------
class TestTdxGpRecordIter:
    def test_iter_yields_all_files(self):
        """3 fixture files"""
        infos = list(TdxGpRecordReader.iter_quarters(
            Path("tests/fixtures/fin/gp")
        ))
        assert len(infos) >= 3


# ---------------------------------------------------------------------
# TestTdxGpRecordFullParse
# ---------------------------------------------------------------------
class TestTdxGpRecordFullParse:
    def test_run_full_parse_writes_parquet(self, tmp_path):
        """3 fixture files → 1 Parquet"""
        out = tmp_path / "records.parquet"
        summary = TdxGpRecordReader.run_full_parse(
            raw_dir=Path("tests/fixtures/fin/gp"),
            output_path=out,
            db_path=None,
        )
        assert summary.parsed_ok == 3
        assert summary.parsed_failed == 1
        assert summary.output_rows == 27032 + 26473 + 6257  # 茅台+平安+北交所
        assert out.exists()

        # 验证 Parquet 可读
        table = pq.read_table(out)
        assert table.num_rows == 59762
        assert set(table.column_names) >= {
            "type", "date", "value_1", "value_2", "market", "code",
        }

    def test_run_full_parse_writes_meta_db(self, tmp_path):
        """meta.db 升级 record_count"""
        from tdx_chronos.meta.db import MetaDB
        out = tmp_path / "records.parquet"
        db = tmp_path / "meta.db"
        TdxGpRecordReader.run_full_parse(
            raw_dir=Path("tests/fixtures/fin/gp"),
            output_path=out,
            db_path=db,
        )

        # 验证 meta.db
        meta = MetaDB(db)
        try:
            assert meta.count_gp_metadata() == 4  # 3 OK + 1 failed
        finally:
            meta.close()

    def test_run_full_parse_max_files(self, tmp_path):
        """max_files=1 限制 (取第 1 个 file · sorted 顺序 bj 优先)"""
        out = tmp_path / "records.parquet"
        summary = TdxGpRecordReader.run_full_parse(
            raw_dir=Path("tests/fixtures/fin/gp"),
            output_path=out,
            db_path=None,
            max_files=1,
        )
        assert summary.parsed_ok == 1
        # 第 1 个 (sorted) 是 bj430017 (6257 records)
        assert summary.output_rows == 6257
