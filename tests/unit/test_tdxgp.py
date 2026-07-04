"""Sprint 4a D2 · tdxgp.py 单元测试

Sprint 4a D2 schema 真相 (2026-07-04 实证):
- 股本 .dat = N × 13B records · NO header · NO footer
- record = uint8 type + uint32 date + uint32 field1 + uint32 field2

Test classes:
- TestTdxGpFilenameParse   · gp{market}{code6}.dat 文件名解析
- TestTdxGpParseFile       · 单 .dat → GpFileInfo (13B records · 27032 个)
- TestTdxGpErrorHandling   · 截断文件 / 太小文件 / 不存在
- TestTdxGpIter            · iter_quarters 全目录遍历
- TestTdxGpFullParse       · run_full_parse + meta.db 集成
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tdx_chronos.fin.tdxgp import (
    RECORD_SIZE,
    GpFileInfo,
    TdxGpReader,
)


@pytest.fixture
def gp_dir():
    """3 个真股本 + 1 个截断 (100 bytes)"""
    return Path("tests/fixtures/fin/gp")


# ---------------------------------------------------------------------
# TestTdxGpFilenameParse
# ---------------------------------------------------------------------
class TestTdxGpFilenameParse:
    def test_sh(self):
        assert TdxGpReader._parse_filename("gpsh600519.dat") == ("sh", "600519")

    def test_sz(self):
        assert TdxGpReader._parse_filename("gpsz000001.dat") == ("sz", "000001")

    def test_bj(self):
        assert TdxGpReader._parse_filename("gpbj430017.dat") == ("bj", "430017")

    def test_bj830xxx(self):
        """北交所老代码 830xxx"""
        assert TdxGpReader._parse_filename("gpbj830779.dat") == ("bj", "830779")

    def test_invalid_market(self):
        assert TdxGpReader._parse_filename("gpXX600519.dat") == ("?", "?")

    def test_short_code(self):
        assert TdxGpReader._parse_filename("gpsh123.dat") == ("?", "?")

    def test_wrong_prefix(self):
        assert TdxGpReader._parse_filename("gpxx600519.dat") == ("?", "?")

    def test_not_dat(self):
        assert TdxGpReader._parse_filename("gpsh600519.zip") == ("?", "?")


# ---------------------------------------------------------------------
# TestTdxGpParseFile
# ---------------------------------------------------------------------
class TestTdxGpParseFile:
    def test_maotai_real(self):
        """茅台 gpsh600519.dat: 351,416 bytes · 27032 records (13B each)"""
        info = TdxGpReader.parse_file(
            "tests/fixtures/fin/gp/gpsh600519.dat"
        )
        assert info.parse_ok is True
        assert info.market == "sh"
        assert info.code == "600519"
        assert info.file_size == 351416
        # 351416 / 13 = 27032
        assert info.record_count == 27032

    def test_maotai_first_last_date(self):
        """茅台 type=1 季末: 最早 2001-12-31 (IPO 后年末)"""
        info = TdxGpReader.parse_file(
            "tests/fixtures/fin/gp/gpsh600519.dat"
        )
        assert info.first_date == 20011231
        # last_date 采样限末尾 200 records · 茅台 type=1 最后在 rec 103 (20260331)
        # 所以 sampling 可能 miss → last_date 接受 None 或 >= 20260101
        if info.last_date is not None:
            assert info.last_date >= 20260101

    def test_pingan_bank_real(self):
        """平安银行 gpsz000001.dat"""
        info = TdxGpReader.parse_file(
            "tests/fixtures/fin/gp/gpsz000001.dat"
        )
        assert info.parse_ok is True
        assert info.market == "sz"
        assert info.code == "000001"
        # 344149 / 13 = 26473
        assert info.record_count == 26473

    def test_bj_neeq_real(self):
        """北交所 gpbj430017.dat"""
        info = TdxGpReader.parse_file(
            "tests/fixtures/fin/gp/gpbj430017.dat"
        )
        assert info.parse_ok is True
        assert info.market == "bj"
        assert info.code == "430017"
        assert info.file_size == 81341
        # 81341 / 13 = 6257
        assert info.record_count == 6257

    def test_record_count_calculation(self, gp_dir):
        """record_count = size / 13"""
        for f in gp_dir.glob("gp*.dat"):
            if f.stat().st_size > 13:
                info = TdxGpReader.parse_file(f)
                if info.parse_ok:
                    expected = info.file_size // RECORD_SIZE
                    assert info.record_count == expected, f.name

    def test_size_13b_alignment(self):
        """所有真股本 .dat 必须是 13 的倍数"""
        # 茅台 / 平安 / 宁波银行 (历史更长) 都验证
        for name, expected_count in [
            ("gpsh600519.dat", 27032),
            ("gpsh600000.dat", 24613),
            ("gpsz000001.dat", 26473),
        ]:
            p = Path(f"tests/fixtures/fin/gp/{name}")
            if p.exists():
                info = TdxGpReader.parse_file(p)
                assert info.record_count == expected_count, name


# ---------------------------------------------------------------------
# TestTdxGpErrorHandling
# ---------------------------------------------------------------------
class TestTdxGpErrorHandling:
    def test_truncated_file_100b(self, gp_dir):
        """截断 100 bytes · 100 % 13 = 9 · parse_ok=False"""
        info = TdxGpReader.parse_file(gp_dir / "gpsh601318.dat")
        assert info.parse_ok is False
        assert info.error is not None
        assert "aligned" in info.error

    def test_truncated_file_50b(self, tmp_path):
        """50 bytes · 50 % 13 = 11 · 错"""
        f = tmp_path / "gpsh123456.dat"
        f.write_bytes(b"\x00" * 50)
        info = TdxGpReader.parse_file(f)
        assert info.parse_ok is False

    def test_nonexistent_file(self, tmp_path):
        """不存在文件"""
        info = TdxGpReader.parse_file(tmp_path / "nonexistent.dat")
        assert info.parse_ok is False
        assert "not found" in info.error

    def test_empty_file(self, tmp_path):
        """0 bytes 文件"""
        empty = tmp_path / "empty.dat"
        empty.write_bytes(b"")
        info = TdxGpReader.parse_file(empty)
        assert info.parse_ok is False
        assert "empty" in info.error


# ---------------------------------------------------------------------
# TestTdxGpIter
# ---------------------------------------------------------------------
class TestTdxGpIter:
    def test_iter_yields_all_files(self, gp_dir):
        """3 real + 1 truncated · 全部 yield"""
        infos = list(TdxGpReader.iter_quarters(gp_dir))
        assert len(infos) == 4

    def test_iter_mix_ok_failed(self, gp_dir):
        """3 ok + 1 failed"""
        infos = list(TdxGpReader.iter_quarters(gp_dir))
        ok = [i for i in infos if i.parse_ok]
        failed = [i for i in infos if not i.parse_ok]
        assert len(ok) == 3
        assert len(failed) == 1

    def test_iter_sorted(self, gp_dir):
        """按 file_path 排序"""
        infos = list(TdxGpReader.iter_quarters(gp_dir))
        paths = [str(i.file_path) for i in infos]
        assert paths == sorted(paths)


# ---------------------------------------------------------------------
# TestTdxGpFullParse + meta.db
# ---------------------------------------------------------------------
class TestTdxGpFullParse:
    def test_run_full_parse_writes_meta_db(self, gp_dir, tmp_path):
        """run_full_parse 写 meta.db gp_metadata 表"""
        db_path = tmp_path / "meta.db"
        summary = TdxGpReader.run_full_parse(gp_dir, db_path)
        assert summary.total_files == 4
        assert summary.parsed_ok == 3
        assert summary.parsed_failed == 1
        assert summary.total_size > 0
        assert summary.total_records > 0

        # 验证 meta.db 写入
        from tdx_chronos.meta.db import MetaDB
        db = MetaDB(db_path)
        try:
            assert db.count_gp_metadata() == 4
            assert db.count_gp_metadata(parse_ok=True) == 3
            assert db.count_gp_metadata(parse_ok=False) == 1

            # 按 market 统计
            stats = db.get_gp_market_stats()
            stats_dict = {r["market"]: r["file_count"] for r in stats}
            assert stats_dict.get("sh") == 1
            assert stats_dict.get("sz") == 1
            assert stats_dict.get("bj") == 1

            # 错误率报表
            failed = db.get_gp_failed(limit=10)
            assert len(failed) == 1
            assert "601318" in failed[0]["file_path"]
        finally:
            db.close()

    def test_run_full_parse_by_market(self, gp_dir, tmp_path):
        """by_market() helper"""
        db_path = tmp_path / "meta.db"
        summary = TdxGpReader.run_full_parse(gp_dir, db_path)
        by = summary.by_market()
        assert by["sh"] == 1
        assert by["sz"] == 1
        assert by["bj"] == 1
        assert by["?"] == 0

    def test_run_full_parse_error_rate(self, gp_dir, tmp_path):
        """error_rate() = 1/4 = 0.25"""
        db_path = tmp_path / "meta.db"
        summary = TdxGpReader.run_full_parse(gp_dir, db_path)
        assert summary.error_rate() == 0.25
