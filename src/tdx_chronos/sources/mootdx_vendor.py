"""mootdx vendor 抽象层 · v2.0 实时增量备用 · v1.1 主路径不依赖

设计原则（v1.1 第 7+8 轮修订）：
- 抽象层仅定义接口（is_vendored_mootdx_available / version）·
- 实际实时增量调用在 v2.0 才实现
- v1.1 主路径（官方 .day 集中下载）完全绕开此模块
- 单元测试只验 "可 import + 可被抽象层调用"（不验 4 bug 触发）

4 bug 状态（v1.1 不修·v1.1 主路径 0 触发）：
- Bug #3 · StdQuotes.do_heartbeat() 多次请求卡死
- Bug #4 · StdQuotes multithread=True 多次请求卡顿
- Bug #5 · Affair.fetch(filename=str) 实际行为与参数类型不匹配
- Bug #6 · mootdx.financial/__init__.py 0 行
"""

from __future__ import annotations

from typing import Optional


def is_vendored_mootdx_available() -> bool:
    """检查 vendor 化的 mootdx 0.11.7 是否可用
    
    Returns:
        True if vendor/mootdx/mootdx/ 可被 import
        
    Note:
        单元测试只验 "可 import + 返回 bool" · 不触发 4 bug
    """
    try:
        import mootdx  # noqa: F401
        return True
    except ImportError:
        return False


def vendored_mootdx_version() -> Optional[str]:
    """返回 vendor 化的 mootdx 版本号
    
    Returns:
        version string (e.g. '0.11.7') · or None if not available
        
    Note:
        单元测试只验 "可调用 + 返回 string 或 None"
    """
    try:
        import mootdx
        return getattr(mootdx, '__version__', None)
    except ImportError:
        return None


__all__ = [
    'is_vendored_mootdx_available',
    'vendored_mootdx_version',
]
