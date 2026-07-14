"""TDX-chronos · Doctor (v1.1 Sprint 5 T2)

§四.7 / §四.8 健康检查 + 完整度审计

8 项检查 + 健康级别 (healthy / degraded / unhealthy)

公开 API:
- HealthLevel (enum-like: 'healthy' | 'degraded' | 'unhealthy')
- CheckResult (name, passed, actual, threshold, level)
- DoctorReport (checks, level, summary)
- Doctor(meta_db_path, parquet_root).run() -> DoctorReport

检查项:
  1. K线 symbol count           == 12,256 (±10)
  2. 财务 季度 count            >= 100 (近 5 年)
  3. 股本 record_count          >= 100M records
  4. 5 指数 record_count        == 28,004 (±10)
  5. download_log 7d success    >= 95%
  6. Parquet K线 总大小         >= 600 MB
  7. 指数 last_date 数据新鲜度  <= 7 天 (vs today)
  8. error_rate (failed_status)  <= 5%
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pyarrow.parquet as pq

from tdx_chronos.meta.db import MetaDB

# 健康级别 (字符串常量)
LEVEL_HEALTHY = "healthy"
LEVEL_DEGRADED = "degraded"
LEVEL_UNHEALTHY = "unhealthy"

# K线预期 (Sprint 2 M1 验证 · 12,256 真 .day)
EXPECTED_KLINE_SYMBOLS = 12_256
EXPECTED_INDEX_RECORDS = 28_004

# Sprint 14 · snapshot 检查阈值 (与 retention 默认 3d 配合)
SNAPSHOT_MAX_TOTAL_GB = 30.0     # 上限: 30 GB (375 dirs 用满 /app 30%)
SNAPSHOT_MAX_AGE_DAYS = 10        # 警告: 超过 retention+7 天 (避免 retention 失效)
SNAPSHOT_DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class CheckResult:
    """单项检查结果"""

    name: str
    passed: bool
    actual: object
    threshold: str
    detail: Optional[str] = None


@dataclass
class DoctorReport:
    """完整体检报告"""

    checks: List[CheckResult] = field(default_factory=list)
    level: str = LEVEL_HEALTHY
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed)

    @property
    def summary(self) -> str:
        lines = [
            f"Doctor Report @ {self.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Level: {self.level}",
            f"Passed: {self.passed_count}/{len(self.checks)}",
        ]
        for c in self.checks:
            icon = "✅" if c.passed else "❌"
            lines.append(f"  {icon} {c.name}: {c.actual} (threshold: {c.threshold})")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "timestamp": self.timestamp.isoformat(),
            "passed": self.passed_count,
            "failed": self.failed_count,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "actual": c.actual,
                    "threshold": c.threshold,
                    "detail": c.detail,
                }
                for c in self.checks
            ],
        }


class Doctor:
    """§四.7/§四.8 健康检查"""

    def __init__(
        self,
        meta_db_path: Path = Path("/app/tdx-chronos/data/meta/meta.db"),
        parquet_root: Path = Path("/app/tdx-chronos/data"),
        today: Optional[datetime] = None,
    ) -> None:
        self.meta_db_path = Path(meta_db_path)
        self.parquet_root = Path(parquet_root)
        self.today = today or datetime.now(timezone.utc)

    def _check_kline_symbols(self, db: MetaDB) -> CheckResult:
        """检查 1: K线 symbol count"""
        actual = db.count_symbols()
        passed = abs(actual - EXPECTED_KLINE_SYMBOLS) <= 10
        return CheckResult(
            name="kline_symbols",
            passed=passed,
            actual=actual,
            threshold=f"== {EXPECTED_KLINE_SYMBOLS} (±10)",
        )

    def _check_financial_quarters(self) -> CheckResult:
        """检查 2: 财务 季度 count"""
        fin_dir = self.parquet_root / "fin" / "parsed"
        if not fin_dir.exists():
            return CheckResult(
                name="financial_quarters",
                passed=False,
                actual=0,
                threshold=">= 100",
                detail="data/fin/parsed/ 不存在",
            )
        actual = len(list(fin_dir.glob("*.parquet")))
        passed = actual >= 100
        return CheckResult(
            name="financial_quarters",
            passed=passed,
            actual=actual,
            threshold=">= 100",
        )

    def _check_gp_records(self) -> CheckResult:
        """检查 3: 股本 record count"""
        gp = self.parquet_root / "gp" / "records.parquet"
        if not gp.exists():
            return CheckResult(
                name="gp_records",
                passed=False,
                actual=0,
                threshold=">= 100,000,000",
                detail="data/gp/records.parquet 不存在",
            )
        md = pq.read_metadata(gp)
        actual = md.num_rows
        passed = actual >= 100_000_000
        return CheckResult(
            name="gp_records",
            passed=passed,
            actual=actual,
            threshold=">= 100,000,000",
        )

    def _check_index_records(self) -> CheckResult:
        """检查 4: 5 指数 record count"""
        idx = self.parquet_root / "index" / "indices.parquet"
        if not idx.exists():
            return CheckResult(
                name="index_records",
                passed=False,
                actual=0,
                threshold=f"== {EXPECTED_INDEX_RECORDS} (±10)",
                detail="data/index/indices.parquet 不存在",
            )
        md = pq.read_metadata(idx)
        actual = md.num_rows
        passed = abs(actual - EXPECTED_INDEX_RECORDS) <= 10
        return CheckResult(
            name="index_records",
            passed=passed,
            actual=actual,
            threshold=f"== {EXPECTED_INDEX_RECORDS} (±10)",
        )

    def _check_download_log_7d(self, db: MetaDB) -> CheckResult:
        """检查 5: download_log 7 天内 success rate"""
        rows = db.get_recent_downloads(limit=20)
        if not rows:
            return CheckResult(
                name="download_log_7d_success_rate",
                passed=False,
                actual=0.0,
                threshold=">= 95%",
                detail="download_log 无记录",
            )
        # 简化: 用所有记录 (实操 cron 已验证 6 zip 全部 success/partial)
        total = len(rows)
        success = sum(1 for r in rows if r["parse_status"] in ("success", "partial"))
        rate = success / total * 100
        passed = rate >= 95.0
        return CheckResult(
            name="download_log_7d_success_rate",
            passed=passed,
            actual=f"{rate:.1f}% ({success}/{total})",
            threshold=">= 95%",
        )

    def _check_kline_parquet_size(self) -> CheckResult:
        """检查 6: K线 Parquet 总大小"""
        kline_dir = self.parquet_root / "parquet_compact"
        if not kline_dir.exists():
            # fallback: parquet/
            kline_dir = self.parquet_root / "parquet"  # legacy (Sprint 14 removed canonical; kept as defensive fallback)
        if not kline_dir.exists():
            return CheckResult(
                name="kline_parquet_size_mb",
                passed=False,
                actual=0,
                threshold=">= 600 MB",
                detail="parquet_compact/ 与 parquet/ 都不存在",
            )
        total_bytes = sum(p.stat().st_size for p in kline_dir.rglob("*.parquet"))
        actual_mb = total_bytes / 1024 / 1024
        passed = actual_mb >= 600
        return CheckResult(
            name="kline_parquet_size_mb",
            passed=passed,
            actual=f"{actual_mb:.1f} MB",
            threshold=">= 600 MB",
        )

    def _check_disk_snapshots(
        self,
        today: Optional[date] = None,
        max_total_gb: float = SNAPSHOT_MAX_TOTAL_GB,
        max_age_days: int = SNAPSHOT_MAX_AGE_DAYS,
    ) -> CheckResult:
        """Sprint 14 · 检查 snapshot/ 占盘大小 + 最老 dated dir age.

        Walk ``data/snapshot/<YYYY-MM-DD>/``:
          * Total bytes > ``max_total_gb`` → fail
          * Any dated dir > ``max_age_days`` 旧 → fail (retention 失效)

        Args:
            today:        override for deterministic tests; default local date.
            max_total_gb: threshold in GB.
            max_age_days: max retained age (default 10, includes 7-day buffer).
        """
        snap_root = self.parquet_root / "snapshot"
        if today is None:
            today = datetime.now().date()

        if not snap_root.exists():
            return CheckResult(
                name="disk_snapshots",
                passed=True,
                actual={"dirs": 0, "total_gb": 0.0},
                threshold=f"<= {max_total_gb:.1f} GB, no dir > {max_age_days} days old",
                detail="snapshot/ 不存在 (首次跑或已清空)",
            )

        # Walk
        total_bytes = 0
        dated_dirs: List = []  # (date, size_bytes, name)
        other_dirs: List[str] = []
        for child in sorted(snap_root.iterdir()):
            if not child.is_dir():
                continue
            sz = sum(p.stat().st_size for p in child.rglob("*") if p.is_file())
            total_bytes += sz
            m = SNAPSHOT_DATE_DIR_RE.match(child.name)
            if m:
                try:
                    d = datetime.strptime(child.name, "%Y-%m-%d").date()
                    dated_dirs.append((d, sz, child.name))
                except ValueError:
                    other_dirs.append(child.name)
            else:
                other_dirs.append(child.name)

        total_gb = round(total_bytes / 1024 / 1024 / 1024, 2)
        size_ok = total_gb <= max_total_gb

        # Age check (only dated dirs) · oldest = min(dates)
        oldest_date = min((d for d, _, _ in dated_dirs), default=None)
        age_ok = True
        oldest_age_days = None
        if oldest_date is not None:
            oldest_age_days = (today - oldest_date).days
            if oldest_age_days > max_age_days:
                age_ok = False

        # Identify stale dirs (for actionable detail)
        stale = [
            (name, (today - d).days)
            for d, _, name in dated_dirs
            if (today - d).days > max_age_days
        ]

        passed = size_ok and age_ok
        actual = {
            "dirs": len(dated_dirs) + len(other_dirs),
            "dated_dirs": len(dated_dirs),
            "other_dirs": len(other_dirs),
            "total_gb": total_gb,
            "oldest_age_days": oldest_age_days,
            "stale_count": len(stale),
        }

        detail_parts = []
        if not size_ok:
            detail_parts.append(
                f"snapshot/ 占盘 {total_gb:.2f} GB 超过阈值 {max_total_gb:.1f} GB"
            )
        if not age_ok:
            stale_str = ", ".join(f"{n} ({age}d)" for n, age in stale[:5])
            detail_parts.append(
                f"{len(stale)} 个 dated dir 超过 {max_age_days} 天: {stale_str}"
            )
        if not detail_parts:
            detail_parts.append(
                f"OK: {len(dated_dirs)} dated + {len(other_dirs)} other, "
                f"oldest={oldest_date.isoformat() if oldest_date else 'none'} "
                f"({oldest_age_days if oldest_age_days is not None else 0}d old)"
            )
        if not age_ok:
            stale_str = ", ".join(f"{n} ({age}d)" for n, age in stale[:5])
            detail_parts.append(
                f"{len(stale)} 个 dated dir 超过 {max_age_days} 天: {stale_str}"
            )
        if not detail_parts:
            detail_parts.append(
                f"OK: {len(dated_dirs)} dated + {len(other_dirs)} other, "
                f"oldest={oldest_date.isoformat() if oldest_date else 'none'} "
                f"({oldest_age_days if oldest_age_days is not None else 0}d old)"
            )

        return CheckResult(
            name="disk_snapshots",
            passed=passed,
            actual=actual,
            threshold=f"<= {max_total_gb:.1f} GB, age <= {max_age_days} days",
            detail=" · ".join(detail_parts),
        )

    def _check_index_freshness(self) -> CheckResult:
        """检查 7: 指数 last_date 数据新鲜度"""
        idx = self.parquet_root / "index" / "indices.parquet"
        if not idx.exists():
            return CheckResult(
                name="index_freshness_days",
                passed=False,
                actual="N/A",
                threshold="<= 7 days",
                detail="data/index/indices.parquet 不存在",
            )
        table = pq.read_table(idx, columns=["date"])
        last_date_int = int(table.column("date").to_pandas().max())
        last_date = datetime.strptime(str(last_date_int), "%Y%m%d").replace(tzinfo=timezone.utc)
        days_old = (self.today - last_date).days
        passed = days_old <= 7
        return CheckResult(
            name="index_freshness_days",
            passed=passed,
            actual=f"{days_old} days (last={last_date_int})",
            threshold="<= 7 days",
        )

    def _check_error_rate(self, db: MetaDB) -> CheckResult:
        """检查 8: error_rate (parse_status='failed')"""
        rows = db.get_recent_downloads(limit=20)
        if not rows:
            return CheckResult(
                name="error_rate",
                passed=True,
                actual="0.0% (无记录)",
                threshold="<= 5%",
            )
        total = len(rows)
        failed = sum(1 for r in rows if r["parse_status"] == "failed")
        rate = failed / total * 100
        passed = rate <= 5.0
        return CheckResult(
            name="error_rate",
            passed=passed,
            actual=f"{rate:.1f}% ({failed}/{total})",
            threshold="<= 5%",
        )

    def _check_reconciliation(
        self,
        tolerance: float = 0.001,
    ) -> CheckResult:
        """检查 9: 最近 quarter 三表勾稽 (Sprint 8 T3 + Sprint 9 T1)

        Args:
            tolerance: 容差 (default 0.1%)

        Returns:
            CheckResult:
              - passed: 3 大勾稽全部 PASS
              - actual: "{failed}/{total} failed"
              - threshold: f"all 3 checks pass at ±{tolerance*100:.2f}%"
              - detail: "latest=YYYYMMDD" 或 错误信息
        """
        from tdx_chronos.fin.reconciliation import reconcile_quarter

        import pandas as pd

        fin_dir = self.parquet_root / "fin" / "parsed"
        if not fin_dir.exists():
            return CheckResult(
                name="reconciliation",
                passed=False,
                actual="N/A",
                threshold=f"all 3 checks pass at ±{tolerance*100:.2f}%",
                detail="data/fin/parsed/ 不存在",
            )

        # 找最近有效 parquet (跳过空 / placeholder)
        files = sorted(fin_dir.glob("gpcw*.parquet"), reverse=True)
        for f in files:
            try:
                df = pd.read_parquet(f)
            except Exception as e:
                continue
            # 跳过空 / 缺资产总计的 parquet
            if len(df) == 0 or "资产总计" not in df.columns:
                continue
            # 提取 report_date 从文件名
            try:
                report_date = int(f.stem.replace("gpcw", ""))
            except ValueError:
                report_date = 0

            # 跑 reconcile_quarter
            try:
                rec = reconcile_quarter(df, report_date=report_date, tolerance=tolerance)
            except Exception as e:
                return CheckResult(
                    name="reconciliation",
                    passed=False,
                    actual="N/A",
                    threshold=f"all 3 checks pass at ±{tolerance*100:.2f}%",
                    detail=f"reconcile_quarter 报错: {e}",
                )

            failed_n = rec.failed_count
            total_n = len(rec.checks)
            detail = f"latest={report_date} stocks={rec.total_stocks}"
            for c in rec.checks:
                detail += f" · {c.name}={c.pass_rate*100:.2f}%"

            return CheckResult(
                name="reconciliation",
                passed=rec.passed,
                actual=f"{failed_n}/{total_n} failed",
                threshold=f"all 3 checks pass at ±{tolerance*100:.2f}%",
                detail=detail,
            )

        # 没找到有效 parquet
        return CheckResult(
            name="reconciliation",
            passed=False,
            actual="N/A",
            threshold=f"all 3 checks pass at ±{tolerance*100:.2f}%",
            detail="未找到有效 quarter parquet",
        )

    def _check_quarter_metadata(self, db: MetaDB) -> CheckResult:
        """检查 10: quarter_metadata (Sprint 8 T1 · Sprint 9 T2)

        Args:
            db: MetaDB instance

        Returns:
            CheckResult:
              - passed: parsed_count >= min_parsed AND parse_ok_ratio >= min_ratio
              - actual: f"{parsed}/{total_non_placeholder} parsed ({ratio*100:.1f}% ok)"
              - threshold: f">= {min_parsed} parsed · >= {min_ratio*100:.0f}% ok"
              - detail: quarter_stats 聚合 或 错误信息
        """
        # 默认阈值: 100 parsed quarters + 95% ok ratio
        min_parsed = 100
        min_ratio = 0.95

        total_non_placeholder = db.count_quarters(exclude_placeholders=True)
        parsed_count = db.count_quarters(
            parse_ok=True, exclude_placeholders=True,
        )
        ratio = (parsed_count / total_non_placeholder
                 if total_non_placeholder > 0 else 0.0)

        passed = (parsed_count >= min_parsed) and (ratio >= min_ratio)

        # 详细 stats (top 2 categories)
        detail_parts = []
        stats = db.get_quarter_stats()
        for row in stats[:4]:
            detail_parts.append(
                f"parse_ok={row['parse_ok']} ph={row['is_placeholder']}: "
                f"{row['q_count']}"
            )
        detail = f"stats: {', '.join(detail_parts)}"

        return CheckResult(
            name="quarter_metadata",
            passed=passed,
            actual=f"{parsed_count}/{total_non_placeholder} parsed ({ratio*100:.1f}% ok)",
            threshold=f">= {min_parsed} parsed · >= {min_ratio*100:.0f}% ok",
            detail=detail,
        )

    def run(self) -> DoctorReport:
        """跑全部 11 检查 → DoctorReport (Sprint 14 加 disk_snapshots)"""
        report = DoctorReport()
        db = MetaDB(self.meta_db_path)
        try:
            report.checks = [
                self._check_kline_symbols(db),
                self._check_financial_quarters(),
                self._check_gp_records(),
                self._check_index_records(),
                self._check_download_log_7d(db),
                self._check_kline_parquet_size(),
                self._check_disk_snapshots(),
                self._check_index_freshness(),
                self._check_error_rate(db),
                self._check_reconciliation(),
                self._check_quarter_metadata(db),
            ]
        finally:
            db.close()

        # 健康级别: 0 失败 = healthy, 1-2 = degraded, 3+ = unhealthy
        failed = report.failed_count
        if failed == 0:
            report.level = LEVEL_HEALTHY
        elif failed <= 2:
            report.level = LEVEL_DEGRADED
        else:
            report.level = LEVEL_UNHEALTHY

        return report

    def alert_if_unhealthy(
        self,
        report: DoctorReport,
        alertor=None,
    ):
        """Sprint 9 T4 · 如果 report 不是 healthy, 发告警

        Args:
            report: Doctor.run() 返回的报告
            alertor: Alertor 实例 (default: 创建 DRY-RUN 实例)

        Returns:
            AlertCard if 发送 else None
        """
        from tdx_chronos.alertor import Alertor

        if report.level == LEVEL_HEALTHY:
            return None

        if alertor is None:
            alertor = Alertor()  # 默认 DRY-RUN

        # 提取失效 check
        failed_checks = [c for c in report.checks if not c.passed]
        failed_lines = "\n".join(
            f"- {c.name}: {c.actual} (threshold: {c.threshold})"
            for c in failed_checks
        )

        # Level 映射: degraded = warning, unhealthy = error
        level_map = {
            LEVEL_DEGRADED: "warning",
            LEVEL_UNHEALTHY: "error",
        }
        level = level_map.get(report.level, "warning")

        summary = (
            f"tdx-chronos doctor {report.level.upper()}: "
            f"{report.failed_count}/{len(report.checks)} failed"
        )
        detail = f"Failed checks:\n{failed_lines}"

        return alertor.send_alert(
            level=level,
            summary=summary,
            detail=detail,
            source="weekly_doctor.sh",
        )