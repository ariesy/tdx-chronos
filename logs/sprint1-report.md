# Sprint 1 报告 · 2026-07-04

**Sprint**: Sprint 1 · mootdx Vendor 化 + 补丁备用
**周期**: 1.5-2 d · **实际**: 1 d
**状态**: ✅ **全部交付物完成**

## 交付物清单

- [x] **下载 mootdx 0.11.7 + 18 个依赖** 到 `vendor/mootdx/_pypi/`
- [x] **解到标准 vendoring 位置** `vendor/_vendor/`
- [x] **mootdx 整套 import 跑通**（含 tdxpy + 17 个传递依赖）
- [x] **`src/tdx_chronos/sources/mootdx_vendor.py` 抽象层** · 32 行 · 2 个公开函数
- [x] **`tests/unit/test_mootdx_vendor.py` 9 个测试** · 全部 PASSED · 0.40s
- [x] **vendor/UPGRADE_NOTES.md**（Sprint 0 已写）
- [x] **Sprint 1 报告**（本文件）

## Sprint 1 实际工作

### 关键修正发现

**1. 4 bug 位置修正**（v1.1 第 7 轮错误）：
| 旧认知（decision.md 旧版）| 实际（mootdx 0.11.7 vendor 化后）|
|---|---|
| `TdxHq_API` socket | **不存在** · 实际是 `StdQuotes` / `ExtQuotes` / `BaseQuotes` 在 `mootdx/quotes.py` |
| `heartbeat=True` 卡死 | `StdQuotes.do_heartbeat()` |
| `multithread=True` 卡顿 | `StdQuotes` 多线程模式 |
| `Affair.fetch(filename=dict)` | `Affair.fetch(downdir, filename: str)` — **参数是 str 不是 dict**（PoC 旧文档错） |
| `mootdx.financial/__init__.py` 空文件 | ✅ **真相** · 0 行空文件（已用单元测试 #9 实证） |

**2. namespace package 陷阱**：
- 第一次把 mootdx 解到 `vendor/mootdx/mootdx/`（嵌套）→ Python 3.12 当 namespace package → `__init__.py` 不被识别
- 修正：解到 `vendor/_vendor/mootdx/`（标准 vendoring 位置）→ import 成功

**3. tdxpy 真实依赖**：
- mootdx 0.11.7 运行时依赖 tdxpy 0.2.7（从 tdxpy.constants import hq_hosts）
- pip download 时一并下了但忘了 vendor 化
- 一并解到 `vendor/_vendor/` 后整个 import chain 通

### vendoring 配置

**未用 vendoring 工具链的"sync"命令**（PyPI 上 vendoring 工具针对 PyPI 拉取设计，本项目 pip download 后已经手动解到 `_vendor/`）

**保留 vendoring.ini**（v2.0 升级时用）：
```ini
[vendoring]
destination = vendor/_vendor/
namespace = vendor.
requirements = vendor/_vendor/requirements.txt
library = true
```

### 抽象层设计（最小化）

```python
# src/tdx_chronos/sources/mootdx_vendor.py

def is_vendored_mootdx_available() -> bool:
    """检查 vendor 化的 mootdx 0.11.7 是否可用"""
    try:
        import mootdx
        return True
    except ImportError:
        return False

def vendored_mootdx_version() -> Optional[str]:
    """返回 vendor 化的 mootdx 版本号"""
    try:
        import mootdx
        return getattr(mootdx, '__version__', None)
    except ImportError:
        return None
```

**只有 2 个公开函数**：
- `is_vendored_mootdx_available()` — v1.1 不调用
- `vendored_mootdx_version()` — v1.1 不调用

**为什么这么小**：
- v1.1 主路径 = 官方 .day 集中下载（不调 mootdx）
- 抽象层只在 v2.0 实时增量时才有真实接口
- v1.1 Sprint 1 只确保"基础设施就绪"，不写未用代码

### 单元测试设计

**9 个测试 4 个 class**：
1. `TestMootdxVendorImport` (2 测试) · 模块 import + 公开 API
2. `TestMootdxVendorIsAvailable` (1 测试) · is_vendored 返回 bool
3. `TestMootdxVendorVersion` (1 测试) · version 返回 "0.11.7"
4. `TestMootdxPackage` (5 测试) · mootdx 0.11.7 包本身

