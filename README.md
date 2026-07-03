# tdx-chronos

> **A 股离线数据仓库** · 通达信 .day 集中下载 + Parquet 整理 + 本地调用接口

[![Status](https://img.shields.io/badge/status-v1.1.0-blue)]() [![Python](https://img.shields.io/badge/python-3.12-green)]() [![License](https://img.shields.io/badge/license-MIT-lightgrey)]()

## v1.1 是什么

`tdx-chronos` 每天 17:30 从通达信官方服务器下 5 个 zip（hsjday/tdxfin/tdxgp + 2 指数），
周日 02:00 下 tdxfin 周更，解 .day/.dat 为 Parquet，存到本地供 daily_stock_analysis 等下游调用。

**核心数据流**：
```
通达信官方 zip → curl → 本地 ZIP → struct 解析 → Parquet → SQLite 元数据
                       ↓
                  daily_sync.sh (cron 17:30)
                  weekly_sync.sh (cron Sun 02:00)
```

## v1.1 不做什么

- ❌ 多源验证（sina/同花顺/tushare）— v2.0 预留
- ❌ 在线实时推送 — v2.0 预留
- ❌ HTTP 兜底 — v2.0 预留
- ❌ 修复 mootdx 4 个 bug — 主路径不触发，记入 vendor/UPGRADE_NOTES.md

## 快速开始

```bash
# 1. 装 venv
python3 -m venv .venv
.venv/bin/pip install vendoring pytest pandas pyarrow requests

# 2. 验证 vendoring（委员会 Confidence Medium → High 必跑）
python3 -m vendoring sync vendor/mootdx/

# 3. 跑测试
.venv/bin/pytest tests/

# 4. 启动下载（仅开发期 · 实际由 cron 触发）
bash cron/daily_sync.sh
```

## 文档

- **需求文档**：[requirements.md](requirements.md) · 唯一权威
- **Sprint 报告**：[logs/](logs/)
- **贡献指南**：[docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)

## 项目状态

| 轮 | 关键变更 | 日期 |
|---|---|---|
| 1 | Q4 vendor 模式 + 委员会 P0 补正 | 2026-07-03 |
| 2-4 | 18 zip 摸排 + 数据格式 + 解析器 | 2026-07-03 |
| 5-8 | 里程碑重写 + 砍多源 + 4 bug 不修 + 委员会 P0 补正 | 2026-07-03 |
| **Sprint 0** | **项目初始化** | **2026-07-03** |

v1.1.0 · 25.5-27 工作日 · 9 Sprint · 5 验证里程碑

## License

MIT
