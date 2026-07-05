"""Sprint 9 T3 · sample_unknown_fields.py 单元测试 (2 测试)

验证:
- 脚本能跑成功 (单次 read parquet 不爆)
- 输出 CSV 行数 == 182 (col323-400 + col440-500 + col522-560 + _col582-585)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_CSV = ROOT / "data" / "research" / "sprint9_unknown_fields.csv"


class TestSampleUnknownFields:
    """Sprint 9 T3 · colXXX + _colXXX 摸排脚本 (2 测试)"""

    def test_sample_unknown_fields_runs_without_error(self):
        """脚本跑成功 (单次 read parquet, 182 字段全部摸排)"""
        env = {"PYTHONPATH": "src:vendor/_vendor"}
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "sample_unknown_fields.py"),
            ],
            cwd=str(ROOT),
            env={**env, **(__import__("os").environ)},
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, (
            f"脚本应 exit 0 · stderr={result.stderr}\nstdout={result.stdout[-500:]}"
        )
        assert "已输出 182 行" in result.stdout or "✅ 已输出" in result.stdout

    def test_sample_unknown_fields_csv_has_182_rows(self):
        """输出 CSV 行数 == 182 (col323-400=78 + col440-500=61 + col522-560=39 + _col582-585=4)"""
        if not OUTPUT_CSV.exists():
            pytest.skip(f"CSV 不存在 · 请先跑 test_sample_unknown_fields_runs_without_error")
        df = pd.read_csv(OUTPUT_CSV)
        # 182 = 78 + 61 + 39 + 4
        assert len(df) == 182, f"应 182 行 · 实际 {len(df)} 行"

        # 列含 colXXX 三段 + 4 个 _colXXX
        cols = set(df["column_name"])
        col323_400 = sum(1 for c in cols if c.startswith("col") and 323 <= int(c[3:]) <= 400)
        col440_500 = sum(1 for c in cols if c.startswith("col") and 440 <= int(c[3:]) <= 500)
        col522_560 = sum(1 for c in cols if c.startswith("col") and 522 <= int(c[3:]) <= 560)
        assert col323_400 == 78, f"col323-400 应 78 · 实际 {col323_400}"
        assert col440_500 == 61, f"col440-500 应 61 · 实际 {col440_500}"
        assert col522_560 == 39, f"col522-560 应 39 · 实际 {col522_560}"

        # _col582-585 = 4 fields
        assert {"_col582", "_col583", "_col584", "_col585"} <= cols, \
            f"_colXXX 缺 · {cols & {'_col582', '_col583', '_col584', '_col585'}}"

        # 关键列存在
        expected_cols = {
            "column_name", "nonzero_count", "nonzero_ratio",
            "mean", "min_val", "max_val",
            "unique_count", "is_binary",
            "best_correlation_field", "best_correlation_value",
            "maotai_2025_value",
        }
        assert expected_cols <= set(df.columns), \
            f"缺列 · 缺 {expected_cols - set(df.columns)}"
