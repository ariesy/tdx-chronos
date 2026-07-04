"""Sprint 2 · official_zip 流式 + run_full_parse 测试

5 fixture + 集成测试:
- TestParseHsjdayDir      · batch 遍历 fixture 全集
- TestRunFullParse        · 一键全量 (fixture + 元数据 + Parquet)
- TestErrorHandling       · 坏文件不 crash · download_log 记录
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tdx_chronos.meta.db import (
    MetaDB,
    PARSE_STATUS_FAILED,
)
from tdx_chronos.sources.official_zip import (
    BatchSummary,
    OfficialZipParser,
    parse_hsjday_dir,
    run_full_parse,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "day"


# ---------------------------------------------------------------------
# TestParseHsjdayDir
# ---------------------------------------------------------------------
class TestParseHsjdayDir:
    def test_iterates_all_5_fixtures(self, tmp_path):
        """batch 遍历 fixture (5 个真 .day)"""
        parser = OfficialZipParser()
        files = list(parser.iter_day_files(FIXTURES))
        assert len(files) == 5

    def test_yields_parse_results_in_order(self, tmp_path):
        """parse_hsjday_dir 按字典序 yield ParseResult"""
        results = list(parse_hsjday_dir(
            FIXTURES, tmp_path / "parquet", show_progress=False,
        ))
        assert len(results) == 5
        # 全部 market 推断成功 (无 "?" 错误标记)
        assert all(r.market in {"sh", "sz", "bj"} for r in results)
        # 字典序: bj920193 < sh600000 < sh600519 < sz000001 < sz300750
        assert results[0].symbol == "bj920193"
        assert results[-1].symbol == "sz300750"

    def test_writes_parquet_files_per_market(self, tmp_path):
        """§四.D 输出目录结构: parquet/{sh,sz,bj}/<symbol>.parquet"""
        output_dir = tmp_path / "parquet"
        list(parse_hsjday_dir(FIXTURES, output_dir, show_progress=False))
        # sh 目录有 sh600000 + sh600519
        sh_files = sorted((output_dir / "sh").glob("*.parquet"))
        assert {f.stem for f in sh_files} == {"sh600000", "sh600519"}
        # sz 目录有 sz000001 + sz300750
        sz_files = sorted((output_dir / "sz").glob("*.parquet"))
        assert {f.stem for f in sz_files} == {"sz000001", "sz300750"}
        # bj 目录有 bj920193
        bj_files = sorted((output_dir / "bj").glob("*.parquet"))
        assert {f.stem for f in bj_files} == {"bj920193"}

    def test_records_symbol_metadata_when_db_provided(self, tmp_path):
        """提供 MetaDB → symbol_metadata 写入追溯链"""
        db_path = tmp_path / "meta.db"
        db = MetaDB(db_path)
        db.init_schema()
        try:
            results = list(parse_hsjday_dir(
                FIXTURES, tmp_path / "parquet", db=db, show_progress=False,
            ))
            assert len(results) == 5
            assert db.count_symbols() == 5

            # sh 查询应有 2 行
            sh = db.get_symbols_by_market("sh")
            assert sh == ["sh600000", "sh600519"]

            # sh600000 在 db 中有 parquet_path
            conn = db._connect()
            row = conn.execute(
                "SELECT parquet_path FROM symbol_metadata WHERE symbol=?",
                ("sh600000",),
            ).fetchone()
            assert row["parquet_path"] is not None
            assert row["parquet_path"].endswith("sh/sh600000.parquet")
        finally:
            db.close()


# ---------------------------------------------------------------------
# TestRunFullParse
# ---------------------------------------------------------------------
class TestRunFullParse:
    def test_runs_on_fixtures_yields_summary(self, tmp_path):
        """run_full_parse · 一键全量 fixture + meta.db + Parquet"""
        summary = run_full_parse(
            FIXTURES,
            tmp_path / "parquet",
            tmp_path / "meta.db",
            show_progress=False,
        )
        assert isinstance(summary, BatchSummary)
        assert summary.total_files == 5
        assert summary.parsed_ok == 5
        assert summary.parsed_failed == 0
        # 5 fixture 解析时间应 < 10s
        assert summary.elapsed_seconds < 10.0

        # meta.db 应该含 5 行
        db = MetaDB(tmp_path / "meta.db")
        try:
            assert db.count_symbols() == 5
        finally:
            db.close()

    def test_summary_tracks_disk_usage(self, tmp_path):
        """input 字节 + output 字节累计"""
        summary = run_full_parse(
            FIXTURES,
            tmp_path / "parquet",
            tmp_path / "meta.db",
            show_progress=False,
        )
        # 5 fixture 大小 ~700KB → bytes_read 应 > 0
        assert summary.bytes_read > 500_000  # > 500 KB
        # Parquet 输出比输入略小 (列存压缩)
        assert summary.parquet_bytes > 0
        # 输入 5×~140KB > 500KB, 输出 5× Parquet (>300KB)
        assert summary.parquet_bytes < summary.bytes_read * 2

    def test_summary_has_utc_timestamps(self, tmp_path):
        """start_at + end_at 都是 UTC datetime"""
        summary = run_full_parse(
            FIXTURES,
            tmp_path / "parquet",
            tmp_path / "meta.db",
            show_progress=False,
        )
        assert summary.start_at.tzinfo is not None
        assert summary.end_at.tzinfo is not None
        assert summary.end_at >= summary.start_at


# ---------------------------------------------------------------------
# TestErrorHandling · 坏文件不 crash + 记录失败
# ---------------------------------------------------------------------
class TestErrorHandling:
    def test_bad_file_does_not_crash(self, tmp_path):
        """坏文件 (不是 32 倍数) 不 crash · yield 错误标记"""
        # 创建 1 个坏文件: 65 字节 (不是 32 倍数 · struct.error)
        bad_dir = tmp_path / "bad_raw" / "sh" / "lday"
        bad_dir.mkdir(parents=True)
        bad_file = bad_dir / "sh999999.day"
        bad_file.write_bytes(b"\x00" * 65)  # 65 字节 → struct.error
        # 加 1 个真 .day
        good_src = FIXTURES / "sh" / "lday" / "sh600000.day"
        good_dst = bad_dir / "sh600000.day"
        good_dst.write_bytes(good_src.read_bytes())

        results = list(parse_hsjday_dir(
            tmp_path / "bad_raw",
            tmp_path / "parquet",
            show_progress=False,
        ))
        # 2 个文件: 1 success + 1 failed
        assert len(results) == 2
        good_results = [r for r in results if r.market != "?"]
        bad_results = [r for r in results if r.market == "?"]
        assert len(good_results) == 1
        assert len(bad_results) == 1
        # bad_results 标记为 sh999999 (path stem)
        assert bad_results[0].symbol == "sh999999"

    def test_bad_file_recorded_in_download_log(self, tmp_path):
        """坏文件被记录到 download_log(parse_status='failed')"""
        bad_dir = tmp_path / "bad_raw" / "sh" / "lday"
        bad_dir.mkdir(parents=True)
        bad_file = bad_dir / "sh999999.day"
        bad_file.write_bytes(b"\x00" * 65)  # 65 字节 → struct.error

        db = MetaDB(tmp_path / "meta.db")
        db.init_schema()
        try:
            list(parse_hsjday_dir(
                tmp_path / "bad_raw",
                tmp_path / "parquet",
                db=db,
                show_progress=False,
            ))
            # download_log 应有 1 行 failed
            rows = db.get_recent_downloads(limit=10)
            assert len(rows) == 1
            assert rows[0]["parse_status"] == PARSE_STATUS_FAILED
            assert rows[0]["error_msg"] is not None
        finally:
            db.close()