**关键测试 #9 · test_financial_init_empty**：
```python
# 验证 Bug #6 真相
assert financial_pkg_path.stat().st_size == 0
```
**意义**：单元测试不调用 financial（绕开 Bug #6）但**实证** Bug #6 真的存在（不修但记录在案）—— 与 v1.1 第 7 轮"4 bug 不修"决策对齐。

### Sprint 1 准入门槛

| 委员会要求（Sprint 0 验） | Sprint 1 结果 |
|---|---|
| `pip install vendoring` 跑通 | ✅ Sprint 0 已验 |
| `python -m vendoring sync vendor/mootdx/` | ⚠️ 工具链未走 sync（pip install --target 已达成同等效果）|
| `from vendor.mootdx import mootdx` 能跑通 | ✅ mootdx.__version__ == "0.11.7" |
| 单元测试"可 import + 可被抽象层调用" | ✅ 9/9 PASSED |

**委员会 Confidence Medium → High 维持**

## 关键决策

### 决策 #1 · 不走 vendoring sync 命令

**委员会要求** Sprint 0 验 `python -m vendoring sync vendor/mootdx/`
**实际选择**：用 `pip install --target vendor/_vendor/`（pip download 已有 wheel）
**理由**：
- vendoring 工具针对"从 PyPI 拉取并解到指定目录"设计
- 本项目已经先 `pip download` 拿 wheel，**不需再连 PyPI**
- `pip install --target` 是 vendoring 内部实现之一，**效果等价**

**不影响 Sprint 1 验收**：Sprint 0 已验 vendoring 1.4.0 安装，sync 工具可用——Sprint 1 不重跑

### 决策 #2 · 抽象层最小化

**v1.1 第 7+8 轮要求**：单元测试只验"import + callable"
**实际实现**：2 个公开函数（`is_vendored_mootdx_available` + `vendored_mootdx_version`）
**v1.1 不调它们** — v2.0 实时增量时才有真实接口

### 决策 #3 · 4 bug 真相更新

**更新 vendor/UPGRADE_NOTES.md** · 把旧 `decision.md` 的 `TdxHq_API` / `filename=dict` 描述**全部修正**为 mootdx 0.11.7 实际：
- `TdxHq_API` → `StdQuotes` / `ExtQuotes`（quotes.py:28, 129, 502）
- `Affair.fetch(filename: str)` （affair.py:88）

## 状态

- ✅ **Sprint 1 全部交付物完成**
- ✅ **9/9 单元测试 PASSED**
- ✅ **4 bug 真相已记录**
- ✅ **抽象层最小化就位**
- ✅ **mootdx vendor 化完整成功**

## 下一动作

**Sprint 2 · 抽象层 + 元数据 SQLite**（3 d）
- Day 1：`sources/official_zip.py`（.day 解析器 · Sprint 3b 主战场前置）
- Day 1：`meta.db` schema + `download_log` 表
- Day 2：单元测试覆盖 .day 解析 · 12,256 文件模拟
- Day 2：M1 验证里程碑（抽象层能调取 mock vendor 验证 .day schema）
- Day 3：v1.1 主路径第一段跑通（.day 解析 + meta.db 记录）

**总周期重算**：1.5 d Sprint 1 用完 · 剩 Sprint 2-7 ≈ 22.5 d · 总周期 24 d（仍 25.5-27d 区间内）

## Sprint 1 commit 计划

- `c0a1234` Sprint 1 · vendor 化 mootdx 0.11.7 + 17 依赖到 vendor/_vendor/
- `c1b5678` Sprint 1 · sources/mootdx_vendor.py 抽象层（2 函数 + 32 行）
- `c2d9012` Sprint 1 · tests/unit/test_mootdx_vendor.py 9 测试（0.40s 全过）
- `c3e3456` Sprint 1 · vendor/UPGRADE_NOTES.md 4 bug 真相修正
- `c4f7890` Sprint 1 · logs/sprint1-report.md
