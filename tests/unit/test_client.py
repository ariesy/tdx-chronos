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
    """建 sh/sh600000.parquet 含 sh600000 三行 → 读必须返回"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    (fake_data_dir / "parquet_compact" / "sh").mkdir(parents=True)
    table = pa.table({
        "symbol": ["sh600000", "sh600000", "sh600000"],
        "date": [20240102, 20240103, 20240104],
        "open": [10.0, 10.5, 11.0],
        "high": [10.5, 11.0, 11.5],
        "low": [9.8, 10.3, 10.8],
        "close": [10.3, 10.8, 11.2],
        "volume": [1000, 2000, 3000],
        "amount": [10250.0, 21600.0, 33780.0],
        "market": ["sh"] * 3,
    })
    pq.write_table(table, str(fake_data_dir / "parquet_compact" / "sh" / "sh600000.parquet"))

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.kline("sh600000")
    assert len(df) == 3
    assert set(df.columns) == {"date", "open", "high", "low", "close", "volume", "amount", "market"}


def test_kline_with_date_range(fake_data_dir):
    """start='2024-01-02' end='2024-01-03' → 2 行"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    (fake_data_dir / "parquet_compact" / "sh").mkdir(parents=True)
    table = pa.table({
        "symbol": ["sh600000"] * 5,
        "date": [20240101, 20240102, 20240103, 20240104, 20240105],
        "open": [10.0, 10.5, 11.0, 11.5, 12.0],
        "high": [10.5, 11.0, 11.5, 12.0, 12.5],
        "low": [9.8, 10.3, 10.8, 11.3, 11.8],
        "close": [10.3, 10.8, 11.2, 11.7, 12.2],
        "volume": [1000, 2000, 3000, 4000, 5000],
        "amount": [10250.0, 21600.0, 33780.0, 47160.0, 61600.0],
        "market": ["sh"] * 5,
    })
    pq.write_table(table, str(fake_data_dir / "parquet_compact" / "sh" / "sh600000.parquet"))

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
    (fake_data_dir / "parquet_compact" / "sh").mkdir(parents=True)
    market_file = fake_data_dir / "parquet_compact" / "sh" / "sh600000.parquet"
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
    (fake_data_dir / "parquet_compact" / "sh").mkdir(parents=True)
    table = pa.table({
        "symbol": ["sh600000", "sh600000"],
        "date": [20240102, 20240103],
        "open": [10.0, 10.5],
        "high": [10.5, 11.0],
        "low": [9.8, 10.3],
        "close": [10.3, 10.8],
        "volume": [1000, 2000],
        "amount": [10250.0, 21600.0],
        "market": ["sh", "sh"],
    })
    pq.write_table(table, str(fake_data_dir / "parquet_compact" / "sh" / "sh600000.parquet"))

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
        "code": ["600000"],
        "type": [1],
        "date": [20250630],
        "value_1": [1000],
        "value_2": [2000],
        "market": ["sh"],
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
        "symbol": ["sh000001", "sh000001", "sh000001"],
        "date": [20240101, 20240102, 20240103],
        "open": [3000.0, 3010.0, 3020.0],
        "high": [3010.0, 3020.0, 3030.0],
        "low": [2990.0, 3000.0, 3010.0],
        "close": [3005.0, 3015.0, 3025.0],
        "volume": [100, 200, 300],
        "market": ["sh"] * 3,
        "amount": [1000.0, 2000.0, 3000.0],
        "vol": [10, 20, 30],
        "reserved": [0, 0, 0],
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
        "symbol": ["sh000001"] * 5,
        "date": [20240101, 20240102, 20240103, 20240104, 20240105],
        "open": [3000.0, 3010.0, 3020.0, 3030.0, 3040.0],
        "high": [3010.0, 3020.0, 3030.0, 3040.0, 3050.0],
        "low": [2990.0, 3000.0, 3010.0, 3020.0, 3030.0],
        "close": [3005.0, 3015.0, 3025.0, 3035.0, 3045.0],
        "volume": [100, 200, 300, 400, 500],
        "market": ["sh"] * 5,
        "amount": [1000.0, 2000.0, 3000.0, 4000.0, 5000.0],
        "vol": [10, 20, 30, 40, 50],
        "reserved": [0] * 5,
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


