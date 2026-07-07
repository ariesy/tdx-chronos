"""Phase 1 TDD · TdxChronos facade scaffolding"""
import pandas as pd
import pytest
from pathlib import Path


def test_tdx_client_can_be_imported():
    from tdx_chronos.client import TdxChronos
    assert TdxChronos is not None


@pytest.fixture
def fake_data_dir(tmp_path):
    """伪造 5 子路径 + meta.db · 模拟完整数据目录"""
    (tmp_path / "parquet_compact").mkdir()
    (tmp_path / "fin" / "parsed").mkdir(parents=True)
    (tmp_path / "gp").mkdir()
    (tmp_path / "gp" / "records.parquet").touch()
    (tmp_path / "index").mkdir()
    (tmp_path / "index" / "indices.parquet").touch()
    (tmp_path / "meta").mkdir()
    (tmp_path / "meta" / "meta.db").touch()
    return tmp_path


@pytest.fixture
def populated_data_dir(fake_data_dir):
    """fake_data_dir + MetaDB schema initialized, ready for record_symbol() calls"""
    from tdx_chronos.meta.db import MetaDB
    db = MetaDB(str(fake_data_dir / "meta" / "meta.db"))
    db.init_schema()
    db.close()
    return fake_data_dir


def test_init_with_valid_data_dir(fake_data_dir):
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    assert tdx.data_dir == fake_data_dir.resolve()


def test_init_with_missing_data_dir_raises(tmp_path):
    from tdx_chronos.client import TdxChronos
    with pytest.raises(FileNotFoundError, match="data_dir 不存在"):
        TdxChronos(data_dir=tmp_path / "nonexistent", readonly=False)


def test_init_with_incomplete_data_dir_raises(tmp_path):
    """只建部分子目录 → 应报 5 子路径缺失"""
    (tmp_path / "parquet_compact").mkdir()  # 只 1 个
    from tdx_chronos.client import TdxChronos
    with pytest.raises(FileNotFoundError, match="缺失"):
        TdxChronos(data_dir=tmp_path, readonly=False)


# ─── Task 3: symbol_info + list_symbols ────────────────────────────────────────

