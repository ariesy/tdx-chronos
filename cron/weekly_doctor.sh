#!/bin/bash
# Sprint 9 T4 修正 · weekly_doctor.sh · 周日 03:00 Shanghai
# 修复点 (Sprint 5 → Sprint 9):
# - 使用 Sprint 9 T4 alert_if_unhealthy (替代 hardcoded if-elif)
# - 失败数动态 (10 checks 当前 · 而不是 hardcoded "8")
# - DRY-RUN 由 TDX_DRY_RUN env var 控制 (默认 1, 上线后改为 0)
set -euo pipefail
TDX_ROOT="/app/tdx-chronos"
LOG_DIR="$TDX_ROOT/logs/cron"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/weekly_doctor_$(TZ=Asia/Shanghai date +%Y%m%d_%H%M%S).log"

echo "weekly_doctor 启动: $(TZ=Asia/Shanghai date)" | tee -a "$LOG_FILE"

cd "$TDX_ROOT"
export PYTHONPATH=src:vendor/_vendor

.venv/bin/python << 'PYEOF' | tee -a /tmp/weekly_doctor_inner.log
"""Sprint 9 T4 修 · weekly_doctor.sh 内容

修复: 使用 alert_if_unhealthy (Sprint 9 T4) 替代 hardcoded 8/8 if-elif
"""
import os
from tdx_chronos.doctor import Doctor
from tdx_chronos.alertor import Alertor

# dry_run 默认 True · 上线生产时设 TDX_DRY_RUN=0
dry_run = os.environ.get("TDX_DRY_RUN", "1") == "1"
alertor = Alertor(dry_run=dry_run)

report = Doctor().run()
print(report.summary)

# Sprint 9 T4 API: alert_if_unhealthy 自动按 level 分发 tone
# - healthy   → 不发
# - degraded  → warning
# - unhealthy → error (danger tone)
result = Doctor().alert_if_unhealthy(report, alertor=alertor)
if result is None:
    print(f"healthy level · no alert · {report.failed_count}/{len(report.checks)} failed")
else:
    print(f"alert sent · level={report.level} · tone={result.tone}")
PYEOF
