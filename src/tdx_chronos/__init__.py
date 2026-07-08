"""tdx-chronos · A 股离线数据仓库 (v1.1.0)"""

__version__ = "1.4.2"
__author__ = "朱琨 · claw-cortex"

# Sprint 11 T6 fix: README line 13 写 `from tdx_chronos import TdxChronos` 但 __init__ 没 export
from tdx_chronos.client import TdxChronos  # noqa: F401,E402

__all__ = ["__version__", "__author__", "TdxChronos"]