# ─── Sprint 12 T1 · _normalize_symbol 92→bj ────────────────────────


def test_normalize_92xx_to_bj_market():
    """92 开头两位 → bj (北交所新股, 实际数据验证 bj920001~bj920005 存在)"""
    from tdx_chronos.client import _normalize_symbol
    assert _normalize_symbol("920001") == "bj920001"
    assert _normalize_symbol("920123") == "bj920123"


def test_normalize_9_b_share_unchanged():
    """9 开头 (非 92) → sh (B 股回归测试, 不能被 T1 改坏)"""
    from tdx_chronos.client import _normalize_symbol
    assert _normalize_symbol("900901") == "sh900901"
    assert _normalize_symbol("900902") == "sh900902"


def test_normalize_other_prefixes_unchanged():
    """5/6/0/2/3/4/8 前缀回归"""
    from tdx_chronos.client import _normalize_symbol
    assert _normalize_symbol("600000") == "sh600000"  # 6 → sh
    assert _normalize_symbol("500001") == "sh500001"  # 5 → sh
    assert _normalize_symbol("000001") == "sz000001"  # 0 → sz
    assert _normalize_symbol("300750") == "sz300750"  # 3 → sz (创业板)
    assert _normalize_symbol("430017") == "bj430017"  # 4 → bj
    assert _normalize_symbol("830017") == "bj830017"  # 8 → bj


def test_normalize_already_prefixed_passthrough():
    """已带前缀的 passthrough (大小写不敏感)"""
    from tdx_chronos.client import _normalize_symbol
    assert _normalize_symbol("bj920001") == "bj920001"
    assert _normalize_symbol("BJ920001") == "bj920001"
    assert _normalize_symbol("Sh600000") == "sh600000"
# ─── Sprint 12 T2 · list_quarters DESC + 过滤 gpcw0 ───────────────


def test_list_quarters_returns_desc_order(populated_data_dir, monkeypatch):
    """list_quarters 必须按日期 DESC 返回 (newest first)"""
    from tdx_chronos.client import TdxChronos

    import pyarrow as pa
    import pyarrow.parquet as pq
    fin_dir = populated_data_dir / "fin" / "parsed"
    for stem in ("gpcw20201231.parquet", "gpcw20251231.parquet", "gpcw20240630.parquet"):
        pq.write_table(pa.table({"code": [], "x": []}), fin_dir / stem)

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    try:
        quarters = tdx.list_quarters()
        assert quarters == ["2025-12-31", "2024-06-30", "2020-12-31"], \
            f"want DESC, got {quarters}"
    finally:
        tdx.close()

def test_list_quarters_skips_invalid_stem(populated_data_dir):
    """gpcw0.parquet / gpcw999.parquet 等非 8 位日期 stem 必须跳过"""
    from tdx_chronos.client import TdxChronos
    import pyarrow as pa
    import pyarrow.parquet as pq

    fin_dir = populated_data_dir / "fin" / "parsed"
    pq.write_table(pa.table({"code": [], "x": []}), fin_dir / "gpcw20251231.parquet")
    pq.write_table(pa.table({"code": [], "x": []}), fin_dir / "gpcw0.parquet")
    pq.write_table(pa.table({"code": [], "x": []}), fin_dir / "gpcw999.parquet")

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    try:
        quarters = tdx.list_quarters()
        assert quarters == ["2025-12-31"], f"want only valid, got {quarters}"
    finally:
        tdx.close()


def test_list_quarters_strict_8_digit_date(populated_data_dir):
    """stem 必须严格 8 位数字 (gpcw2025123.parquet 7 位应跳过)"""
    from tdx_chronos.client import TdxChronos
    import pyarrow as pa
    import pyarrow.parquet as pq

    fin_dir = populated_data_dir / "fin" / "parsed"
    pq.write_table(pa.table({"code": [], "x": []}), fin_dir / "gpcw20251231.parquet")
    pq.write_table(pa.table({"code": [], "x": []}), fin_dir / "gpcw2025123.parquet")

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    try:
        quarters = tdx.list_quarters()
        assert quarters == ["2025-12-31"], f"want strict 8-digit filter, got {quarters}"
    finally:
        tdx.close()


