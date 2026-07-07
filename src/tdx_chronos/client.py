"""Sprint 10 · Query Facade (TdxChronos)

Phase 1 骨架: 仅暴露 TdxChronos class (方法 stub 后续 task 加)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, List, Dict, Any
import pandas as pd


class TdxChronos:
    """5 类离线数据统一 facade · data_dir 必传 (零数据拷贝)

    Args:
        data_dir: 必传 · 数据根目录

    Attributes:
        data_dir: Path (resolved)
    """

    def __init__(self, data_dir: Path | str, *, readonly: bool = True) -> None:
        self.data_dir = Path(data_dir).resolve()
        self.readonly = readonly
