# Contributing to tdx-chronos

> **项目代号**：`tdx-chronos`（Chronos · 时间之神 · 契合"每日增量 + 历史持久化"）
> **作者**：朱琨 · claw-cortex
> **目标版本**：v1.1.0 · 25.5-27 工作日

## 文档结构

```
tdx-chronos/
├── requirements.md       # v1.1 需求文档（唯一权威）
├── docs/
│   └── CONTRIBUTING.md  # 本文档
├── src/tdx_chronos/     # 主代码
├── vendor/mootdx/       # v2.0 备用（不修 4 bug）
├── cron/                # daily_sync.sh + weekly_sync.sh
├── data/                # 不 commit
├── tests/               # unit / integration / fixtures
├── scripts/             # 工具脚本
└── logs/                # 运行时日志
```

## 开发循环

1. **看需求** — `requirements.md` §三/§四/§六/§七
2. **看 Sprint** — §六 当前 Sprint 编号（0-7）
3. **写代码** — `src/tdx_chronos/<module>.py` + `tests/unit/test_<module>.py`
4. **跑测试** — `.venv/bin/pytest tests/`
5. **commit** — `git add -A && git commit -m "Sprint X · <deliverable>"`
6. **更新 Sprint 报告** — `logs/sprintX-report.md`

## Sprint 0 启动检查表

- [ ] GitHub repo 创立
- [ ] 目录骨架（已建）
- [ ] venv 工具链（vendoring 1.4.0 ✅ · pytest ✅ · pandas ✅ · pyarrow ✅）
- [ ] Sprint 0 报告（logs/sprint0-report.md）
- [ ] 初始化 commit

## v1.1 主路径速查

| 任务 | 调用方 | 不调 mootdx |
|---|---|---|
| 下 5 zip 工作日 17:30 | `cron/daily_sync.sh` | ✅ curl |
| 下 1 zip 周日 02:00 | `cron/weekly_sync.sh` | ✅ curl |
| 解析 .day → Parquet | `src/tdx_chronos/sources/official_zip.py` | ✅ struct |
| 解析 .dat → DataFrame | `src/tdx_chronos/sources/financial.py` | ✅ struct |
| 飞书告警 | `src/tdx_chronos/alerts/feishu.py` | ✅ requests |

## 不允许的事

- ❌ 在 v1.1 调用 `mootdx.financial`（4 bug 触发）
- ❌ 在 v1.1 调 `TdxHq_API` socket（4 bug 触发）
- ❌ commit `data/` 目录（大数据卷不 git 跟踪）
- ❌ 改 `vendor/mootdx/`（4 bug 不修 · 仅记入 UPGRADE_NOTES.md）

## 委员会验收

v1.1 第 8 轮委员会评审 Confidence: **High**（vendoring 工具链 Sprint 0 验证通过）

> Sprint 0 末必须先验：`pip install vendoring && python -m vendoring sync vendor/mootdx/`
> Sprint 1 才能开干（vendor 化 + 单元测试）

## 联系人

- 主人：朱琨（ariesy.bleiben@gmail.com）
- AI 助手：claw-cortex 🦞