# ─── Sprint 12 T3 · close() 资源释放 ──────────────────────────────


def test_close_releases_db_when_readonly_false(populated_data_dir):
    """readonly=False 路径 close() 必须释放 db 连接 (P0 修复)"""
    from tdx_chronos.client import TdxChronos

    # Pre-populate so lazy db opens
    from tdx_chronos.meta.db import MetaDB
    db = MetaDB(str(populated_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")
    db.close()

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)

    # Force lazy db open via symbol_info
    info = tdx.symbol_info("sh600000")
    assert info["symbol"] == "sh600000"
    assert tdx._db is not None  # db 已开

    # Close (no chmod attempted in readonly=False path)
    tdx.close()

    # Critical: db must be released
    assert tdx._db is None, "readonly=False path leaked db connection"


def test_close_releases_db_when_readonly_true(populated_data_dir):
    """readonly=True 路径 close() 仍释放 db (回归)"""
    from tdx_chronos.client import TdxChronos

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=True)
    info = tdx.symbol_info("sh600000")
    assert tdx._db is not None

    tdx.close()
    assert tdx._db is None, "readonly=True path leaked db connection"


# ─── Sprint 12 T4 · index_klines drop symbol ───────────────────────


def test_index_klines_drops_symbol_column(fake_data_dir):
    """index_klines 返回 df 不应含 symbol 列 (与 kline 一致)"""
    from tdx_chronos.client import TdxChronos
    import pyarrow as pa
    import pyarrow.parquet as pq

    idx_path = fake_data_dir / "index" / "indices.parquet"
    pq.write_table(
        pa.table({
            "date": [20240102, 20240103],
            "open": [10.0, 10.1],
            "high": [10.5, 10.6],
            "low": [9.8, 9.9],
            "close": [10.2, 10.4],
            "amount": [1e8, 1.1e8],
            "vol": [1e7, 1.1e7],
            "reserved": [0, 0],
            "symbol": ["sh000001", "sh000001"],
            "market": ["sh", "sh"],
            "source_zip": ["shzsday.zip", "shzsday.zip"],
            "ingested_at": ["2024-01-02T00:00:00", "2024-01-03T00:00:00"],
            "code": ["000001", "000001"],
            "ds_code": ["sh000001", "sh000001"],
            "name": ["上证指数", "上证指数"],
        }),
        idx_path,
    )

    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    try:
        df = tdx.index_klines("sh000001", start="2024-01-01", end="2024-12-31")
        assert "symbol" not in df.columns, f"symbol should be dropped, got: {list(df.columns)}"
        # 元信息列保留
        assert "market" in df.columns
        assert "code" in df.columns
        assert "ds_code" in df.columns
        assert "name" in df.columns
    finally:
        tdx.close()


def test_index_klines_preserves_metadata_columns(fake_data_dir):
    """index_klines 保留 market/code/ds_code/name 元信息列 (P1 决策)"""
    from tdx_chronos.client import TdxChronos
    import pyarrow as pa
    import pyarrow.parquet as pq

    idx_path = fake_data_dir / "index" / "indices.parquet"
    pq.write_table(
        pa.table({
            "date": [20240102],
            "open": [10.0], "high": [10.5], "low": [9.8], "close": [10.2],
            "amount": [1e8], "vol": [1e7], "reserved": [0],
            "symbol": ["sh000001"], "market": ["sh"],
            "source_zip": ["shzsday.zip"], "ingested_at": ["2024-01-02"],
            "code": ["000001"], "ds_code": ["sh000001"], "name": ["上证指数"],
        }),
        idx_path,
    )

    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    try:
        df = tdx.index_klines("sh000001", start="2024-01-01")
        assert "code" in df.columns
        assert "ds_code" in df.columns
        assert "name" in df.columns
        assert "market" in df.columns
    finally:
        tdx.close()


