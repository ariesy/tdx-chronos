# tdx-chronos

> **A 股离线数据仓库** · 通达信 .day/.dat 集中下载 + Parquet 整理 + 本地调用接口

[![Status](https://img.shields.io/badge/status-v1.1.0-blue)]() [![Python](https://img.shields.io/badge/python-3.12-green)]() [![Tests](https://img.shields.io/badge/tests-229%20passed-brightgreen)]() [![License](https://img.shields.io/badge/license-MIT-lightgrey)]()

## v1.1 是什么

`tdx-chronos` 每天 17:30 (Asia/Shanghai) 从通达信官方服务器下 5 个 zip（hsjday/tdxfin/tdxgp + 2 指数），
周日 02:00 下 tdxfin 周更，解 .day/.dat 为 Parquet，存到本地供下游分析使用。

**核心数据流**：
```
通达信官方 zip → curl → 本地 ZIP → struct 解析 → Parquet → SQLite 元数据
                       ↓
                  daily_sync.sh (cron Mon-Fri 17:30)
                  weekly_sync.sh (cron Sun 02:00)
                  weekly_doctor.sh (cron Sun 03:00 · 健康检查 + 飞书告警)
```

## 数据规模 (v1.1)

| 类别 | 数量 | 备注 |
|---|---:|---|
| 股票 (symbols) | **12,256** | A 股 + 港股 + 美股 |
| 股本 records | **120,340,424** | 7,571 .dat 文件 · 587.7 MB Parquet |
| 财务 quarters | 121 | 5 个 zip 周更 |
| 指数 records | **28,004** | 5 个指数日线 |
| 股本 type 字段语义 | **33 types 映射** | 5 categories · 100% 覆盖 |

## 5 大模块

1. **kline** - 日线 (.day) → Parquet (12,256 stocks)
2. **financial** - 财务 (.dat) → Parquet (121 quarters)
3. **gp** - 股本 (.dat) → Parquet (1.2 亿 records · 5 categories 语义映射)
4. **index** - 指数 (.day) → Parquet (28,004 records)
5. **cron + doctor + alertor** - 健康检查 + 飞书告警

## 快速开始

```bash
# 1. 装 venv
python3 -m venv .venv
.venv/bin/pip install vendoring pytest pandas pyarrow requests

# 2. 验证 vendoring（committee Confidence Medium → High 必跑）
python3 -m vendoring sync vendor/mootdx/

# 3. 跑测试 (229 PASSED)
.venv/bin/pytest tests/

# 4. 启动下载（开发期 · 实际由 cron 触发）
bash cron/daily_sync.sh

# 5. 启动股本分类探索
PYTHONPATH=src:vendor/_vendor .venv/bin/python -c "
from tdx_chronos.fin.tdxgp_types import CATEGORY_BUCKETS, get_type_name
print(f'capital_share: {len(CATEGORY_BUCKETS[\"capital_share\"])} types')
print(f'type 21 name: {get_type_name(21)}')
"
```

## v1.1 核心 API

```python
from pathlib import Path
from tdx_chronos.fin.tdxgp_record import TdxGpRecordReader
from tdx_chronos.fin.tdxgp_types import CATEGORY_BUCKETS, get_type_name

# 按 category 获取股本 records
df = TdxGpRecordReader.to_categorized(
    Path("data/gp/records.parquet"),
    "capital_share",           # 5 categories
    code="600519",             # Optional 单股过滤
)
# columns: code, type, date, value_1, value_2, market, type_name
```

```python
# 健康检查 (Sprint 5)
from tdx_chronos.doctor import HealthDoctor
status = HealthDoctor.run_all()
# 8 项检查 · 3 级别 (healthy/degraded/unhealthy)
```

## v1.1 不做什么

- ❌ 多源验证 (sina/同花顺/tushare) — v2.0 预留
- ❌ 在线实时推送 — v2.0 预留
- ❌ HTTP 兜底 — v2.0 预留
- ❌ 修复 mootdx 4 个 bug — 主路径不触发，记入 vendor/UPGRADE_NOTES.md
- ❌ gpcw 财务领域解析 — Sprint 8 预留

## Sprint 7 核心成果

- **33 types 字段语义映射** (Sprint 6: 14 → Sprint 7: 33 · +19)
- **100% records 覆盖** (Sprint 6: 69% → Sprint 7: 100%)
- **zstd 压缩实验** (snappy → zstd3 节省 26.1%)
- **摸排脚本** (511 sample records · 5 大蓝筹 + 28 types)
- **测试 229 PASSED** (Sprint 1-7 累计)

## 文档

- **需求文档**: `requirements.md` · 唯一权威
- **Sprint 计划**: `docs/plans/`
- **Sprint 报告**: `logs/sprint{N}-report.md`
- **贡献指南**: `docs/CONTRIBUTING.md`

## 项目状态

| Sprint | 关键变更 | 日期 | 状态 |
|---|---|---|---|
| 0 | 项目初始化 + vendoring | 2026-07-03 | ✅ |
| 1 | mootdx Vendor + 4 bug 真相 | 2026-07-03 | ✅ |
| 2 | 抽象层 + 股本元数据 SQLite | 2026-07-04 | ✅ |
| 3-4 | 解析 + Parquet 输出 + 元数据 | 2026-07-04 | ✅ |
| 5 | cron 接入 + doctor + 飞书告警 | 2026-07-05 | ✅ |
| 6 | 股本 type 字段语义 (14 types) + gpcw bug 修复 | 2026-07-05 | ✅ |
| **7** | **未分类 28 types 语义 (33 types) + zstd 实验** | **2026-07-05** | **✅** |
| 8 | gpcw 财务领域 (预留) | TBD | ⏳ |

v1.1.0 · 38 commits · 229 PASSED · 7 Sprint · 3 验证里程碑

## License

MIT

---

Co-Authored-By: claw-cortex 🦞 <ariesy.bleiben@gmail.com>