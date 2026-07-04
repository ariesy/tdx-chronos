"""Sprint 2 · meta/db.py 单元测试

8 测试覆盖 (用 :memory: 不写磁盘):
  TestSchema:           schema 创建幂等
  TestRecordSymbol:     upsert + 覆盖 + 查询
  TestRecordDownload:   insert + 状态更新
  TestGetUnparsedFiles: 重跑场景
  TestIntegration:      端到端 (parse 真 .day -> 写 db -> 查询)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tdx_chronos.meta.db import (
    MetaDB,
    PARSE_STATUS_FAILED,
    PARSE_STATUS_PARTIAL,
    PARSE_STATUS_PENDING,
    PARSE_STATUS_SUCCESS,
)


# ---------------------------------------------------------------------
# fixture · :memory: db
# ---------------------------------------------------------------------
@pytest.fixture
def db():
    """每次测试 fresh :memory: db · init_schema 已调"""
    d = MetaDB(":memory:")
    d.init_schema()
    yield d
    d.close()


# ---------------------------------------------------------------------
# TestSchema
# ---------------------------------------------------------------------
class TestSchema:
    def test_init_schema_creates_both_tables(self, db):
        conn = db._connect()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "ORDER BY name"
        ).fetchall()
        table_names = {r["name"] for r in rows}
        assert "symbol_metadata" in table_names
        assert "download_log" in table_names

    def test_init_schema_idempotent(self):
        """多次 init_schema 不报错 (CREATE TABLE IF NOT EXISTS)"""
        d = MetaDB(":memory:")
        try:
            d.init_schema()
            d.init_schema()  # 第二次幂等
            d.init_schema()  # 第三次幂等
            # 还有 2 张表
            assert d.count_symbols() == 0
        finally:
            d.close()


# ---------------------------------------------------------------------
# TestRecordSymbol
# ---------------------------------------------------------------------
class TestRecordSymbol:
    def test_insert_basic(self, db):
        db.record_symbol(
            symbol="sh600000",
            market="sh",
            first_listing_date=19991110,
            record_count=6338,
            source_zip="hsjday.zip",
            parquet_path="data/parquet/sh/sh600000.parquet",
        )
        assert db.count_symbols() == 1

    def test_get_symbols_by_market(self, db):
        db.record_symbol("sh600000", "sh", 19991110, 6338, "hsjday.zip", "x")
        db.record_symbol("sh600519", "sh", 20010827, 5953, "hsjday.zip", "y")
        db.record_symbol("sz000001", "sz", 19910403, 8402, "hsjday.zip", "z")
        db.record_symbol("bj920193", "bj", 20260101, 2, "hsjday.zip", "w")

        sh = db.get_symbols_by_market("sh")
        sz = db.get_symbols_by_market("sz")
        bj = db.get_symbols_by_market("bj")

        assert sh == ["sh600000", "sh600519"]
        assert sz == ["sz000001"]
        assert bj == ["bj920193"]

    def test_upsert_overwrites(self, db):
        """Same symbol insert -> upsert DO UPDATE"""
        db.record_symbol("sh600000", "sh", 19991110, 6338, "hsjday.zip", "old.parquet")
        db.record_symbol(
            "sh600000", "sh", 19991110, 7000, "hsjday.zip", "new.parquet",
        )
        # 仍是 1 行 (覆盖)
        assert db.count_symbols() == 1
        # 新 parquet_path 覆盖
        conn = db._connect()
        row = conn.execute(
            "SELECT * FROM symbol_metadata WHERE symbol=?", ("sh600000",)
        ).fetchone()
        assert row["parquet_path"] == "new.parquet"
        assert row["record_count"] == 7000


# ---------------------------------------------------------------------
# TestRecordDownload
# ---------------------------------------------------------------------
class TestRecordDownload:
    def test_insert_returns_rowid(self, db):
        rid = db.record_download(
            zip_name="hsjday.zip",
            mirror="data.tdx.com.cn",
            size_bytes=540_000_000,
            sha256="abc123",
        )
        assert isinstance(rid, int)
        assert rid > 0

    def test_update_parse_status_success(self, db):
        rid = db.record_download("hsjday.zip", None, 100, "h")
        db.update_parse_status(rid, PARSE_STATUS_SUCCESS)
        row = db._connect().execute(
            "SELECT parse_status FROM download_log WHERE id=?", (rid,)
        ).fetchone()
        assert row["parse_status"] == PARSE_STATUS_SUCCESS

    def test_update_parse_status_failed_with_message(self, db):
        rid = db.record_download("hsjday.zip", None, 100, "h")
        db.update_parse_status(rid, PARSE_STATUS_FAILED, "bin file truncated")
        row = db._connect().execute(
            "SELECT parse_status, error_msg FROM download_log WHERE id=?", (rid,)
        ).fetchone()
        assert row["parse_status"] == PARSE_STATUS_FAILED
        assert row["error_msg"] == "bin file truncated"

    def test_update_invalid_status_raises(self, db):
        rid = db.record_download("hsjday.zip", None, 100, "h")
        with pytest.raises(ValueError, match="Unknown parse_status"):
            db.update_parse_status(rid, "BOGUS")

    def test_get_recent_downloads(self, db):
        # 插 3 条
        db.record_download("hsjday.zip", "m1", 100, "h1")
        db.record_download("tdxfin.zip", "m1", 200, "h2")
        db.record_download("tdxgp.zip", "m1", 300, "h3")
        rows = db.get_recent_downloads(limit=10)
        assert len(rows) == 3
        # 最新的在前面
        assert rows[0]["zip_name"] == "tdxgp.zip"


# ---------------------------------------------------------------------
# TestGetUnparsedFiles
# ---------------------------------------------------------------------
class TestGetUnparsedFiles:
    def test_empty_when_all_parsed(self, db):
        """每个 symbol 都有 parquet_path -> 返回 []"""
        db.record_symbol("sh600000", "sh", 19991110, 1, "hsjday.zip", "x.parquet")
        result = db.get_unparsed_files("hsjday.zip")
        assert result == []

    def test_returns_symbols_without_parquet_path(self, db):
        """没有 parquet_path 的 symbol 出现在 unparsed 列表"""
        db.record_symbol("sh600000", "sh", 19991110, 1, "hsjday.zip", "x.parquet")
        db.record_symbol("sh600519", "sh", 20010827, 1, "hsjday.zip", None)  # 没 parquet
        db.record_symbol("sz000001", "sz", 19910403, 1, "hsjday.zip", "z.parquet")
        result = db.get_unparsed_files("hsjday.zip")
        assert result == ["sh600519"]


# ---------------------------------------------------------------------
# TestIntegration · 真 .day + 解析 + meta.db
# ---------------------------------------------------------------------
class TestIntegration:
    """端到端: 解析真 .day fixture -> 写 meta.db -> 查回

    这是 Sprint 2 D1 末 M1 验证里程碑的早期版本
    (D2 下午会扩展到 12,256 文件 · 这里只 3 个 fixture)
    """

    def test_parse_fixture_then_record_symbol(self, db):
        from tdx_chronos.sources.official_zip import OfficialZipParser

        fixtures = Path(__file__).parent.parent / "fixtures" / "day"
        parser = OfficialZipParser(source_zip="hsjday.zip")

        # 解析 3 个真 fixture
        for market, symbol in [
            ("sh", "sh600000"), ("sh", "sh600519"), ("sz", "sz000001"),
        ]:
            day_path = fixtures / market / "lday" / f"{symbol}.day"
            result = parser.parse_day_file(day_path)
            db.record_symbol(
                symbol=result.symbol,
                market=result.market,
                first_listing_date=result.first_date,
                record_count=result.record_count,
                source_zip="hsjday.zip",
                parquet_path=f"data/parquet/{market}/{symbol}.parquet",
            )

        # 验证: 3 行 symbol_metadata
        assert db.count_symbols() == 3
        # sh 应该有 2 行
        assert len(db.get_symbols_by_market("sh")) == 2
        # sz 应该有 1 行 (sz000001)
        assert db.get_symbols_by_market("sz") == ["sz000001"]
        # bj 没有
        assert db.get_symbols_by_market("bj") == []

        # 查回 sh600000: first_listing_date=19991110
        conn = db._connect()
        row = conn.execute(
            "SELECT first_listing_date, record_count FROM symbol_metadata "
            "WHERE symbol=?", ("sh600000",)
        ).fetchone()
        assert row["first_listing_date"] == 19991110
        assert row["record_count"] == 6338