# ─── Sprint 12 T5b · client 调 MetaDB public API ─────────────────


def test_client_symbol_info_uses_meta_db_public_api(monkeypatch, populated_data_dir):
    """TdxChronos.symbol_info 必须调 MetaDB.get_symbol, 不调 _connect"""
    from tdx_chronos.client import TdxChronos
    from tdx_chronos.meta import db as db_mod

    # Pre-populate
    from tdx_chronos.meta.db import MetaDB
    db = MetaDB(str(populated_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")
    db.close()

    # Spy on MetaDB.get_symbol
    call_count = {"n": 0}
    original = MetaDB.get_symbol
    def spy(self, symbol):
        call_count["n"] += 1
        return original(self, symbol)
    monkeypatch.setattr(MetaDB, "get_symbol", spy)

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    try:
        info = tdx.symbol_info("sh600000")
        assert info["symbol"] == "sh600000"
        assert call_count["n"] >= 1, "MetaDB.get_symbol was not called"
    finally:
        tdx.close()


def test_client_list_symbols_uses_meta_db_public_api(monkeypatch, populated_data_dir):
    """TdxChronos.list_symbols 必须调 MetaDB.list_symbols"""
    from tdx_chronos.client import TdxChronos
    from tdx_chronos.meta.db import MetaDB

    # Pre-populate
    db = MetaDB(str(populated_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")
    db.record_symbol("sz000001", "sz", 19910403, 8000, "hsjday.zip")
    db.close()

    # Spy on MetaDB.list_symbols
    call_count = {"n": 0}
    original = MetaDB.list_symbols
    def spy(self, market=None):
        call_count["n"] += 1
        return original(self, market)
    monkeypatch.setattr(MetaDB, "list_symbols", spy)

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    try:
        syms = tdx.list_symbols()
        assert "sh600000" in syms
        assert "sz000001" in syms
        assert call_count["n"] >= 1, "MetaDB.list_symbols was not called"

        syms_sh = tdx.list_symbols("sh")
        assert syms_sh == ["sh600000"]
    finally:
        tdx.close()


def test_client_symbol_info_unchanged_behavior(populated_data_dir):
    """symbol_info 行为回归: 找/不找/大小写"""
    from tdx_chronos.client import TdxChronos
    from tdx_chronos.meta.db import MetaDB

    db = MetaDB(str(populated_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")
    db.close()

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    try:
        # 找到
        info = tdx.symbol_info("sh600000")
        assert info["symbol"] == "sh600000"
        # 大小写
        info2 = tdx.symbol_info("SH600000")
        assert info2["symbol"] == "sh600000"
        # 找不到返回 {} (不 raise)
        info3 = tdx.symbol_info("sh999999")
        assert info3 == {}
    finally:
        tdx.close()


def test_client_list_symbols_unchanged_behavior(populated_data_dir):
    """list_symbols 行为回归: 全列/过滤/排序"""
    from tdx_chronos.client import TdxChronos
    from tdx_chronos.meta.db import MetaDB

    db = MetaDB(str(populated_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")
    db.record_symbol("sz000001", "sz", 19910403, 8000, "hsjday.zip")
    db.close()

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    try:
        # 全部 sorted ASC
        syms = tdx.list_symbols()
        assert syms == ["sh600000", "sz000001"]
        # 过滤
        sh = tdx.list_symbols("sh")
        assert sh == ["sh600000"]
    finally:
        tdx.close()


# ─── Sprint 11 T4 · shareholders_history ─────────────────────────────────────


def test_shareholders_history_unknown_symbol_returns_empty(fake_data_dir):
    """unknown symbol → empty DataFrame"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.table({
        "code": ["600000"], "type": [1], "date": [20250630],
        "value_1": [1000], "value_2": [2000], "market": ["sh"],
    })
    pq.write_table(table, str(fake_data_dir / "gp" / "records.parquet"))

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    try:
        # sh999999 不在 fixture → 应返回 empty DataFrame
        df = tdx.shareholders_history("sh999999")
        assert df.empty
    finally:
        tdx.close()


def test_shareholders_history_types_filter(fake_data_dir):
    """types=[1,2,3,4] → df['type'].unique() ⊆ {1,2,3,4}"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.table({
        "code":    ["600000"] * 5,
        "type":    [1, 2, 3, 4, 5],
        "date":    [20250101, 20250201, 20250301, 20250401, 20250501],
        "value_1": [100, 200, 300, 400, 500],
        "value_2": [100, 200, 300, 400, 500],
        "market":  ["sh"] * 5,
    })
    pq.write_table(table, str(fake_data_dir / "gp" / "records.parquet"))

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    try:
        df = tdx.shareholders_history("sh600000", types=[1, 2, 3, 4])
        assert len(df) == 4
        assert set(df["type"].unique()).issubset({1, 2, 3, 4})
        assert 5 not in df["type"].values
    finally:
        tdx.close()


def test_shareholders_history_since_date_filter(fake_data_dir):
    """since_date='2024-01-01' → df['date'].min() >= 20240101"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.table({
        "code":    ["600000"] * 4,
        "type":    [1, 1, 1, 1],
        "date":    [20230101, 20240101, 20240630, 20250101],
        "value_1": [100, 200, 300, 400],
        "value_2": [100, 200, 300, 400],
        "market":  ["sh"] * 4,
    })
    pq.write_table(table, str(fake_data_dir / "gp" / "records.parquet"))

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    try:
        df = tdx.shareholders_history("sh600000", since_date="2024-01-01")
        assert df["date"].min() >= 20240101
        assert 20230101 not in df["date"].values
    finally:
        tdx.close()


def test_shareholders_history_limit(fake_data_dir):
    """limit=2 → len(df) <= 2 (sorted by date DESC)"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.table({
        "code":    ["600000"] * 5,
        "type":    [1, 1, 1, 1, 1],
        "date":    [20250101, 20250201, 20250301, 20250401, 20250501],
        "value_1": [100, 200, 300, 400, 500],
        "value_2": [100, 200, 300, 400, 500],
        "market":  ["sh"] * 5,
    })
    pq.write_table(table, str(fake_data_dir / "gp" / "records.parquet"))

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    try:
        df = tdx.shareholders_history("sh600000", limit=2)
        assert len(df) == 2
        # sorted by date DESC
        assert list(df["date"]) == [20250501, 20250401]
    finally:
        tdx.close()


def test_shareholders_history_combined(fake_data_dir):
    """types=[1,4] + since_date='2024-01-01' + limit=3 → 全部条件满足"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    # 制造: type 1,2,3,4 各多条, 覆盖 2023/2024 日期
    rows = []
    for t in [1, 2, 3, 4]:
        for d in [20230101, 20240101, 20240630, 20250101]:
            rows.append({"code": "600000", "type": t, "date": d,
                         "value_1": 100, "value_2": 100, "market": "sh"})
    table = pa.table({
        "code":    [r["code"] for r in rows],
        "type":    [r["type"] for r in rows],
        "date":    [r["date"] for r in rows],
        "value_1": [r["value_1"] for r in rows],
        "value_2": [r["value_2"] for r in rows],
        "market":  [r["market"] for r in rows],
    })
    pq.write_table(table, str(fake_data_dir / "gp" / "records.parquet"))

    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    try:
        df = tdx.shareholders_history(
            "sh600000", types=[1, 4], since_date="2024-01-01", limit=3,
        )
        assert len(df) == 3
        # types only 1 or 4
        assert set(df["type"].unique()).issubset({1, 4})
        # dates >= 20240101
        assert df["date"].min() >= 20240101
        # sorted by date DESC
        assert list(df["date"]) == sorted(df["date"].tolist(), reverse=True)
    finally:
        tdx.close()


def test_tdx_chronos_exported_from_top_level():
    """Sprint 11 T6 fix: TdxChronos 必须在 tdx_chronos package 顶层可 import"""
    from tdx_chronos import TdxChronos as TopLevel
    from tdx_chronos.client import TdxChronos as FromClient
    assert TopLevel is FromClient, "Top-level TdxChronos 应与 tdx_chronos.client.TdxChronos 是同一 class"


# ─── Sprint 13 · ETF 显式化 (list_etfs + _is_fund_or_bond) ──────────────────


def test_is_fund_or_bond_classification():
    """_is_fund_or_bond 代码段判定: 含 ETF/LOF/REITs/可转债, 排除 A 股/指数"""
    from tdx_chronos.client import _is_fund_or_bond

    # 沪市基金
    assert _is_fund_or_bond("sh500001") is True   # 老封闭式基金
    assert _is_fund_or_bond("sh510050") is True   # 50ETF
    assert _is_fund_or_bond("sh510300") is True   # 沪深300ETF
    assert _is_fund_or_bond("sh511010") is True   # 国债ETF
    assert _is_fund_or_bond("sh512760") is True   # 芯片ETF
    assert _is_fund_or_bond("sh513500") is True   # 标普500ETF
    assert _is_fund_or_bond("sh588200") is True   # 科创50ETF
    assert _is_fund_or_bond("sh560500") is True   # LOF
    # 沪市可转债
    assert _is_fund_or_bond("sh110001") is True   # 可转债
    assert _is_fund_or_bond("sh113001") is True   # 可转债
    # 深市 ETF
    assert _is_fund_or_bond("sz159915") is True   # 创业板ETF
    assert _is_fund_or_bond("sz159949") is True   # 创业板50ETF
    # 深市 LOF + REITs
    assert _is_fund_or_bond("sz160105") is True   # LOF
    assert _is_fund_or_bond("sz180101") is True   # 公募REITs
    # 深市可转债
    assert _is_fund_or_bond("sz123001") is True   # 可转债
    assert _is_fund_or_bond("sz127001") is True   # 可转债
    assert _is_fund_or_bond("sz128001") is True   # 可转债

    # 不属于场内基金/可转债: A 股 + B 股 + 指数 + 北交所
    assert _is_fund_or_bond("sh600519") is False  # 贵州茅台 (A股)
    assert _is_fund_or_bond("sh600036") is False  # 招商银行 (A股)
    assert _is_fund_or_bond("sz000001") is False  # 平安银行 (A股)
    assert _is_fund_or_bond("sz300750") is False  # 宁德时代 (创业板)
    assert _is_fund_or_bond("sh688981") is False  # 中芯国际 (科创板)
    assert _is_fund_or_bond("bj838000") is False  # 北交所
    assert _is_fund_or_bond("bj920001") is False  # 北交所新股
    assert _is_fund_or_bond("sh000001") is False  # 上证指数
    assert _is_fund_or_bond("sh900901") is False  # B 股


def test_list_etfs_all(populated_data_dir):
    """list_etfs() 默认 = 全部场内基金/可转债 (含 sh5 + sh1 + sz1)"""
    from tdx_chronos.client import TdxChronos
    from tdx_chronos.meta.db import MetaDB

    db = MetaDB(str(populated_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")     # A 股
    db.record_symbol("sh510050", "sh", 20050223, 5000, "hsjday.zip")     # 50ETF
    db.record_symbol("sh510300", "sh", 20120528, 3000, "hsjday.zip")     # 沪深300ETF
    db.record_symbol("sh588200", "sh", 20221026, 800, "hsjday.zip")      # 科创50ETF
    db.record_symbol("sh110001", "sh", 20100115, 2000, "hsjday.zip")     # 沪可转债
    db.record_symbol("sz000001", "sz", 19910403, 8000, "hsjday.zip")     # A 股
    db.record_symbol("sz159915", "sz", 20111209, 3500, "hsjday.zip")     # 创业板ETF
    db.record_symbol("sz160105", "sz", 20100115, 2000, "hsjday.zip")     # LOF
    db.record_symbol("sz180101", "sz", 20210607, 500, "hsjday.zip")      # REITs
    db.record_symbol("sz123001", "sz", 20100115, 2000, "hsjday.zip")     # 深可转债
    db.record_symbol("bj838000", "bj", 20200101, 1000, "hsjday.zip")     # 北交所
    db.close()

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    try:
        etfs = tdx.list_etfs()
        # 6 只场内基金/可转债 (排除 sh600000/sz000001/bj838000)
        assert "sh510050" in etfs
        assert "sh510300" in etfs
        assert "sh588200" in etfs
        assert "sh110001" in etfs
        assert "sz159915" in etfs
        assert "sz160105" in etfs
        assert "sz180101" in etfs
        assert "sz123001" in etfs
        # A 股/北交所不在
        assert "sh600000" not in etfs
        assert "sz000001" not in etfs
        assert "bj838000" not in etfs
        # sorted ASC
        assert etfs == sorted(etfs)
        assert len(etfs) == 8
    finally:
        tdx.close()


def test_list_etfs_by_market_sh(populated_data_dir):
    """list_etfs(market='sh') 仅返回沪市场内基金/可转债"""
    from tdx_chronos.client import TdxChronos
    from tdx_chronos.meta.db import MetaDB

    db = MetaDB(str(populated_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh510050", "sh", 20050223, 5000, "hsjday.zip")
    db.record_symbol("sh110001", "sh", 20100115, 2000, "hsjday.zip")
    db.record_symbol("sz159915", "sz", 20111209, 3500, "hsjday.zip")
    db.record_symbol("sz123001", "sz", 20100115, 2000, "hsjday.zip")
    db.close()

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    try:
        sh_etfs = tdx.list_etfs(market="sh")
        assert sh_etfs == ["sh110001", "sh510050"]  # sorted ASC
        assert all(s.startswith("sh") for s in sh_etfs)
    finally:
        tdx.close()


def test_list_etfs_by_market_sz(populated_data_dir):
    """list_etfs(market='sz') 仅返回深市 ETF/LOF/REITs/可转债"""
    from tdx_chronos.client import TdxChronos
    from tdx_chronos.meta.db import MetaDB

    db = MetaDB(str(populated_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh510050", "sh", 20050223, 5000, "hsjday.zip")
    db.record_symbol("sz159915", "sz", 20111209, 3500, "hsjday.zip")
    db.record_symbol("sz180101", "sz", 20210607, 500, "hsjday.zip")
    db.record_symbol("sz123001", "sz", 20100115, 2000, "hsjday.zip")
    db.close()

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    try:
        sz_etfs = tdx.list_etfs(market="sz")
        assert sz_etfs == ["sz123001", "sz159915", "sz180101"]  # sorted ASC
        assert all(s.startswith("sz") for s in sz_etfs)
    finally:
        tdx.close()


def test_list_etfs_empty_when_no_funds(populated_data_dir):
    """全是 A 股 → list_etfs 返回空 list"""
    from tdx_chronos.client import TdxChronos
    from tdx_chronos.meta.db import MetaDB

    db = MetaDB(str(populated_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")
    db.record_symbol("sz000001", "sz", 19910403, 8000, "hsjday.zip")
    db.close()

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    try:
        assert tdx.list_etfs() == []
        assert tdx.list_etfs(market="sh") == []
        assert tdx.list_etfs(market="sz") == []
    finally:
        tdx.close()


def test_list_etfs_excludes_bj(populated_data_dir):
    """list_etfs() 排除 bj 市场 (北交所无场内基金)"""
    from tdx_chronos.client import TdxChronos
    from tdx_chronos.meta.db import MetaDB

    db = MetaDB(str(populated_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh510050", "sh", 20050223, 5000, "hsjday.zip")
    db.record_symbol("bj838000", "bj", 20200101, 1000, "hsjday.zip")
    db.close()

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    try:
        etfs = tdx.list_etfs()
        assert "sh510050" in etfs
        assert "bj838000" not in etfs
        # list_etfs(market='bj') 显式也是空
        assert tdx.list_etfs(market="bj") == []
    finally:
        tdx.close()
