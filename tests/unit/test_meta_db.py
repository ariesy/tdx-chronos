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

    def test_upgrade_pending_downloads(self, db):
        """批量升级 pending → success (7d window)"""
        # 插 5 行 pending
        for i in range(5):
            db.record_download(f"zip{i}.zip", "m1", 100, f"h{i}")
        # 插 1 行 failed (不应被升级)
        rid_failed = db.record_download("failed.zip", "m1", 100, "h_fail")
        db.update_parse_status(rid_failed, PARSE_STATUS_FAILED)

        upgraded = db.upgrade_pending_downloads(success_threshold=1)
        assert upgraded == 5

        rows = db.get_recent_downloads(limit=10)
        status_count = {}
        for r in rows:
            status_count[r["parse_status"]] = status_count.get(r["parse_status"], 0) + 1
        assert status_count.get(PARSE_STATUS_SUCCESS) == 5
        assert status_count.get(PARSE_STATUS_FAILED) == 1


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


# ---------------------------------------------------------------------
# TestQuarterMetadata (Sprint 8 T1)
# ---------------------------------------------------------------------
class TestQuarterMetadata:
    """Sprint 8 T1 · quarter_metadata 表 CRUD 测试"""

    def test_init_quarter_metadata_schema_creates_table(self, db):
        """init_quarter_metadata_schema 幂等创建 quarter_metadata 表"""
        # init_schema 已经调过 (fixture)
        conn = db._connect()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='quarter_metadata'"
        ).fetchall()
        assert len(rows) == 1

    def test_record_quarter_metadata_basic(self, db):
        """Upsert 基本字段"""
        db.record_quarter_metadata(
            report_date=20260331,
            file_path="/app/tdx-chronos/data/snapshot/2026-07-04/raw/gpcw20260331.zip",
            file_size=12_960_000,
            stock_count=5524,
            parquet_path="data/fin/parsed/gpcw20260331.parquet",
        )
        assert db.count_quarters() == 1
        assert db.count_quarters(parse_ok=True) == 1
        assert 20260331 in db.get_quarters()

    def test_record_quarter_metadata_placeholder(self, db):
        """164B 占位 zip 标记 is_placeholder=1"""
        db.record_quarter_metadata(
            report_date=20261231,  # 未来季
            file_path="/app/tdx-chronos/data/snapshot/2026-07-04/raw/gpcw20261231.zip",
            file_size=164,
            stock_count=0,
            parquet_path=None,
            is_placeholder=True,
        )
        # 包含 placeholder
        assert db.count_quarters() == 1
        # exclude_placeholders 过滤掉
        assert db.count_quarters(exclude_placeholders=True) == 0
        assert db.get_quarters(exclude_placeholders=True) == []

    def test_get_quarters_parsed_only(self, db):
        """parsed_only=True 仅返回 parse_ok=1 的 quarters"""
        # 成功
        db.record_quarter_metadata(
            report_date=20260331,
            file_path="/x/gpcw20260331.zip",
            file_size=12960000,
            stock_count=5524,
            parse_ok=True,
        )
        # 失败
        db.record_quarter_metadata(
            report_date=20251231,
            file_path="/x/gpcw20251231.zip",
            file_size=12_000_000,
            stock_count=0,
            parse_ok=False,
            error="corrupt zip",
        )
        # 全部
        assert db.count_quarters() == 2
        # parsed only
        assert db.get_quarters(parsed_only=True) == [20260331]

    def test_quarter_metadata_upsert_updates(self, db):
        """重复 record 同一个 report_date 会更新 (不是插入)"""
        # 第一次
        db.record_quarter_metadata(
            report_date=20260331,
            file_path="/x/old.zip",
            file_size=10_000_000,
            stock_count=5000,
            parse_ok=True,
        )
        assert db.count_quarters() == 1
        # 第二次 (同 date · 更新)
        db.record_quarter_metadata(
            report_date=20260331,
            file_path="/x/new.zip",
            file_size=12_960_000,
            stock_count=5524,
            parse_ok=True,
        )
        # 还是 1 行
        assert db.count_quarters() == 1
        # 但 stock_count 更新了
        conn = db._connect()
        row = conn.execute(
            "SELECT stock_count, file_size FROM quarter_metadata WHERE report_date=?",
            (20260331,),
        ).fetchone()
        assert row["stock_count"] == 5524
        assert row["file_size"] == 12_960_000


# ---------------------------------------------------------------------
# TestStaleSHMRecovery (Sprint 11 T9 · TDD)
# ---------------------------------------------------------------------

class TestStaleSHMRecovery:
    """Sprint 11 T9 · MetaDB._clean_stale_wal_files() 防御性清理

    根因: Sprint 10 集成测试期间 umask 0o277 创建了 400-permission
    meta.db-shm · 导致后续 WAL mmap 失败报 'readonly database'
    """

    def test_stale_shm_with_mode_400_is_removed(self, tmp_path):
        """stale 400-permission SHM 自动删除"""
        import os
        db_path = tmp_path / "meta.db"
        shm = tmp_path / "meta.db-shm"
        shm.write_bytes(b"\x00" * 1024)
        os.chmod(shm, 0o400)
        db = MetaDB(str(db_path))
        db.init_schema()
        rid = db.record_download("test.zip", "test.tdx", 100, "abc", "pending", None)
        assert rid > 0
        db.close()
        # 验证 SHM 已被 SQLite 重建为正常权限 (≥ 0o600) 或被 _clean_stale_wal_files 删了
        if shm.exists():
            assert (shm.stat().st_mode & 0o777) >= 0o600, f"SHM mode={oct(shm.stat().st_mode & 0o777)}"

    def test_empty_wal_with_no_shm_is_removed(self, tmp_path):
        """0 字节 WAL + 无 SHM 自动删除"""
        db_path = tmp_path / "meta.db"
        wal = tmp_path / "meta.db-wal"
        wal.write_bytes(b"")
        assert wal.exists() and wal.stat().st_size == 0
        db = MetaDB(str(db_path))
        db.init_schema()
        db.close()
        assert not wal.exists(), f"WAL should be removed, but exists with size {wal.stat().st_size}"

    def test_record_download_after_stale_shm_recovery(self, tmp_path):
        """完整场景: stale SHM → MetaDB → record_download PASS"""
        import os
        db_path = tmp_path / "meta.db"
        shm = tmp_path / "meta.db-shm"
        shm.write_bytes(b"\x00" * 1024)
        os.chmod(shm, 0o400)
        db = MetaDB(str(db_path))
        db.init_schema()
        rid = db.record_download("recovered.zip", "test.tdx", 100, "abc", "pending", None)
        assert rid > 0
        db.close()


