"""Sprint 2 · official_zip.py 单元测试（用真 .day fixture）

5 个真 .day sample 覆盖 (per Phase 1 PoC):
  1. sh600000.day (35 年 · 老股)
  2. sh600519.day (35 年 · 茅台 · 价格高)
  3. sz000001.day (30 年 · 平安 · 老股)
  4. sz300750.day (近年 · 宁德 · 新股)
  5. bj920193.day (1 年 · 北交所)

+ 1 个 Parquet 输出测试

不调 socket · 不连网络 · 纯本地 fixture 解析
"""
from __future__ import annotations

import struct
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from tdx_chronos.sources.official_zip import (
    DAY_STRUCT,
    OfficialZipParser,
    ParseResult,
    DEFAULT_SOURCE_ZIP,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "day"


def _day_path(market: str, symbol: str) -> Path:
    return FIXTURES / market / "lday" / f"{symbol}.day"


# ---------------------------------------------------------------------
# class-level constants
# ---------------------------------------------------------------------
class TestConstants:
    def test_day_struct_size_is_32_bytes(self):
        """§四.B schema: 32 bytes/record (8 fields × 4 bytes)"""
        assert DAY_STRUCT.size == 32
        assert DAY_STRUCT.format == "<IIIIIfII"

    def test_default_source_zip(self):
        assert DEFAULT_SOURCE_ZIP == "hsjday.zip"


# ---------------------------------------------------------------------
# 5 真 fixture 测试 · 每只股票 1 个
# ---------------------------------------------------------------------
class TestParseDayFileSh600000:
    """sh600000 (浦发 · 35 年 · 老股 · reserved=1175)"""

    def test_returns_dataframe_with_expected_schema(self):
        result = OfficialZipParser().parse_day_file(
            _day_path("sh", "sh600000")
        )
        assert isinstance(result, ParseResult)
        assert isinstance(result.df, pd.DataFrame)
        # §四.D schema 字段完整
        expected = {
            "date", "open", "high", "low", "close",
            "amount", "vol", "reserved",
            "symbol", "market", "source_zip", "ingested_at",
        }
        assert set(result.df.columns) == expected

    def test_metadata_correct(self):
        result = OfficialZipParser().parse_day_file(
            _day_path("sh", "sh600000")
        )
        assert result.symbol == "sh600000"
        assert result.market == "sh"
        # 35 年老股 · 6000+ records (排除周末/节假日)
        assert result.record_count > 6000
        assert result.record_count < 8000
        # 第一条: 浦发上市首日 (1999-11-10)
        assert result.first_date == 19991110
        # 最后一条: 当日数据
        assert 20260100 < result.last_date <= 20261231

    def test_first_record_is_listing_day(self):
        """验证第一行 = 上市首日 · 与 struct 直接读取一致 (单源真相)"""
        parser = OfficialZipParser()
        result = parser.parse_day_file(_day_path("sh", "sh600000"))
        # 第一行开盘价 (浦发 1999-11-10 上市首日)
        first = result.df.iloc[0]
        assert first["date"] == 19991110
        # close 价大约 27 块 (历史真实)
        assert 20.0 < first["close"] < 35.0
        # 验证与 raw struct 一致
        raw = _day_path("sh", "sh600000").read_bytes()
        r0 = next(DAY_STRUCT.iter_unpack(raw[:32]))
        assert int(first["date"]) == r0[0]
        assert first["close"] == r0[4] / 100.0


class TestParseDayFileSh600519:
    """sh600519 (茅台 · 35 年 · 老股 · reserved=4816)

    · 验证 §四.B 验证过的 2001-08-27 上市首日数据 (Phase 1 PoC 实证)
    """

    def test_moutai_listing_day_first_record(self):
        result = OfficialZipParser().parse_day_file(
            _day_path("sh", "sh600519")
        )
        assert result.symbol == "sh600519"
        assert result.market == "sh"
        # 茅台 2001-08-27 上市 · 第一条 = 此日
        assert result.first_date == 20010827
        first = result.df.iloc[0]
        # close 35.55 (与 §四.B 实证值完全一致)
        assert first["close"] == pytest.approx(35.55, abs=0.01)
        # open 34.51
        assert first["open"] == pytest.approx(34.51, abs=0.01)
        # 2026-07-03 = 1194.45 (今日数据)
        last = result.df.iloc[-1]
        assert int(last["date"]) == 20260703
        assert last["close"] == pytest.approx(1194.45, abs=0.01)

    def test_reserved_field_preserved(self):
        """reserved 字段保留原始 int32 · v1.1 不解释语义 (§四.B)"""
        result = OfficialZipParser().parse_day_file(
            _day_path("sh", "sh600519")
        )
        # 中段 (2005-11-03) reserved=4816 (§四.B 实证)
        row = result.df[result.df["date"] == 20051103].iloc[0]
        assert row["reserved"] == 4816


class TestParseDayFileSz000001:
    """sz000001 (平安 · 30 年 · 老股 · reserved=0)

    · 验证 reserved=0 (老数据无此字段)
    """

    def test_reserved_zero_for_old_records(self):
        result = OfficialZipParser().parse_day_file(
            _day_path("sz", "sz000001")
        )
        # sz000001 是「深发展」(现平安银行) · 1991-04-03 上市
        # 早期 records (1991-1995) reserved=0 (老数据无此字段)
        early = result.df[result.df["date"] < 19950000].iloc[0]
        assert early["reserved"] == 0
        # 上市首日 = 19910403 (Phase 1 PoC 文档写的 19950414 是错的)
        assert result.first_date == 19910403


class TestParseDayFileSz300750:
    """sz300750 (宁德 · 近年 · 新股 · reserved=65536)

    · 验证 reserved=65536 (期权标记或 TDX 特殊状态)
    """

    def test_reserved_max_16bit_for_newer(self):
        result = OfficialZipParser().parse_day_file(
            _day_path("sz", "sz300750")
        )
        # 2022-06-22 reserved=65536
        row = result.df[result.df["date"] == 20220622].iloc[0]
        assert row["reserved"] == 65536


class TestParseDayFileBj920193:
    """bj920193 (北交所 · 1 年 · 新股 · reserved=65536)

    · 验证北交所最小数据
    """

    def test_bj_market_minimal_file(self):
        result = OfficialZipParser().parse_day_file(
            _day_path("bj", "bj920193")
        )
        assert result.market == "bj"
        assert result.symbol == "bj920193"
        # 64 字节 = 2 records (北交所早期很新)
        assert result.record_count == 2
        assert result.df.iloc[0]["reserved"] in (0, 65536)


# ---------------------------------------------------------------------
# Parquet 输出 + 路径遍历
# ---------------------------------------------------------------------
class TestIterDayFiles:
    """iter_day_files · 流式遍历"""

    def test_iterates_all_fixtures(self):
        parser = OfficialZipParser()
        files = list(parser.iter_day_files(FIXTURES))
        # 5 fixture
        assert len(files) == 5
        # 各 .day 路径存在
        for f in files:
            assert f.exists()
            assert f.suffix == ".day"
        # 包含 3 个市场
        markets = {f.parts[-3] for f in files}
        assert markets == {"sh", "sz", "bj"}


class TestParseToParquet:
    """parse_to_parquet · 单 .day → Parquet 写盘"""

    def test_writes_parquet_with_correct_path(self, tmp_path):
        parser = OfficialZipParser()
        # /tmp/bjlday/ 不存在 · fixture 输入
        output_dir = tmp_path / "out"
        result_path = parser.parse_to_parquet(
            _day_path("bj", "bj920193"),
            output_dir,
        )
        # §四.D 命名: bj/bj920193.parquet
        assert result_path == output_dir / "bj" / "bj920193.parquet"
        assert result_path.exists()
        # 读回来 · 内容一致
        df_read = pd.read_parquet(result_path)
        assert len(df_read) == 2
        assert list(df_read["market"].unique()) == ["bj"]


# ---------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------
class TestErrorHandling:
    def test_invalid_path_raises_value_error(self, tmp_path):
        """路径不含 sh/sz/bj → ValueError"""
        bad = tmp_path / "weird" / "x999999.day"
        bad.parent.mkdir(parents=True)
        bad.write_bytes(b"\x00" * 32)
        with pytest.raises(ValueError, match="Cannot infer market"):
            OfficialZipParser().parse_day_file(bad)