def test_symbol_info_returns_dict(populated_data_dir):
    """先 init 一个临时 meta.db + 一行 symbol_metadata"""
    from tdx_chronos.meta.db import MetaDB
    db = MetaDB(str(populated_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip", "/tmp/a.parquet")
    db.close()

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    info = tdx.symbol_info("sh600000")
    assert info["symbol"] == "sh600000"
    assert info["market"] == "sh"


def test_close_releases_db_even_if_chmod_fails(monkeypatch, populated_data_dir):
    """Critical #1: chmod raise PermissionError → db.close() must STILL be called"""
    import tdx_chronos.client as client_mod

    # Pre-populate so lazy db is opened
    from tdx_chronos.meta.db import MetaDB
    db = MetaDB(str(populated_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip", "/tmp/a.parquet")
    db.close()

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=populated_data_dir, readonly=True)

    # Force lazy db open
    info = tdx.symbol_info("sh600000")
    assert info["symbol"] == "sh600000"
    assert tdx._db is not None  # confirm db is open

    # Monkeypatch chmod to fail
    def fake_chmod(path, mode):
        raise PermissionError(f"simulated chmod failure on {path}")
    monkeypatch.setattr(client_mod.os, "chmod", fake_chmod)

    # Close should raise RuntimeError (chmod failed)
    with pytest.raises(RuntimeError, match="close\\(\\) failed to restore"):
        tdx.close()

    # But db should still have been released
    assert tdx._db is None, "db connection was leaked — Critical #1 not fixed"


def test_symbol_info_unknown_returns_empty(fake_data_dir):
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    assert tdx.symbol_info("sh999999") == {}


def test_list_symbols_all(populated_data_dir):
    from tdx_chronos.meta.db import MetaDB
    db = MetaDB(str(populated_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh600000", "sh", 19991110, 1, "x", "y")
    db.record_symbol("sz000001", "sz", 19910403, 1, "x", "y")
    db.record_symbol("bj838000", "bj", 20200101, 1, "x", "y")
    db.close()
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    syms = tdx.list_symbols()
    assert set(syms) == {"sh600000", "sz000001", "bj838000"}


def test_list_symbols_by_market(populated_data_dir):
    """取仅 sh"""
    from tdx_chronos.meta.db import MetaDB
    db = MetaDB(str(populated_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh600000", "sh", 19991110, 1, "x", "y")
    db.record_symbol("sz000001", "sz", 19910403, 1, "x", "y")
    db.record_symbol("bj838000", "bj", 20200101, 1, "x", "y")
    db.close()
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    sh = tdx.list_symbols(market="sh")
    assert sh == ["sh600000"]


# ─── Task 4: kline (pyarrow predicate pushdown) ────────────────────────────────

def test_kline_single_symbol(fake_data_dir):
    """建 sh.parquet 含 sh600000 三行 → 读必须返回"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.table({
        "symbol": ["sh600000", "sh600000", "sh600000"],
        "date": [20240102, 20240103, 20240104],
        "open": [10.0, 10.5, 11.0],
        "high": [10.5, 11.0, 11.5],
        "low": [9.8, 10.3, 10.8],
        "close": [10.3, 10.8, 11.2],
        "volume": [1000, 2000, 3000],
        "amount": [10250.0, 21600.0, 33780.0],
    })
    pq.write_table(table, str(fake_data_dir / "parquet_compact" / "sh.parquet"))

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.kline("sh600000")
    assert len(df) == 3
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume", "amount"]


def test_kline_with_date_range(fake_data_dir):
    """start='2024-01-02' end='2024-01-03' → 2 行"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.table({
        "symbol": ["sh600000"] * 5,
        "date": [20240101, 20240102, 20240103, 20240104, 20240105],
        "open": [10.0, 10.5, 11.0, 11.5, 12.0],
        "high": [10.5, 11.0, 11.5, 12.0, 12.5],
        "low": [9.8, 10.3, 10.8, 11.3, 11.8],
        "close": [10.3, 10.8, 11.2, 11.7, 12.2],
        "volume": [1000, 2000, 3000, 4000, 5000],
        "amount": [10250.0, 21600.0, 33780.0, 47160.0, 61600.0],
    })
    pq.write_table(table, str(fake_data_dir / "parquet_compact" / "sh.parquet"))

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.kline("sh600000", start="2024-01-02", end="2024-01-03")
    assert len(df) == 2
    assert list(df["date"]) == [20240102, 20240103]


def test_kline_unknown_symbol_returns_empty(fake_data_dir):
    """sh999999 不存在 → 不 raise, 返回空 DataFrame"""
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.kline("sh999999")
    assert df.empty


def test_kline_corrupt_parquet_returns_empty_with_warning(caplog, fake_data_dir):
    """corrupted parquet → empty DataFrame + warning logged (not silent)"""
    import logging
    market_file = fake_data_dir / "parquet_compact" / "sh.parquet"
    market_file.write_text("this is not a valid parquet file")

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    with caplog.at_level(logging.WARNING):
        df = tdx.kline("sh600000")
    assert df.empty
    assert any("kline read failed" in r.message for r in caplog.records)


def test_kline_invalid_date_range_raises(fake_data_dir):
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    with pytest.raises(ValueError, match="must be <="):
        tdx.kline("sh600000", start="2024-01-05", end="2024-01-03")


def test_kline_columns_projection(fake_data_dir):
    """columns 参数只返回指定列"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.table({
        "symbol": ["sh600000", "sh600000"],
        "date": [20240102, 20240103],
        "open": [10.0, 10.5],
        "high": [10.5, 11.0],
        "low": [9.8, 10.3],
        "close": [10.3, 10.8],
        "volume": [1000, 2000],
        "amount": [10250.0, 21600.0],
    })
    pq.write_table(table, str(fake_data_dir / "parquet_compact" / "sh.parquet"))

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.kline("sh600000", columns=["date", "close"])
    assert list(df.columns) == ["date", "close"]
    assert len(df) == 2


# ─── Task 5: finance + shareholders + index_klines + list_quarters + doctor ─────

def test_finance_single_quarter(fake_data_dir):
    """建 1 季度 parquet 含 sh600000 一行"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.table({
        "code": ["600000"],
        "report_date": [20251231],
        "资产总计": [1000.0],
        "负债合计": [400.0],
        "所有者权益合计": [600.0],
        "净利润": [50.0],
        "基本每股收益": [0.5],
        "稀释每股收益": [0.4],
        "营业总收入": [200.0],
        "营业收入": [180.0],
        "营业成本": [120.0],
        "利润总额": [70.0],
        "经营活动产生的现金流量净额": [80.0],
        "投资活动产生的现金流量净额": [-20.0],
        "筹资活动产生的现金流量净额": [-10.0],
        "现金及现金等价物净增加额": [50.0],
        "资产收益率": [0.05],
        "净资产收益率": [0.083],
        "资产负债率": [0.4],
    })
    pq.write_table(table, str(fake_data_dir / "fin" / "parsed" / "gpcw20251231.parquet"))

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.finance("sh600000", report_date="2025-12-31")
    assert len(df) == 1
    assert "资产总计" in df.columns


def test_finance_all_quarters(fake_data_dir):
    """report_date=None → 返回全部 available quarters"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    table_empty = pa.table({"code": [], "report_date": [], "资产总计": []})
    table1 = pa.table({
        "code": ["600000"], "report_date": [20251231],
        "资产总计": [1000.0], "负债合计": [400.0], "所有者权益合计": [600.0],
        "净利润": [50.0], "基本每股收益": [0.5], "稀释每股收益": [0.4],
        "营业总收入": [200.0], "营业收入": [180.0], "营业成本": [120.0],
        "利润总额": [70.0], "经营活动产生的现金流量净额": [80.0],
        "投资活动产生的现金流量净额": [-20.0],
        "筹资活动产生的现金流量净额": [-10.0],
        "现金及现金等价物净增加额": [50.0],
        "资产收益率": [0.05], "净资产收益率": [0.083], "资产负债率": [0.4],
    })
    table2 = pa.table({
        "code": ["600000"], "report_date": [20250930],
        "资产总计": [950.0], "负债合计": [380.0], "所有者权益合计": [570.0],
        "净利润": [45.0], "基本每股收益": [0.45], "稀释每股收益": [0.36],
        "营业总收入": [190.0], "营业收入": [170.0], "营业成本": [115.0],
        "利润总额": [65.0], "经营活动产生的现金流量净额": [70.0],
        "投资活动产生的现金流量净额": [-15.0],
        "筹资活动产生的现金流量净额": [-8.0],
        "现金及现金等价物净增加额": [47.0],
        "资产收益率": [0.047], "净资产收益率": [0.079], "资产负债率": [0.40],
    })
    pq.write_table(table1, str(fake_data_dir / "fin" / "parsed" / "gpcw20251231.parquet"))
    pq.write_table(table2, str(fake_data_dir / "fin" / "parsed" / "gpcw20250930.parquet"))

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.finance("sh600000")  # 默认: 全部 quarters
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2  # 两个季度


def test_finance_unknown_symbol_returns_empty(fake_data_dir):
    """sh999999 不存在 → 返回空 DataFrame"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.table({"code": ["600000"], "report_date": [20251231], "资产总计": [1000.0]})
    pq.write_table(table, str(fake_data_dir / "fin" / "parsed" / "gpcw20251231.parquet"))

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.finance("sh999999")
    assert df.empty


def test_shareholders_single_symbol(fake_data_dir):
    """gp/records.parquet 含 sh600000 一行"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.table({
        "symbol": ["sh600000"],
        "name": ["ABC Corp"],
        "share": [1000.0],
        "share_type": ["A股"],
        "holder_type": ["流通股东"],
    })
    pq.write_table(table, str(fake_data_dir / "gp" / "records.parquet"))

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.shareholders("sh600000")
    assert len(df) == 1
    assert "symbol" in df.columns


def test_shareholders_unknown_symbol_returns_empty(fake_data_dir):
    """sh999999 不存在 → 返回空 DataFrame"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.table({"symbol": ["sh600000"], "name": ["ABC"], "share": [1000.0]})
    pq.write_table(table, str(fake_data_dir / "gp" / "records.parquet"))

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.shareholders("sh999999")
    assert df.empty


def test_index_klines_sh000001(fake_data_dir):
    """index/indices.parquet 含 sh000001 三行"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.table({
        "index_code": ["sh000001", "sh000001", "sh000001"],
        "date": [20240101, 20240102, 20240103],
        "open": [3000.0, 3010.0, 3020.0],
        "high": [3010.0, 3020.0, 3030.0],
        "low": [2990.0, 3000.0, 3010.0],
        "close": [3005.0, 3015.0, 3025.0],
        "volume": [100, 200, 300],
    })
    pq.write_table(table, str(fake_data_dir / "index" / "indices.parquet"))

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.index_klines("sh000001")
    assert len(df) == 3
    assert "close" in df.columns


def test_index_klines_with_date_range(fake_data_dir):
    """start + end 过滤"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.table({
        "index_code": ["sh000001"] * 5,
        "date": [20240101, 20240102, 20240103, 20240104, 20240105],
        "open": [3000.0, 3010.0, 3020.0, 3030.0, 3040.0],
        "high": [3010.0, 3020.0, 3030.0, 3040.0, 3050.0],
        "low": [2990.0, 3000.0, 3010.0, 3020.0, 3030.0],
        "close": [3005.0, 3015.0, 3025.0, 3035.0, 3045.0],
        "volume": [100, 200, 300, 400, 500],
    })
    pq.write_table(table, str(fake_data_dir / "index" / "indices.parquet"))

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.index_klines("sh000001", start="2024-01-02", end="2024-01-04")
    assert len(df) == 3
    assert list(df["date"]) == [20240102, 20240103, 20240104]


def test_list_quarters(fake_data_dir):
    """fin/parsed 下 2 个 parquet → 2 个 quarter string"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.table({"code": [], "report_date": []})
    pq.write_table(table, str(fake_data_dir / "fin" / "parsed" / "gpcw20251231.parquet"))
    pq.write_table(table, str(fake_data_dir / "fin" / "parsed" / "gpcw20250930.parquet"))

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    quarters = tdx.list_quarters()
    assert "2025-12-31" in quarters
    assert "2025-09-30" in quarters


def test_list_quarters_empty_returns_empty_list(fake_data_dir):
    """fin/parsed 下无 parquet → 返回空 list"""
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    quarters = tdx.list_quarters()
    assert quarters == []


# ─── Sprint 10 T5-fix: missing-file + ratio_only tests ───────────────────────

def _make_data_dir_without_required_parquet_files(tmp_path):
    """Creates data dir structure WITHOUT gp/records.parquet and index/indices.parquet.
    Used to test that shareholders/index_klines handle missing files gracefully."""
    (tmp_path / "parquet_compact").mkdir()
    (tmp_path / "fin" / "parsed").mkdir(parents=True)
    (tmp_path / "gp").mkdir()          # NOTE: no records.parquet created
    (tmp_path / "index").mkdir()        # NOTE: no indices.parquet created
    (tmp_path / "meta").mkdir()
    (tmp_path / "meta" / "meta.db").touch()
    return tmp_path


def test_shareholders_missing_file_returns_empty(tmp_path):
    """gp/records.parquet 不存在 → empty DataFrame, 不 raise"""
    data_dir = _make_data_dir_without_required_parquet_files(tmp_path)
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=data_dir, readonly=False)
    df = tdx.shareholders("sh600000")
    assert df.empty


def test_index_klines_missing_file_returns_empty(tmp_path):
    """index/indices.parquet 不存在 → empty DataFrame, 不 raise"""
    data_dir = _make_data_dir_without_required_parquet_files(tmp_path)
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=data_dir, readonly=False)
    df = tdx.index_klines("sh000001")
    assert df.empty


def test_finance_ratio_only_filter(fake_data_dir):
    """ratio_only=True 保留 ratio/率 columns, 剔除其他"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    # NOTE: code column stores bare 6-digit, not prefixed (matching finance() logic)
    table = pa.table({
        "code": ["600000"],
        "report_date": [20251231],
        "资产总计": [1000.0],          # non-ratio
        "负债合计": [400.0],           # non-ratio
        "净利润": [50.0],              # non-ratio
        "净资产收益率": [10.5],         # ratio (率)
        "资产负债率": [40.0],          # ratio (率)
        "current_ratio": [1.5],        # ratio (English)
        "pe_ratio": [12.0],            # ratio (English)
    })
    pq.write_table(table, str(fake_data_dir / "fin" / "parsed" / "gpcw20251231.parquet"))

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.finance("sh600000", report_date="2025-12-31", ratio_only=True)

    assert "code" in df.columns
    assert "report_date" in df.columns
    assert "净资产收益率" in df.columns    # kept (率)
    assert "资产负债率" in df.columns      # kept (率)
    assert "current_ratio" in df.columns   # kept (ratio)
    assert "pe_ratio" in df.columns       # kept (ratio)
    assert "资产总计" not in df.columns    # filtered out
    assert "负债合计" not in df.columns    # filtered out
    assert "净利润" not in df.columns      # filtered out