# ─── Sprint 12 T5a · MetaDB public API (get_symbol + list_symbols) ───


def test_get_symbol_found(db):
    """get_symbol 找到时返回 dict"""
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")
    result = db.get_symbol("sh600000")
    assert result is not None
    assert result["symbol"] == "sh600000"
    assert result["market"] == "sh"
    assert result["first_listing_date"] == 19991110


def test_get_symbol_not_found_returns_none(db):
    """get_symbol 找不到返回 None (与 TdxChronos.symbol_info 的空 dict 区分)"""
    result = db.get_symbol("sh999999")
    assert result is None


def test_list_symbols_all_sorted_asc(db):
    """list_symbols(market=None) 返回所有 symbols, sorted ASC"""
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")
    db.record_symbol("sz000001", "sz", 19910403, 8000, "hsjday.zip")
    db.record_symbol("bj430017", "bj", 20200807, 100, "hsjday.zip")
    result = db.list_symbols()
    assert result == ["bj430017", "sh600000", "sz000001"]


def test_list_symbols_filtered_by_market(db):
    """list_symbols(market='sh') 仅返回 sh 市场 symbols"""
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")
    db.record_symbol("sh600036", "sh", 20020423, 3000, "hsjday.zip")
    db.record_symbol("sz000001", "sz", 19910403, 8000, "hsjday.zip")
    result = db.list_symbols(market="sh")
    assert result == ["sh600000", "sh600036"]


def test_list_symbols_case_insensitive_market(db):
    """list_symbols(market='SH') 与 'sh' 等价 (大小写不敏感)"""
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")
    result = db.list_symbols(market="SH")
    assert result == ["sh600000"]


# ─── Sprint 11 T1 · should_skip_quarter + file_mtime ─────────────────────────


class TestShouldSkipQuarter:
    """Sprint 11 T1 · MetaDB.should_skip_quarter() 增量跳过判断"""

    def test_skip_when_parse_ok_and_mtime_unchanged(self, db, tmp_path):
        """已 parse_ok=1 + mtime 同 → skip"""
        raw_path = tmp_path / "gpcw20260331.dat"
        raw_path.write_bytes(b"\x00" * 100)
        mtime = raw_path.stat().st_mtime

        db.record_quarter_metadata(
            report_date=20260331,
            file_path=str(raw_path),
            file_size=100,
            stock_count=5524,
            parse_ok=True,
        )
        # Manually set file_mtime in DB (simulate previous parse)
        conn = db._connect()
        conn.execute(
            "UPDATE quarter_metadata SET file_mtime = ? WHERE report_date = ?",
            (mtime, 20260331),
        )

        result = db.should_skip_quarter(20260331, raw_path)
        assert result is True

    def test_no_skip_when_parse_ok_but_mtime_changed(self, db, tmp_path):
        """已 parse_ok=1 + mtime 变 → 不 skip"""
        raw_path = tmp_path / "gpcw20260331.dat"
        raw_path.write_bytes(b"\x00" * 100)
        old_mtime = raw_path.stat().st_mtime - 10

        db.record_quarter_metadata(
            report_date=20260331,
            file_path=str(raw_path),
            file_size=100,
            stock_count=5524,
            parse_ok=True,
        )
        conn = db._connect()
        conn.execute(
            "UPDATE quarter_metadata SET file_mtime = ? WHERE report_date = ?",
            (old_mtime, 20260331),
        )

        result = db.should_skip_quarter(20260331, raw_path)
        assert result is False

    def test_no_skip_when_no_db_record(self, db, tmp_path):
        """无 DB record → 不 skip (需要 parse)"""
        raw_path = tmp_path / "gpcw20260331.dat"
        raw_path.write_bytes(b"\x00" * 100)

        result = db.should_skip_quarter(20260331, raw_path)
        assert result is False

    def test_no_skip_when_parse_ok_is_zero(self, db, tmp_path):
        """parse_ok=0 (之前 failed) → 不 skip (重试)"""
        raw_path = tmp_path / "gpcw20260331.dat"
        raw_path.write_bytes(b"\x00" * 100)
        mtime = raw_path.stat().st_mtime

        db.record_quarter_metadata(
            report_date=20260331,
            file_path=str(raw_path),
            file_size=100,
            stock_count=0,
            parse_ok=False,
            error="corrupt zip",
        )
        conn = db._connect()
        conn.execute(
            "UPDATE quarter_metadata SET file_mtime = ? WHERE report_date = ?",
            (mtime, 20260331),
        )

        result = db.should_skip_quarter(20260331, raw_path)
        assert result is False

    def test_no_skip_when_raw_path_not_exists(self, db, tmp_path):
        """raw_path 不存在 → 不 skip (留给 caller 处理)"""
        nonexistent = tmp_path / "nonexistent.dat"

        result = db.should_skip_quarter(20260331, nonexistent)
        assert result is False
