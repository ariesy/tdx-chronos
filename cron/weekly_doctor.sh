#!/bin/bash
# Sprint 5 · weekly_doctor.sh · 03:00 周日
set -euo pipefail
TDX_ROOT="/app/tdx-chronos"
LOG_DIR="$TDX_ROOT/logs/cron"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/weekly_doctor_$(TZ=Asia/Shanghai date +%Y%m%d_%H%M%S).log"

echo "weekly_doctor 启动: $(TZ=Asia/Shanghai date)" | tee -a "$LOG_FILE"

cd "$TDX_ROOT"
export PYTHONPATH=src:vendor/_vendor

.venv/bin/python << 'PYEOF' | tee -a /tmp/weekly_doctor_inner.log
from tdx_chronos.doctor import Doctor
from tdx_chronos.alertor import Alertor

report = Doctor().run()
print(report.summary)

# unhealthy → 飞书告警 (cron 会自动投递到 chat_id)
alertor = Alertor(dry_run=False)
if report.level == "unhealthy":
    alertor.send_alert(
        level="critical",
        summary=f"Doctor unhealthy: {report.failed_count}/8 failed",
        detail=report.summary,
        source="weekly_doctor.sh",
    )
elif report.level == "degraded":
    alertor.send_alert(
        level="warning",
        summary=f"Doctor degraded: {report.failed_count}/8 failed",
        detail=report.summary,
        source="weekly_doctor.sh",
    )
else:
    alertor.send_alert(
        level="success",
        summary="Doctor healthy · 8/8 passed",
        detail=report.summary,
        source="weekly_doctor.sh",
    )
PYEOF
