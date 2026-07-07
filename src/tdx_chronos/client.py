"""Sprint 10 · Query Facade (TdxChronos)

Phase 1 骨架: 仅暴露 TdxChronos class (方法 stub 后续 task 加)
"""
from __future__ import annotations

import os
import stat
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

    SUBDIRS_REQUIRED = [
        "parquet_compact",
        "fin/parsed",
        "gp",
        "index",
        "meta",
    ]
    FILES_REQUIRED = [
        "gp/records.parquet",
        "index/indices.parquet",
        "meta/meta.db",
    ]

    def __init__(self, data_dir: Path | str, *, readonly: bool = True) -> None:
        self.data_dir = Path(data_dir).resolve()
        if not self.data_dir.is_dir():
            raise FileNotFoundError(f"data_dir 不存在: {self.data_dir}")
        missing = []
        for sub in self.SUBDIRS_REQUIRED:
            if not (self.data_dir / sub).is_dir():
                missing.append(str(self.data_dir / sub))
        for f in self.FILES_REQUIRED:
            if not (self.data_dir / f).is_file():
                missing.append(str(self.data_dir / f))
        if missing:
            raise FileNotFoundError(
                f"data_dir 不完整 ({len(missing)}/8 缺失):\n  "
                + "\n  ".join(missing)
            )
        self.parquet_compact = self.data_dir / "parquet_compact"
        self.fin_parsed = self.data_dir / "fin" / "parsed"
        self.gp_records = self.data_dir / "gp" / "records.parquet"
        self.index_klines = self.data_dir / "index" / "indices.parquet"
        self.meta_db_path = self.data_dir / "meta" / "meta.db"
        self.readonly = readonly
        self._db: Optional[Any] = None
        if readonly:
            self._lock_for_readonly()

    def _lock_for_readonly(self):
        for p in [self.gp_records, self.index_klines, self.meta_db_path]:
            if p.is_file():
                try:
                    os.chmod(p, stat.S_IRUSR)
                except PermissionError:
                    pass

    def close(self):
        if not self.readonly:
            return
        for p in [self.gp_records, self.index_klines, self.meta_db_path]:
            if p.is_file():
                try:
                    os.chmod(p, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                except (PermissionError, FileNotFoundError):
                    pass
        if self._db is not None:
            self._db.close()
            self._db = None
