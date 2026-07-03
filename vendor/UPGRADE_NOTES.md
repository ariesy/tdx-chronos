# vendor/UPGRADE_NOTES.md

> **mootdx 0.11.7 vendor 化记录** · 4 个已知 bug 状态：**已记录 · 不修**
> 详细来源：Phase 1 PoC `/home/ariesy/.openclaw/workspace/projects/tdx-poc/decision.md` §弱证据 #3-#6

## v1.1 主路径与 mootdx 关系

**v1.1 主路径 = 官方 .day 集中下载 + struct 解析**，不调 mootdx 任何函数。

| 触发模块 | 触发函数 | v1.1 是否触发 | 原因 |
|---|---|---|---|
| `TdxHq_API` socket | `do_heartbeat()` | ❌ 不触发 | cron 用 curl 不连 TdxHQ 行情服务 |
| `TdxHq_API` 多线程 | multithread | ❌ 不触发 | 同上 |
| `mootdx.Affair` | `fetch(filename=dict)` | ❌ 不触发 | 用 `sources/financial.py` 直接 struct 拆 264 字段 |
| `mootdx.financial` | `import mootdx.financial` | ❌ 不触发 | 同上，不 import 该模块 |

**结论**：4 bug 在 v1.1 主路径下 0 触发 → 修不修与 v1.1 输出质量无关 → **不修**

## 4 个 bug 详细记录

### Bug #3 · `heartbeat=True` + 多次请求 → 卡死
- **触发**：`TdxHq_API` socket 层 `do_heartbeat()` 函数
- **现象**：连接后多次请求时卡死
- **缓解**（已记入）：永远不用 `heartbeat=True`
- **v1.1 影响**：0（不调 TdxHq_API）

### Bug #4 · `multithread=True` + 多次请求 → 严重卡顿
- **触发**：`TdxHq_API` 多线程模式
- **现象**：严重卡顿
- **缓解**（已记入）：单线程已 30 ms/股，够用
- **v1.1 影响**：0（不调 TdxHq_API）

### Bug #5 · `Affair.fetch(filename=dict)` → TypeError
- **触发**：`mootdx.Affair` 财务下载类
- **现象**：参数类型错误
- **缓解**（已记入）：用 `f['filename']` 取出字符串
- **v1.1 影响**：0（用 `sources/financial.py` 替代）

### Bug #6 · `mootdx.financial/__init__.py` 是空文件
- **触发**：import 层
- **现象**：`import mootdx.financial` 失败
- **缓解**（已记入）：用 `from mootdx.financial.financial import ...`
- **v1.1 影响**：0（不 import mootdx.financial）

## 升级流程（v2.0 备用）

```bash
# 1. 拉新版本
pip download mootdx==NEW_VERSION -d vendor/mootdx/_pypi/

# 2. 重 vendor
python -m vendoring sync vendor/mootdx/

# 3. 单元测试
.venv/bin/pytest tests/unit/test_mootdx_vendor.py

# 4. 验 4 bug 是否在新版本修复
grep -E "heartbeat|multithread|Affair|financial.__init__" vendor/mootdx/mootdx/ -r
```

## 退出条件（什么时候换源）

| 信号 | 动作 |
|---|---|
| mootdx 上游重大协议变更 | 切到 v2.0 备用（sina/同花顺） |
| mootdx 4 bug 修复 → 升级 | 拉新版本重 vendor |
| mootdx 项目死亡 | 主人独自承担 · tdx-chronos 切到 v2.0 |
