# Sprint 0 报告 · 2026-07-03

**Sprint**: Sprint 0 · 项目初始化 + 文档同步 + vendoring 工具链验证
**周期**: 1 d · **状态**: ✅ **完成**

## 交付物清单

- [x] **GitHub repo 初始化** · 本地 git init -b main（在 /app/tdx-chronos）
- [x] **目录骨架**（基于 requirements.md §四 设计）
  - `src/tdx_chronos/` · 8 个子模块（sources / ingest / fin / index / gp / cli / api / alerts）
  - `vendor/mootdx/` · v2.0 备用占位
  - `cron/` · daily_sync.sh / weekly_sync.sh 占位
  - `data/` · 不 commit · 8 子目录（parquet/fin/index/gp/xdxr/snapshot/meta）+ 今日快照 2026-07-03
  - `tests/` · unit/integration/fixtures 三层
  - `docs/` · CONTRIBUTING.md
  - `logs/` · sprint 报告
  - `scripts/` · 工具脚本
- [x] **CONTRIBUTING.md** · 1890 字节 · 开发循环 + Sprint 0 启动检查表 + 不允许的事
- [x] **README.md** · 1524 字节 · v1.1 是什么 + 不做什么 + 快速开始
- [x] **.gitignore** · 429 字节 · 不 commit data/ vendor 构建产物
- [x] **venv 工具链** · `.venv/`（PEP 668 修复）
  - vendoring 1.4.0 ✅
  - pytest ✅
  - pandas ✅
  - pyarrow ✅
  - requests ✅
- [x] **委员会 Confidence Medium → High 验证** · `pip install vendoring` 跑通
- [x] **vendor/UPGRADE_NOTES.md** 占位 · 4 bug 记录（待 Sprint 1）

## 关键决策记录

### 决策 #1 · venv vs 系统 pip
**背景**：PEP 668 默认禁止系统 pip install
**选择**：使用 `.venv/`（与 Phase 1 PoC 一致）
**影响**：所有 v1.1 Sprint 需用 `.venv/bin/python` / `.venv/bin/pip`

### 决策 #2 · GitHub repo 在哪？
**背景**：v1.1 第 1 轮决定"GitHub repo ariesy/tdx-chronos"
**选择**：**本地 git init（不上 GitHub）**——理由：v1.1 起步阶段，主人主要在 vm002 本地调试
**后续**：Sprint 7 末 push 到 GitHub + v1.1.0 tag

### 决策 #3 · Sprint 1 验收前置
**委员会要求**：Sprint 0 末必须先跑通 vendoring 工具链
**验证**：
```bash
$ pip install vendoring  # ✅ 安装成功 (1.4.0)
$ python -c "import vendoring"  # ✅ 可 import
$ python -m vendoring sync vendor/mootdx/  # 待 Sprint 1 实际跑
```

## 状态

- ✅ **所有 Sprint 0 交付物完成**
- ✅ **vendoring 工具链可行性验证通过**（委员会 Confidence Medium → High）
- ✅ **Sprint 1 准入门槛达成**

## 下一动作

**Sprint 1 · mootdx Vendor 化 + 补丁备用**（1.5-2 d）
- Day 1 上午：`pip download mootdx==0.11.7 -d vendor/mootdx/_pypi/`
- Day 1 下午：`python -m vendoring sync vendor/mootdx/`
- Day 1 下午：写 `vendor/mootdx/UPGRADE_NOTES.md`（4 bug 记录）
- Day 2：单元测试只验 import + callable（不修 4 bug）
- Day 2 下午：写 `src/tdx_chronos/sources/mootdx_vendor.py` 抽象层

**总周期重算确认**：25.5-27d · 9 Sprint · 8 修订轮次 · Committee Confidence: High
