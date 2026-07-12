"""Sprint 10 · Query Facade (TdxChronos)

Phase 1 骨架: 仅暴露 TdxChronos class (方法 stub 后续 task 加)
"""
from __future__ import annotations

import logging
import os
import re
import stat
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq


class TdxChronos:
    """5 类离线数据统一 facade · data_dir 必传 (零数据拷贝)

    覆盖范围 (Sprint 13 明确化):
      - A 股 (sh6/sz0/sz3/bj4/bj8/bj92) — 日 K + 财务 + 股本
      - **场内基金 / ETF / LOF / REITs / 封闭基金** (sh5/sh1/sz1 部分) — 日 K + 股本
      - **可转债** (sh11/sh12/sz12 部分) — 日 K + 股本
      - 上证/深证主要指数 (sh000xxx/sz399xxx) — 日 K

    Args:
        data_dir: 必传 · 数据根目录

    Attributes:
        data_dir: Path (resolved)

    ETF/基金 使用提示:
      - 取列表:  ``list_etfs()`` 或 ``list_etfs(market='sh')``
      - 取日 K:  ``kline('sh510050', '2024-01-01', '2024-12-31')``  (与个股同 API)
      - 取股本:  ``shareholders('sh510050')`` (含 ETF)
      - 取财务:  ``finance('sh510050')`` → **空 DataFrame** (tdxfin.zip 不含基金)
    """

    SUBDIRS_REQUIRED = [
        "parquet_compact",
        "fin/parsed",
        "gp",
        "index",
        "meta",
    ]
    FILES_REQUIRED = [
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
        self._index_klines_path = self.data_dir / "index" / "indices.parquet"
        self.meta_db_path = self.data_dir / "meta" / "meta.db"
        self.readonly = readonly
        self._db: Optional[Any] = None
        if readonly:
            self._lock_for_readonly()

    def _lock_for_readonly(self):
        for p in [self.gp_records, self._index_klines_path, self.meta_db_path]:
            if p.is_file():
                try:
                    os.chmod(p, stat.S_IRUSR)
                except PermissionError:
                    pass

    def close(self):
        # 1. Always release db connection FIRST (regardless of readonly)
        db, self._db = self._db, None
        if db is not None:
            db.close()
        # 2. Then restore chmod only when readonly=True
        if not self.readonly:
            return
        for p in [self.gp_records, self._index_klines_path, self.meta_db_path]:
            if p.is_file():
                try:
                    os.chmod(p, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                except PermissionError as e:
                    raise RuntimeError(
                        f"close() failed to restore write permission on {p}: {e}. "
                        f"cron may be unable to write until manually chmod'd."
                    ) from e

    # ─── Task 3: symbol_info + list_symbols ────────────────────────────────────

    def _ensure_db(self) -> Any:
        """Lazy init MetaDB connection"""
        if self._db is None:
            from tdx_chronos.meta.db import MetaDB
            self._db = MetaDB(self.meta_db_path)
            self._db.init_schema()
        return self._db

    def symbol_info(self, symbol: str) -> Dict[str, Any]:
        """symbol metadata lookup · returns dict or {} when not found

        Args:
            symbol: 'sh600000' / 'sz000001' / 'bj838000'

        Returns:
            dict · 含 symbol/market/first_listing_date/record_count/source_zip
            找不到返回 {} (不 raise)
        """
        db = self._ensure_db()
        return db.get_symbol(_normalize_symbol(symbol)) or {}

    def list_symbols(self, market: Optional[str] = None) -> List[str]:
        """list symbols in meta.db

        Args:
            market: 'sh'/'sz'/'bj' filter · None=全部 3 个市场

        Returns:
            List[str] · sorted by symbol ASC

        Note:
            返回**全部**标的,含 A 股 + 场内基金 (含 ETF) + 可转债 + REITs + 指数。
            若仅需 ETF/基金/可转债, 用 ``list_etfs(market=...)`` 更精准。
        """
        db = self._ensure_db()
        return db.list_symbols(market)

    def list_etfs(self, market: Optional[str] = None) -> List[str]:
        """list 场内基金 / ETF / LOF / REITs / 可转债 symbols

        适合 ETF Beta 跟踪 / 行业 ETF 筛选 / 跨境 ETF 拉数据等场景。

        Args:
            market: 'sh'/'sz' filter · None=全部 (忽略 bj, 北交所无场内基金)

        Returns:
            List[str] · sorted by symbol ASC

        代码段规则 (通达信/SSE/SZSE 公开代码分配):
            sh5xxxxx — 沪市基金
                - 50xxxx : 老封闭式基金 (1998-1999 上市, 如 sh500001 基金金泰)
                - 51xxxx : ETF (510/511/512/513/515/518 跨/单/跨境/主题/行业)
                - 56xxxx : 沪市 LOF
                - 58xxxx : 科创板 ETF (588xxx)
            sh1xxxxx — 沪市可转债 (110-113 段)
            sz15xxxx (=sz159xxx) — **深市 ETF** (创业板/沪深300/恒生等)
            sz16xxxx — 深市 LOF
            sz18xxxx — 深市 **公募 REITs** (基础设施证券投资基金)
            sz12xxxx — 深市可转债 (123/127/128 段)

        数据可用性 (Sprint 13 验证):
            ✅ 日 K 线 (来自 hsjday.zip · 12,279 symbols 全覆盖)
            ✅ 股本变动 (来自 tdxgp.zip · 7,573 symbols 含场内基金)
            ❌ 财务三表 (tdxfin.zip 仅 A 股, 调用 finance() 返回空 DataFrame)

        Example:
            >>> etfs = tdx.list_etfs()
            >>> 'sh510050' in etfs  # 50ETF
            True
            >>> 'sz159915' in etfs  # 创业板ETF
            True
            >>> sh_etfs = tdx.list_etfs(market='sh')
            >>> df = tdx.kline('sh510050', start='2024-01-01')
        """
        db = self._ensure_db()
        if market is None:
            all_syms = db.list_symbols()
        else:
            all_syms = db.list_symbols(market)
        return [s for s in all_syms if _is_fund_or_bond(s)]

    # ─── Task 4: kline (pyarrow predicate pushdown) ──────────────────────────

    def kline(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        columns: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """K 线 · 单 symbol · pandas DataFrame (sorted by date ASC)

        支持 A 股 / 场内基金 (含 ETF / LOF) / 可转债 / 指数 — 来自 hsjday.zip 全覆盖。

        Args:
            symbol: 'sh600000' / 'sz000001' / 'bj838000' / 'sh510050' (50ETF) / 'sz159915' (创业板ETF)
            start:  起始日期 (inclusive) · 'YYYY-MM-DD' or 'YYYYMMDD'
            end:    截止日期 (inclusive)
            columns:  子集 columns · None=全部

        Returns:
            DataFrame [date, open, high, low, close, volume, amount, market, ...]
            找不到返回 empty DataFrame (不 raise)

        ETF/基金 示例:
            >>> df = tdx.kline('sh510050', start='2024-01-01')   # 50ETF
            >>> df = tdx.kline('sz159915', start='2024-01-01')   # 创业板ETF
            >>> df = tdx.kline('sh588200', start='2024-01-01')   # 科创50ETF
        """
        norm = _normalize_symbol(symbol)
        if start and end and _to_yyyymmdd_int(start) > _to_yyyymmdd_int(end):
            raise ValueError(f"start ({start}) must be <= end ({end})")

        market = norm[:2]
        kline_path = self.parquet_compact / market / f"{norm}.parquet"

        if not kline_path.exists():
            return pd.DataFrame()

        filters = [("symbol", "=", norm)]
        if start:
            filters.append(("date", ">=", _to_yyyymmdd_int(start)))
        if end:
            filters.append(("date", "<=", _to_yyyymmdd_int(end)))

        try:
            table = pq.read_table(str(kline_path), filters=filters, columns=columns)
        except (pa.ArrowInvalid, OSError) as e:
            logging.warning("kline read failed for %s: %s", kline_path, e)
            return pd.DataFrame()

        df = table.to_pandas()
        if not df.empty:
            # kline return cols: no symbol column (already used for predicate)
            if "symbol" in df.columns:
                df = df.drop(columns=["symbol"])
            df = df.sort_values("date").reset_index(drop=True)
        return df

    # ─── Task 5: finance + shareholders + index_klines + list_quarters + doctor ─

    def finance(
        self,
        symbol: str,
        report_date: Optional[str] = None,
        ratio_only: bool = False,
    ) -> pd.DataFrame:
        """单 symbol 财务 · 多 quarter 默认

        Args:
            symbol: 'sh600000' 或 '600000'
            report_date: 单 quarter · None=全部 available
            ratio_only: True=仅 ratio 类型 columns (简化版)

        Returns:
            DataFrame 每行 = 1 个 (symbol, quarter) · 找不到返回 empty DataFrame

        Note:
            **ETF / 场内基金 / 可转债不在 tdxfin.zip 范围内**, 调用本方法对 ETF 代码
            会直接返回 **空 DataFrame** (非错误)。ETF 财务数据需走 tushare `fund_basic`
            或类似第三方源补全 — 见 POC `decision.md` Phase 1.5。
        """
        norm = _normalize_symbol(symbol)
        bare = norm[2:] if norm.startswith(("sh", "sz", "bj")) else norm

        files = sorted(self.fin_parsed.glob("gpcw*.parquet"))
        if not files:
            return pd.DataFrame()

        if report_date:
            target_yyyymmdd = _to_yyyymmdd_int(report_date)
            files = [
                f for f in files
                if f.stem.replace("gpcw", "") == str(target_yyyymmdd)
            ]
            if not files:
                return pd.DataFrame()

        rows = []
        for f in files:
            df = pd.read_parquet(f)
            if not df.empty:
                df = df.reset_index() if "code" not in df.columns else df
                match = df[df["code"].astype(str) == bare]
                if not match.empty:
                    rd = int(f.stem.replace("gpcw", ""))
                    match = match.assign(report_date=rd)
                    if ratio_only:
                        ratio_cols = [
                            c for c in match.columns
                            if "ratio" in c.lower() or "率" in c
                        ]
                        match = match[["code", "report_date"] + ratio_cols]
                    rows.append(match)
        return pd.concat(rows).reset_index(drop=True) if rows else pd.DataFrame()

    def shareholders(self, symbol: str) -> pd.DataFrame:
        """股本 · 按 symbol 过滤

        Args:
            symbol: 'sh600000' 或 'sh510050' (50ETF, 场内基金同样在 tdxgp.zip 范围内)

        Returns:
            DataFrame (可能 empty) · 不 raise · 找不到返回 empty DataFrame

        Note:
            支持 **A 股 + 场内基金 (含 ETF) + 可转债**,全部从 tdxgp.zip 解析。
            实测 sh510050 有 ~2000 行 type=25 股本变动 records。
        """
        norm = _normalize_symbol(symbol)
        bare = norm[2:] if norm.startswith(("sh", "sz", "bj")) else norm
        try:
            table = pq.read_table(str(self.gp_records), filters=[("code", "=", bare)])
        except (pa.ArrowInvalid, OSError) as e:
            logging.warning("shareholders read failed for %s: %s", self.gp_records, e)
            return pd.DataFrame()
        df = table.to_pandas()
        if not df.empty and "symbol" not in df.columns:
            df = df.assign(symbol=df["market"] + df["code"])
        return df

    def shareholders_history(
        self,
        symbol: str,
        types: Optional[List[int]] = None,
        since_date: Optional[Union[int, str]] = None,
        until_date: Optional[Union[int, str]] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """股本历史 · 带 filter 条件

        Args:
            symbol:     'sh600000'
            types:      type filter · e.g. [1, 2, 3, 4] 股本变动; None=全部
            since_date: YYYYMMDD (int) or 'YYYY-MM-DD' (str); None=不限
            until_date: 同上
            limit:      返回最多 N 行 (按 date DESC); None=全部

        Returns:
            DataFrame · type/date/value_1/value_2/market/code/symbol
            可能 empty (找不到 symbol) · 不 raise
        """
        norm = _normalize_symbol(symbol)
        bare = norm[2:] if norm.startswith(("sh", "sz", "bj")) else norm

        # Build pyarrow filter expression
        filters = [ds.field("code") == bare]
        if types:
            filters.append(ds.field("type").isin(types))
        if since_date is not None:
            since_int = _to_yyyymmdd_int(str(since_date))
            filters.append(ds.field("date") >= since_int)
        if until_date is not None:
            until_int = _to_yyyymmdd_int(str(until_date))
            filters.append(ds.field("date") <= until_int)
        from functools import reduce
        import operator
        combined = reduce(operator.and_, filters)

        try:
            if not self.gp_records.exists():
                return pd.DataFrame()
            dataset = ds.dataset(str(self.gp_records), format="parquet")
            table = dataset.to_table(filter=combined, columns=[
                "type", "date", "value_1", "value_2", "market", "code",
            ])
        except (pa.ArrowInvalid, OSError) as e:
            logging.warning("shareholders_history read failed for %s: %s", self.gp_records, e)
            return pd.DataFrame()

        df = table.to_pandas()
        if not df.empty:
            df = df.sort_values("date", ascending=False)
            if limit is not None:
                df = df.head(limit).reset_index(drop=True)
            if "symbol" not in df.columns:
                df = df.assign(symbol=df["market"] + df["code"])
        return df

    def index_klines(
        self,
        index_code: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """5 指数日线 · pandas DataFrame

        Args:
            index_code: 'sh000001'
            start: 起始日期 (inclusive) · 'YYYY-MM-DD' or 'YYYYMMDD'
            end:  截止日期 (inclusive)

        Returns:
            DataFrame sorted by date ASC · 找不到返回 empty DataFrame
        """
        code = index_code.lower()
        filters: List[tuple] = [("symbol", "=", code)]
        if start:
            filters.append(("date", ">=", _to_yyyymmdd_int(start)))
        if end:
            filters.append(("date", "<=", _to_yyyymmdd_int(end)))
        try:
            table = pq.read_table(str(self._index_klines_path), filters=filters)
        except (pa.ArrowInvalid, OSError) as e:
            logging.warning("index_klines read failed for %s: %s", self._index_klines_path, e)
            return pd.DataFrame()
        df = table.to_pandas()
        if not df.empty:
            df = df.sort_values("date").reset_index(drop=True)
            # Sprint 12 T4 · 与 kline() 契约一致 · drop symbol 列
            if "symbol" in df.columns:
                df = df.drop(columns=["symbol"])
        return df

    def list_quarters(self) -> List[str]:
        """list 已 parsed 季度 · 'YYYY-MM-DD' strings

        Returns:
            List[str] · sorted by date DESC (newest first: '2026-03-31', '2025-12-31', ...)
            Files not matching 8-digit date stem are skipped (defensive)
        """
        _QUARTER_STEM_RE = re.compile(r"^gpcw(\d{8})\.parquet$")
        dates: list[int] = []
        for f in self.fin_parsed.glob("gpcw*.parquet"):
            m = _QUARTER_STEM_RE.match(f.name)
            if m is None:
                continue
            dates.append(int(m.group(1)))
        dates.sort(reverse=True)
        return [_int_to_yyyymmdd_dash(d) for d in dates]

    def doctor(self) -> DoctorReport:
        """复用现有 Doctor().run()"""
        from tdx_chronos.doctor import Doctor  # lazy to avoid circular import
        return Doctor(
            meta_db_path=self.meta_db_path,
            parquet_root=self.data_dir,
        ).run()


def _int_to_yyyymmdd_dash(n: int) -> str:
    """20251231 → '2025-12-31'"""
    s = str(n)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def _normalize_symbol(symbol: str) -> str:
    """Normalize bare 6-digit codes to sh/sz/bj prefix"""
    s = symbol.lower().strip()
    if s.startswith(("sh", "sz", "bj")):
        return s
    if len(s) == 6 and s.isdigit():
        if s.startswith("92"):                  # Sprint 12 T1 · 北交所新股优先
            return "bj" + s
        if s.startswith(("5", "6", "9")):
            return "sh" + s
        if s.startswith(("0", "2", "3")):
            return "sz" + s
        if s.startswith(("4", "8")):
            return "bj" + s
    return s


def _is_fund_or_bond(symbol: str) -> bool:
    """判定 symbol 是否属于场内基金 / ETF / LOF / REITs / 可转债

    基于通达信 / SSE / SZSE 公开代码分配规则 (Sprint 13 验证):
      - sh5xxxxx → 沪市基金 (老封基 50x + ETF 51x + LOF 56x + 科创 ETF 588x)
      - sh1xxxxx → 沪市可转债 (110-113 段)
      - sz15xxxx (=sz159xxx) → 深市 ETF
      - sz16xxxx → 深市 LOF
      - sz18xxxx → 深市 REITs
      - sz12xxxx → 深市可转债 (123/127/128 段)

    Returns:
        True = 场内基金/可转债家族, False = A 股/指数/其他
    """
    s = symbol.lower()
    if s.startswith(("sh5", "sh1")):
        return True
    if s.startswith("sz1"):
        return True
    return False


def _to_yyyymmdd_int(s: str) -> int:
    """'2024-01-02' → 20240102"""
    s = s.replace("-", "").replace("/", "")
    return int(s)
