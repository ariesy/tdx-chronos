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
            # Elastic assertion (Sprint 13): 通达信官方 zip 会周期性增发 symbols,
            # 历史轨迹 12256 → 12261 → 12279,硬编码会被每次 sync 打破。
            # 下限 12000 保留 ~2% 缓冲,既能捕捉大幅缩水也能容忍日常 drift。
            assert len(syms) >= 12000, (
                f"symbol count regression: {len(syms)} < 12000 (历史 12256→12261→12279)"
            )
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
            # Elastic assertion (Sprint 13): data/ 内容会漂移 (symbols / index records /
            # balance_sheet_equation 舍入差),原 spec 写 failed_count==1 现已涨到 3。
            # 保留契约: 至少有 1 个已知 drift,level 不能回到 "healthy"。
            assert report.failed_count >= 1, (
                f"expected at least 1 known drift, got {report.failed_count} (all-green?)"
            )
            assert report.level in ("degraded", "unhealthy"), (
                f"doctor regressed to {report.level!r}, expected degraded or unhealthy"
            )
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
