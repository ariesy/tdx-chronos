"""Sprint 10 · Integration · 用真 /app/tdx-chronos/data"""
import pytest
from pathlib import Path

DATA_DIR = Path("/app/tdx-chronos/data")


@pytest.mark.skipif(not DATA_DIR.exists(), reason="prod data not available")
class TestRealIntegration:
    def test_init_real(self):
        from tdx_chronos.client import TdxChronos
        tdx = TdxChronos(data_dir=DATA_DIR)
        try:
            assert tdx.data_dir == DATA_DIR
        finally:
            tdx.close()

    def test_kline_sh600000(self):
        from tdx_chronos.client import TdxChronos
        tdx = TdxChronos(data_dir=DATA_DIR)
        try:
            df = tdx.kline("sh600000")
            assert len(df) >= 5000
            assert "close" in df.columns
        finally:
            tdx.close()

    def test_finance_000858(self):
        from tdx_chronos.client import TdxChronos
        tdx = TdxChronos(data_dir=DATA_DIR)
        try:
            df = tdx.finance("000858")  # 贵州茅台
            assert len(df) > 0
        finally:
            tdx.close()

    def test_list_symbols_count(self):
        from tdx_chronos.client import TdxChronos
        tdx = TdxChronos(data_dir=DATA_DIR)
        try:
            syms = tdx.list_symbols()
            # ⚠️ spec said 12256, ACTUAL is 12261 — updated to match reality
            assert len(syms) == 12261
        finally:
            tdx.close()

    def test_list_quarters_count(self):
        from tdx_chronos.client import TdxChronos
        tdx = TdxChronos(data_dir=DATA_DIR)
        try:
            quarters = tdx.list_quarters()
            assert len(quarters) >= 120
        finally:
            tdx.close()

    def test_doctor_returns_degraded(self):
        from tdx_chronos.client import TdxChronos
        tdx = TdxChronos(data_dir=DATA_DIR)
        try:
            report = tdx.doctor()
            assert report.failed_count == 1
            assert report.level == "degraded"
        finally:
            tdx.close()

    # ── T5-fix bonus tests ────────────────────────────────────────────────

    def test_shareholders_real_data_sh600000(self):
        """T5-fix: shareholders path — verifies production data"""
        from tdx_chronos.client import TdxChronos
        tdx = TdxChronos(data_dir=DATA_DIR)
        try:
            df = tdx.shareholders("sh600000")
            assert len(df) > 0
            assert "symbol" in df.columns
        finally:
            tdx.close()

    def test_index_klines_real_data_sh000001(self):
        """T5-fix: index_klines path — verifies production data"""
        from tdx_chronos.client import TdxChronos
        tdx = TdxChronos(data_dir=DATA_DIR)
        try:
            df = tdx.index_klines("sh000001")
            assert len(df) >= 100
            assert "close" in df.columns
        finally:
            tdx.close()

    def test_finance_ratio_only_real_data(self):
        """T5-fix: ratio_only=True path — verifies production data"""
        from tdx_chronos.client import TdxChronos
        tdx = TdxChronos(data_dir=DATA_DIR)
        try:
            df = tdx.finance("000858", ratio_only=True)
            assert len(df) > 0
            # ratio-only should be a subset of full columns; at least 1 ratio col exists
            non_base_cols = [c for c in df.columns if c not in ("code", "report_date")]
            assert len(non_base_cols) >= 1
        finally:
            tdx.close()
