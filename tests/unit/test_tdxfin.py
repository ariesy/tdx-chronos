"""Sprint 4a D1 · tdxfin.py 单元测试

Test classes:
- TestTdxFinHeaderSchema  · header (hIH3L) + 1 stock header 真实字节验证
- TestTdxFinParse         · 真实 .dat fixture → DataFrame 5524×585
- TestTdxFinZipAuto       · .zip 自动解压到 .dat
- TestTdxFinPlaceholder   · 164B 占位 zip + 20B 占位 dat 检测
- TestTdxFinQuarter       · parse_quarter + output Parquet
"""
from __future__ import annotations

import struct
import zipfile
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

from tdx_chronos.fin.tdxfin import (
    ACTUAL_FIELDS_PER_STOCK,
    HEADER_PACK_FORMAT,
    PLACEHOLDER_DAT_SIZE,
    PLACEHOLDER_ZIP_SIZE,
    STOCK_HEADER_PACK_FORMAT,
    TAIL_UNKNOWN_COLUMNS,
    TdxFinReader,
)


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------
@pytest.fixture
def real_dat():
    return Path("tests/fixtures/fin/gpcw20260331.dat")


@pytest.fixture
def real_placeholder_zip():
    return Path("tests/fixtures/fin/gpcw20261231.zip")


# ---------------------------------------------------------------------
# TestTdxFinHeaderSchema
# ---------------------------------------------------------------------
class TestTdxFinHeaderSchema:
    def test_header_format_is_20_bytes(self):
        assert struct.calcsize(HEADER_PACK_FORMAT) == 20

    def test_stock_header_format_is_11_bytes(self):
        assert struct.calcsize(STOCK_HEADER_PACK_FORMAT) == 11

    def test_real_dat_header_magic_date_count(self, real_dat):
        """真 .dat header: magic=1, date=20260331, count=5524"""
        with open(real_dat, "rb") as f:
            data = f.read(struct.calcsize(HEADER_PACK_FORMAT))
        magic, date, count, _, _, _ = struct.unpack(HEADER_PACK_FORMAT, data)
        assert magic == 1
        assert date == 20260331
        assert count == 5524

    def test_actual_fields_per_stock_constant(self):
        """584 floats/stock (v1.1 实测)"""
        assert ACTUAL_FIELDS_PER_STOCK == 584


# ---------------------------------------------------------------------
# TestTdxFinParse
# ---------------------------------------------------------------------
class TestTdxFinParse:
    def test_parse_real_dat_shape(self, real_dat):
        """gpcw20260331.dat → 5524 × 585 DataFrame"""
        df = TdxFinReader.to_data(real_dat)
        assert df.shape == (5524, 585)

    def test_parse_real_dat_index_is_code(self, real_dat):
        """index name = 'code'"""
        df = TdxFinReader.to_data(real_dat)
        assert df.index.name == "code"

    def test_parse_real_dat_first_5_codes(self, real_dat):
        """深圳主板前 5"""
        df = TdxFinReader.to_data(real_dat)
        assert list(df.index[:5]) == ["000001", "000002", "000004", "000006", "000007"]

    def test_parse_real_dat_columns_start(self, real_dat):
        """前 5 columns = ['report_date', '基本每股收益', ...]"""
        df = TdxFinReader.to_data(real_dat)
        assert list(df.columns[:5]) == [
            "report_date",
            "基本每股收益",
            "扣除非经常性损益每股收益",
            "每股未分配利润",
            "每股净资产",
        ]

    def test_parse_real_dat_columns_tail_has_unknown(self, real_dat):
        """末尾 4 columns = ['_col582', '_col583', '_col584', '_col585']"""
        df = TdxFinReader.to_data(real_dat)
        assert list(df.columns[-4:]) == [
            "_col582", "_col583", "_col584", "_col585",
        ]

    def test_parse_real_dat_maotai_eps(self, real_dat):
        """茅台 600519 2026Q1 基本每股收益 ~21.76 元"""
        df = TdxFinReader.to_data(real_dat)
        row = df.loc["600519"]
        eps = float(row["基本每股收益"])
        # 茅台 2026Q1 估算 EPS 21-25 元范围
        assert 20.0 < eps < 25.0

    def test_parse_real_dat_maotai_report_date(self, real_dat):
        """茅台 report_date = 20260331 (Q1)"""
        df = TdxFinReader.to_data(real_dat)
        assert int(df.loc["600519", "report_date"]) == 20260331

    def test_parse_real_dat_no_nan_in_codes(self, real_dat):
        """无 None / 空 code"""
        df = TdxFinReader.to_data(real_dat)
        assert df.index.notna().all()
        assert "" not in df.index


# ---------------------------------------------------------------------
# TestTdxFinZipAuto
# ---------------------------------------------------------------------
class TestTdxFinZipAuto:
    def test_zip_auto_unpack(self, tmp_path):
        """自己包一个 zip · to_data 自动解压"""
        # 复制 .dat 到 zip
        dat_path = Path("tests/fixtures/fin/gpcw20260331.dat")
        zip_path = tmp_path / "gpcw20260331.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(dat_path, arcname="gpcw20260331.dat")

        df = TdxFinReader.to_data(zip_path)
        assert df.shape == (5524, 585)

    def test_en_header(self, real_dat):
        """header='en' → 'report_date' + 'col1'..'col584'"""
        df = TdxFinReader.to_data(real_dat, header="en")
        assert df.columns[0] == "report_date"
        assert df.columns[1] == "col1"
        assert df.columns[-1] == f"col{ACTUAL_FIELDS_PER_STOCK}"


# ---------------------------------------------------------------------
# TestTdxFinPlaceholder
# ---------------------------------------------------------------------
class TestTdxFinPlaceholder:
    def test_placeholder_164b_zip_rejected(self, real_placeholder_zip):
        """164B zip (未来季) → 拒绝"""
        with pytest.raises(ValueError, match="placeholder"):
            TdxFinReader.to_data(real_placeholder_zip)

    def test_placeholder_20b_dat_rejected(self, tmp_path):
        """20B dat (空季度) → 拒绝"""
        dat = tmp_path / "gpcw20240101.dat"
        dat.write_bytes(b"\x00" * PLACEHOLDER_DAT_SIZE)
        with pytest.raises(ValueError, match="placeholder"):
            TdxFinReader.to_data(dat)

    def test_parse_quarter_placeholder_returns_empty(self, real_placeholder_zip):
        """parse_quarter 对占位 zip 返回 is_placeholder=True, df=空"""
        qd = TdxFinReader.parse_quarter(real_placeholder_zip)
        assert qd.is_placeholder is True
        assert qd.df.empty
        assert qd.report_date == 0

    def test_parse_quarter_real(self, real_dat):
        """parse_quarter 真 .dat → 5524 stocks · report_date=20260331"""
        qd = TdxFinReader.parse_quarter(real_dat)
        assert qd.is_placeholder is False
        assert qd.report_date == 20260331
        assert qd.df.shape == (5524, 585)


# ---------------------------------------------------------------------
# TestTdxFinQuarter
# ---------------------------------------------------------------------
class TestTdxFinQuarter:
    def test_parse_quarter_writes_parquet(self, real_dat, tmp_path):
        """parse_quarter(output_dir=...) 写 Parquet"""
        qd = TdxFinReader.parse_quarter(real_dat, output_dir=tmp_path)
        pq_path = tmp_path / f"gpcw{qd.report_date}.parquet"
        assert pq_path.exists()
        # 验证可读回
        df_read = pd.read_parquet(pq_path)
        assert df_read.shape == (5524, 585)
        assert df_read.index.name == "code"
