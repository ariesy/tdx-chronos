"""mootdx_vendor 单元测试 · v1.1 Sprint 1

v1.1 第 7+8 轮修订：单元测试只验"可 import + 可被抽象层调用"
- 不触发 4 bug
- 不连 TdxHQ socket
- 不调 financial module
- 不调 Affair.fetch
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


# 让 src/ 和 vendor/_vendor/ 都能 import
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "vendor" / "_vendor"))


class TestMootdxVendorImport(unittest.TestCase):
    """测试抽象层可以 import"""

    def test_module_importable(self):
        """mootdx_vendor 模块本身可 import"""
        from tdx_chronos.sources import mootdx_vendor  # noqa: F401

    def test_public_api_exists(self):
        """is_vendored_mootdx_available 和 vendored_mootdx_version 是公开 API"""
        from tdx_chronos.sources.mootdx_vendor import (
            is_vendored_mootdx_available,
            vendored_mootdx_version,
        )
        assert callable(is_vendored_mootdx_available)
        assert callable(vendored_mootdx_version)


class TestMootdxVendorIsAvailable(unittest.TestCase):
    """测试 is_vendored_mootdx_available() 行为"""

    def test_returns_true_when_vendored(self):
        """vendor 化后应返回 True"""
        from tdx_chronos.sources.mootdx_vendor import is_vendored_mootdx_available
        result = is_vendored_mootdx_available()
        assert isinstance(result, bool)
        assert result is True, "vendor/_vendor/mootdx 应该在 import path 中"


class TestMootdxVendorVersion(unittest.TestCase):
    """测试 vendored_mootdx_version() 行为"""

    def test_returns_string(self):
        """返回 version string"""
        from tdx_chronos.sources.mootdx_vendor import vendored_mootdx_version
        version = vendored_mootdx_version()
        assert version is not None
        assert isinstance(version, str)
        assert version == "0.11.7", f"应返回 vendored 版本 0.11.7，实际 {version!r}"


class TestMootdxPackage(unittest.TestCase):
    """测试 vendor 化的 mootdx 0.11.7 包本身可 import + 关键属性存在"""

    def test_mootdx_version(self):
        """mootdx.__version__ == 0.11.7"""
        import mootdx
        assert mootdx.__version__ == "0.11.7"

    def test_mootdx_hosts_constants(self):
        """mootdx 暴露 EX_HOSTS / HQ_HOSTS / GP_HOSTS"""
        import mootdx
        # 三个 host 列表都不为空
        assert len(mootdx.EX_HOSTS) > 0
        assert len(mootdx.HQ_HOSTS) > 0
        assert len(mootdx.GP_HOSTS) > 0

    def test_quotes_module_exists(self):
        """mootdx.quotes 模块存在（实际 bug #3/#4 触发位置）"""
        from mootdx import quotes  # noqa: F401
        # 不实例化 · 不调 do_heartbeat · 不连 socket

    def test_affair_module_exists(self):
        """mootdx.affair 模块存在（实际 bug #5 触发位置）"""
        from mootdx import affair  # noqa: F401
        # 不实例化 · 不调 fetch

    def test_financial_init_empty(self):
        """mootdx.financial/__init__.py 是 0 行空文件（bug #6）"""
        import mootdx
        # 验证 financial 包存在
        financial_pkg_path = Path(mootdx.__file__).parent / "financial" / "__init__.py"
        assert financial_pkg_path.exists()
        # 验证 __init__.py 是 0 行（bug #6 真相）
        assert financial_pkg_path.stat().st_size == 0, "mootdx.financial/__init__.py 应该是 0 行空文件"


if __name__ == "__main__":
    unittest.main()
