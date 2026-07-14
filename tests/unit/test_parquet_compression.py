"""Sprint 4a D3 · parquet_compression.py 单元测试

Test classes:
- TestParquetOptimizerInit  · strategy + compression_level validation
- TestStrategyZstdOnly      · 1 file 1 Parquet · 仅换 zstd
- TestStrategyMerge         · 1-market-1-Parquet + zstd (主路径)
- TestOptimizationSummary   · Summary 字段 + 压缩比
- TestRealRunMerge          · 真 12,256 文件 跑 merge 策略 (小型 fixture)
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from tdx_chronos.optimization.parquet_compression import (
    MARKETS,
    OptimizationSummary,
    ParquetOptimizer,
    STRATEGY_MERGE,
    STRATEGY_MERGE_MAX,
    STRATEGY_ZSTD_ONLY,
    VALID_STRATEGIES,
)


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------
@pytest.fixture
def tiny_parquet_dir(tmp_path):
    """复用 tests/fixtures/parquet_input (3+3+1 files · 50 rows each)"""
    src = Path("tests/fixtures/parquet_input")
    dst = tmp_path / "input"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return dst


@pytest.fixture
def real_parquet_dir():
    """真实 12,256 Parquet (Sprint 2 末产物)"""
    return Path("/app/tdx-chronos/data/parquet_compact")


# ---------------------------------------------------------------------
# TestParquetOptimizerInit
# ---------------------------------------------------------------------
class TestParquetOptimizerInit:
    def test_default_strategy_is_merge(self):
        """默认 merge (Sprint 4a D3 决策)"""
        opt = ParquetOptimizer()
        assert opt.strategy == STRATEGY_MERGE
        assert opt.compression_level == 3

    def test_valid_strategies_constant(self):
        assert STRATEGY_ZSTD_ONLY in VALID_STRATEGIES
        assert STRATEGY_MERGE in VALID_STRATEGIES
        assert STRATEGY_MERGE_MAX in VALID_STRATEGIES

    def test_invalid_strategy_raises(self):
        with pytest.raises(ValueError, match="invalid strategy"):
            ParquetOptimizer(strategy="invalid")

    def test_invalid_compression_level_raises(self):
        with pytest.raises(ValueError, match="invalid compression_level"):
            ParquetOptimizer(compression_level=0)
        with pytest.raises(ValueError, match="invalid compression_level"):
            ParquetOptimizer(compression_level=23)


# ---------------------------------------------------------------------
# TestStrategyZstdOnly
# ---------------------------------------------------------------------
class TestStrategyZstdOnly:
    def test_zstd_only_keeps_per_file_structure(self, tiny_parquet_dir, tmp_path):
        """1 file 1 Parquet · 文件数不变"""
        out = tmp_path / "out"
        opt = ParquetOptimizer(strategy=STRATEGY_ZSTD_ONLY, compression_level=3)
        summary = opt.run(tiny_parquet_dir, out)

        # 3 markets · 7 files
        assert summary.markets["sh"].input_files == 3
        assert summary.markets["sz"].input_files == 3
        assert summary.markets["bj"].input_files == 1

        # 实际文件数仍 7 (per-file)
        for market, count in [("sh", 3), ("sz", 3), ("bj", 1)]:
            files = list((out / market).glob("*.parquet"))
            assert len(files) == count, f"{market}: {len(files)} != {count}"

    def test_zstd_only_uses_zstd_codec(self, tiny_parquet_dir, tmp_path):
        """输出 Parquet 用 zstd codec"""
        out = tmp_path / "out"
        opt = ParquetOptimizer(strategy=STRATEGY_ZSTD_ONLY, compression_level=3)
        opt.run(tiny_parquet_dir, out)

        # 检 1 个文件 (fixture 文件名是 shtest0.parquet)
        out_files = list((out / "sh").glob("*.parquet"))
        assert len(out_files) > 0
        md = pq.read_metadata(out_files[0])
        assert str(md.row_group(0).column(0).compression) == "ZSTD"


# ---------------------------------------------------------------------
# TestStrategyMerge
# ---------------------------------------------------------------------
class TestStrategyMerge:
    def test_merge_creates_one_file_per_market(self, tiny_parquet_dir, tmp_path):
        """1 market 1 Parquet · 3 files total"""
        out = tmp_path / "out"
        opt = ParquetOptimizer(strategy=STRATEGY_MERGE, compression_level=3)
        summary = opt.run(tiny_parquet_dir, out)

        for market in MARKETS:
            out_path = out / market / f"{market}.parquet"
            assert out_path.exists(), f"{market} output missing"
            assert summary.markets[market].output_path == out_path

        # 总文件数 3 (per market)
        total_files = sum(1 for _ in out.rglob("*.parquet"))
        assert total_files == 3

    def test_merge_concatenates_all_rows(self, tiny_parquet_dir, tmp_path):
        """3 sh files × 50 rows = 150 rows in sh.parquet"""
        out = tmp_path / "out"
        opt = ParquetOptimizer(strategy=STRATEGY_MERGE, compression_level=3)
        summary = opt.run(tiny_parquet_dir, out)

        # sh: 3 files × 50 rows = 150
        assert summary.markets["sh"].row_count == 150
        # sz: 3 × 50 = 150
        assert summary.markets["sz"].row_count == 150
        # bj: 1 × 50 = 50
        assert summary.markets["bj"].row_count == 50

    def test_merge_preserves_schema(self, tiny_parquet_dir, tmp_path):
        """schema 完整保留"""
        out = tmp_path / "out"
        opt = ParquetOptimizer(strategy=STRATEGY_MERGE, compression_level=3)
        opt.run(tiny_parquet_dir, out)

        schema = pq.read_schema(out / "sh" / "sh.parquet")
        # 字段名应与原相同
        assert set(schema.names) >= {"date", "open", "high", "low", "close"}

    def test_merge_uses_zstd_codec(self, tiny_parquet_dir, tmp_path):
        """输出 Parquet 用 zstd codec"""
        out = tmp_path / "out"
        opt = ParquetOptimizer(strategy=STRATEGY_MERGE, compression_level=3)
        opt.run(tiny_parquet_dir, out)

        md = pq.read_metadata(out / "sh" / "sh.parquet")
        assert str(md.row_group(0).column(0).compression) == "ZSTD"


# ---------------------------------------------------------------------
# TestOptimizationSummary
# ---------------------------------------------------------------------
class TestOptimizationSummary:
    def test_summary_total_compression_ratio(self, tiny_parquet_dir, tmp_path):
        """总压缩比 = output / input · < 1.0 表示缩小"""
        out = tmp_path / "out"
        opt = ParquetOptimizer(strategy=STRATEGY_MERGE, compression_level=3)
        s = opt.run(tiny_parquet_dir, out)

        # 0 < ratio < 1 (应该缩小)
        assert 0.0 < s.compression_ratio < 1.0

    def test_summary_saved_bytes_positive(self, tiny_parquet_dir, tmp_path):
        """saved_bytes = input - output · > 0"""
        out = tmp_path / "out"
        opt = ParquetOptimizer(strategy=STRATEGY_MERGE, compression_level=3)
        s = opt.run(tiny_parquet_dir, out)

        assert s.saved_bytes > 0
        assert s.saved_percent > 0

    def test_summary_timestamp_utc(self, tiny_parquet_dir, tmp_path):
        """start_at / end_at 都是 UTC"""
        out = tmp_path / "out"
        opt = ParquetOptimizer(strategy=STRATEGY_MERGE, compression_level=3)
        s = opt.run(tiny_parquet_dir, out)

        assert s.start_at.tzinfo is not None
        assert s.end_at.tzinfo is not None
        assert s.total_seconds >= 0


# ---------------------------------------------------------------------
# TestRealRunMerge (真 12,256 文件)
# ---------------------------------------------------------------------
class TestRealRunMerge:
    def test_real_12k_files_merge(self, real_parquet_dir, tmp_path):
        """真 12,256 Parquet · merge 策略 · 验证数据完整"""
        out = tmp_path / "real_out"
        opt = ParquetOptimizer(strategy=STRATEGY_MERGE, compression_level=3)
        summary = opt.run(real_parquet_dir, out)

        # 3 markets
        assert "sh" in summary.markets
        assert "sz" in summary.markets
        assert "bj" in summary.markets

        # sh 5880 + sz 5788 + bj 588 = 12256
        sh = summary.markets["sh"]
        sz = summary.markets["sz"]
        bj = summary.markets["bj"]
        total_files = sh.input_files + sz.input_files + bj.input_files
        assert total_files == 12256

        # 压缩比 30-60% (Sprint 4a D3 预期)
        assert 0.30 < summary.compression_ratio < 0.65, (
            f"compression_ratio={summary.compression_ratio:.2%} not in expected range"
        )

        # 输出 3 files
        for market, result in summary.markets.items():
            assert result.output_path.exists(), f"{market} missing"
            assert result.row_count > 0

    def test_real_merge_saves_over_30_percent(self, real_parquet_dir, tmp_path):
        """节省 > 30% (Sprint 4a D3 决策)"""
        out = tmp_path / "real_out"
        opt = ParquetOptimizer(strategy=STRATEGY_MERGE, compression_level=3)
        summary = opt.run(real_parquet_dir, out)

        # 实际 Sprint 4a D3 验收: 40.6% 节省
        assert summary.saved_percent >= 30, (
            f"saved_percent={summary.saved_percent:.1f}% < 30%"
        )
