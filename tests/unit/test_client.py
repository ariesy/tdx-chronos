"""Phase 1 TDD · TdxChronos facade scaffolding"""
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

def test_symbol_info_returns_dict(fake_data_dir):
    """先 init 一个临时 meta.db + 一行 symbol_metadata"""
    from tdx_chronos.meta.db import MetaDB
    db = MetaDB(str(fake_data_dir / "meta" / "meta.db"))
    db.init_schema()
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip", "/tmp/a.parquet")
    db.close()

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    info = tdx.symbol_info("sh600000")
    assert info["symbol"] == "sh600000"
    assert info["market"] == "sh"


def test_symbol_info_unknown_returns_empty(fake_data_dir):
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    assert tdx.symbol_info("sh999999") == {}


def test_list_symbols_all(fake_data_dir):
    from tdx_chronos.meta.db import MetaDB
    db = MetaDB(str(fake_data_dir / "meta" / "meta.db"))
    db.init_schema()
    db.record_symbol("sh600000", "sh", 19991110, 1, "x", "y")
    db.record_symbol("sz000001", "sz", 19910403, 1, "x", "y")
    db.record_symbol("bj838000", "bj", 20200101, 1, "x", "y")
    db.close()
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    syms = tdx.list_symbols()
    assert set(syms) == {"sh600000", "sz000001", "bj838000"}


def test_list_symbols_by_market(fake_data_dir):
    """取仅 sh"""
    from tdx_chronos.meta.db import MetaDB
    db = MetaDB(str(fake_data_dir / "meta" / "meta.db"))
    db.init_schema()
    db.record_symbol("sh600000", "sh", 19991110, 1, "x", "y")
    db.record_symbol("sz000001", "sz", 19910403, 1, "x", "y")
    db.record_symbol("bj838000", "bj", 20200101, 1, "x", "y")
    db.close()
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
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


def test_kline_unknown_symbol_returns_empty(fake_data_dir):
    """sh999999 不存在 → 不 raise, 返回空 DataFrame"""
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.kline("sh999999")
    assert df.empty
