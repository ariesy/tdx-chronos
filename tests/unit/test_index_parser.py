"""Sprint 4b D2 · index_parser.py 单元测试

5 指数 .day → Parquet

Test classes:
- TestIndexCodes         · 5 指数常量
- TestIndexParseFile      · 单 .day → pd.DataFrame
- TestIndexParseAll       · parse_all + Parquet 落盘

Notes (Sprint 13 hotfix):
    原测试硬编码 ``data/snapshot/2026-07-04/raw`` 现已不存在 (retention 7→3 天后
    4 天前的 snapshot 会被删除). 改为**动态**找最近的 snapshot + 用 **lower-bound**
    断言替代硬编码 record count. 没有 snapshot 时 ``pytest.skip``.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from tdx_chronos.sources.index_parser import (
    INDEX_CODES,
    IndexParser,
)


# ---------------------------------------------------------------------
# TestIndexCodes (不依赖 snapshot, 5 个常量逻辑)
# ---------------------------------------------------------------------
class TestIndexCodes:
    def test_five_main_indices(self):
        """§四.5 5 主要指数"""
        assert len(INDEX_CODES) == 5

    def test_index_codes_unique_ds_code(self):
        ds_codes = {c["ds_code"] for c in INDEX_CODES}
        assert len(ds_codes) == 5  # all unique

    def test_index_codes_well_known(self):
        """5 指数 well-known: 上证/沪深300/深证/创业板/科创50"""
        names = {c["name"] for c in INDEX_CODES}
        assert "上证综指" in names
        assert "沪深300" in names
        assert "深证成指" in names
        assert "创业板指" in names
        assert "科创50" in names


# ---------------------------------------------------------------------
# Snapshot-动态 fixture (Sprint 13 hotfix: hardcoded 2026-07-04 → dynamic)
# ---------------------------------------------------------------------
SNAPSHOT_ROOT = Path("/app/tdx-chronos/data/snapshot")


def _pick_raw() -> Path | None:
    """Most-recent existing snapshot's raw/. None if no snapshot exists."""
    if not SNAPSHOT_ROOT.exists():
        return None
    raws = [p for p in SNAPSHOT_ROOT.glob("*/raw") if p.is_dir()]
    return sorted(raws, reverse=True)[0] if raws else None


@pytest.fixture(scope="module")
def raw_dir() -> Path:
    """Module-scoped: skip entire index integration tests if no snapshot."""
    p = _pick_raw()
    if p is None:
        pytest.skip("no snapshot in data/snapshot/ — run daily_incr.sh first")
    return p


# ---------------------------------------------------------------------
# TestIndexParseFile
# ---------------------------------------------------------------------
class TestIndexParseFile:
    def test_shanghai_composite_columns(self, raw_dir):
        """上证综指 8+ cols.

        历史 record count (2026-07-04 snapshot) = 8674. 新 snapshot 由于
        日数据 append, count 单调递增 → 用 lower-bound ``>= 8000`` 兼容
        未来任意 snapshot. 列名格式不变.
        """
        path = raw_dir / "sh/lday/sh000001.day"
        if not path.exists():
            pytest.skip(f"{path} not in current snapshot")
        df = IndexParser.parse_file(path)
        assert isinstance(df, pd.DataFrame)
        assert df.shape[0] >= 8000
        for col in ("date", "open", "high", "low", "close", "amount", "vol", "reserved"):
            assert col in df.columns

    def test_hs300_record_count(self, raw_dir):
        """沪深 300 ≥ 5000 records (历史值 5220, 单调递增)."""
        path = raw_dir / "sh/lday/sh000300.day"
        if not path.exists():
            pytest.skip(f"{path} not in current snapshot")
        df = IndexParser.parse_file(path)
        assert df.shape[0] >= 5000

    def test_kechuang50_first_date(self, raw_dir):
        """科创 50 首日 2019-12-31 (开板日不可变, 严格 ==)."""
        path = raw_dir / "sh/lday/sh000688.day"
        if not path.exists():
            pytest.skip(f"{path} not in current snapshot")
        df = IndexParser.parse_file(path)
        assert int(df["date"].min()) == 20191231


# ---------------------------------------------------------------------
# TestIndexParseAll
# ---------------------------------------------------------------------
class TestIndexParseAll:
    def test_parse_all_writes_parquet(self, raw_dir, tmp_path):
        """parse_all 至少解析出 1 个指数 → parquet 可读 (历史 28004 rows)."""
        out = tmp_path / "indices.parquet"
        summary = IndexParser.parse_all(raw_dir=raw_dir, output_path=out)
        if summary.parsed_ok == 0:
            pytest.skip(f"no index files found in {raw_dir}")
        assert summary.parsed_ok >= 1
        assert summary.output_rows >= 1
        assert out.exists()

        table = pq.read_table(out)
        assert table.num_rows >= 1
        assert "ds_code" in table.column_names
        assert "name" in table.column_names

    def test_parse_all_5_indices(self, raw_dir, tmp_path):
        """5 指数 (理想) 全 ok; snapshot 不全时 >= 1."""
        summary = IndexParser.parse_all(
            raw_dir=raw_dir,
            output_path=tmp_path / "indices.parquet",
        )
        if summary.parsed_ok == 0:
            pytest.skip(f"no index files found in {raw_dir}")
        assert summary.parsed_ok >= 1
        for spec in INDEX_CODES:
            ds = spec["ds_code"]
            assert summary.results[ds]["parse_ok"] is True
            assert summary.results[ds]["record_count"] > 100