# Phase⑥ Step4 方案A 最终实施计划

**状态**：🗂️ 历史实施计划（撰写时为 Phase 3 阅读验证中，后续已执行）
**更新**：2026-03-27
**目标**：快速验证BCD基础（2.5 小时）

> 说明：本文为 2026-03-27 的阶段性实施计划。后续提交 `3462563`、
> `b332502`、`7239a60` 已推进并记录 Phase⑥ Step4 状态，正文保留原计划语义。

---

## 📊 Context & Current State

**背景**：Phase⑥ Step3（SOCP实施）已完成，BCD框架和轨迹优化模块代码已写好。
现在需要通过最少改动，快速验证整个系统能否可运行。

**现状梳理**：
- ✅ **bcd_loop.py** (677行)：完整实现，包含 clone_snapshot, validate_offloading_outputs 等 5 个核心函数
- ✅ **trajectory_opt.py** (750行)：SOCP改写完成，10/12 测试通过
- ⚠️ **edge_uav/__init__.py**：存在但为空，pytest 无法导入 (ModuleNotFoundError)
- ⚠️ **conftest.py**：不存在，导致 pytest 直接运行失败

**关键发现**：
1. pytest 导入失败的真正原因：`pyproject.toml` 配置了 `package = false`，导致 pytest 直接执行时项目根目录不在 sys.path
2. **解决方案**：创建 `tests/conftest.py`，在 pytest 启动时注入项目路径
3. **其他文件**都完好，无需修改

---

## 🎯 方案A：快速验证BCD基础

### 分阶段实施（总计 2.5 小时）

#### **Phase 1：导入路径修复 (30 min)**

**Step 1.1：创建 `tests/conftest.py`（最小化改动）**

文件路径：`/Users/daisy/Desktop/llm-guided-mod-optimization/tests/conftest.py`（新建）

内容：
```python
"""Pytest configuration for edge_uav tests.

This conftest.py ensures the project root is in sys.path for test discovery,
allowing pytest and uv run pytest to both work correctly with package=false config.
"""

import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
```

**验证**：
```bash
cd /Users/daisy/Desktop/llm-guided-mod-optimization
uv run python -m pytest tests/test_bcd_loop.py --collect-only 2>&1 | head -20
# 预期：显示 8 项测试被收集（无 ImportError）
```

---

**Step 1.2：补充 `edge_uav/__init__.py`（可选，文档意义）**

文件路径：`/Users/daisy/Desktop/llm-guided-mod-optimization/edge_uav/__init__.py`（修改）

建议内容：
```python
"""Edge UAV 优化模块 — LLM 引导分层优化系统的 UAV 边缘计算子系统。

Submodules:
  - data: Core data classes (ComputeTask, UAV, EdgeUavScenario)
  - model: Solvers (propulsion, resource_alloc, trajectory_opt, bcd_loop)
  - scenario_generator: Scenario builder
  - evaluator: Solution evaluator
"""

__version__ = "0.1.0"
```

---

#### **Phase 2：单元测试验证 (45 min)**

**Step 2.1：BCD 单元测试** (15 min)

```bash
cd /Users/daisy/Desktop/llm-guided-mod-optimization
uv run python -m pytest tests/test_bcd_loop.py -v
```

**预期结果**：8/8 通过
- TestBCDDeepCopyIsolation (2 tests)
- TestBCDCostMonotonicity (1 test)
- TestBCDEarlyConvergence (1 test)
- TestBCDWarmStart (1 test)
- TestBCDRollbackLimit (2 tests)
- TestBCDIntegration (1 test placeholder)

**验收标准**：全部通过，无导入错误

---

**Step 2.2：Trajectory 单元测试** (15 min)

```bash
uv run python -m pytest tests/test_trajectory_opt.py -v
```

**预期结果**：12/12 通过（之前的 T1/T9 已修复）

**验收标准**：全部通过

---

**Step 2.3：综合单元测试** (15 min)

```bash
uv run python -m pytest tests/test_bcd_loop.py tests/test_trajectory_opt.py tests/test_resource_alloc.py tests/test_propulsion.py -v --tb=line
```

**预期结果**：40/40 通过（8+12+14+6）

**验收标准**：全部通过，无回归

---

#### **Phase 3：冒烟测试验证 (1.5 hours)**

**Step 3.1：准备最小化参数**

```bash
# 检查 LLM 配置
cat /Users/daisy/Desktop/llm-guided-mod-optimization/config/setting.cfg | grep -E "^(llmModel|api_endpoint)"

# 记录当前环境变量（作为基准）
echo "Current HS_POP_SIZE=${HS_POP_SIZE:-not set}"
echo "Current HS_ITERATION=${HS_ITERATION:-not set}"
```

---

**Step 3.2：执行冒烟测试**

```bash
cd /Users/daisy/Desktop/llm-guided-mod-optimization

# 方法A：环境变量覆盖（推荐）
export HS_POP_SIZE=1
export HS_ITERATION=1
export MAX_BCD_ITER=2
uv run python scripts/testEdgeUav.py

# 预期耗时：< 3 minutes
```

**预期输出特征**：
- ✅ Exit code = 0 (无异常)
- ✅ "[BCD Iteration 1/2]" — 第一次 BCD 循环执行
- ✅ "[Block A] Offloading decision"
- ✅ "[Block C] Resource allocation"
- ✅ "[Block D] Trajectory opt (SCA): convergence = True"
- ✅ "[BCD Iteration 2/2]" — 第二次 BCD 循环（收敛检查）
- ✅ 最后输出 "Cost = XXXX.X" 和 "Feasible = True"

**验收标准**：
| 检查项 | 标准 |
|-------|------|
| Python 无异常 | exit code = 0 |
| BCD 循环执行 | ≥ 2 次迭代完成 |
| 轨迹求解成功 | SCA 返回有效结果 |
| 成本单调性 | 成本非增 |
| 时间控制 | < 3 min |

---

#### **Phase 4：结果验收与诊断 (30 min)**

**Step 4.1：快速验收检查表**

```bash
# 检查 1：pytest 全部通过
pytest_pass=$(uv run python -m pytest tests/test_bcd_loop.py tests/test_trajectory_opt.py -q --tb=no 2>&1 | grep -c "passed")
echo "✓ Unit tests: $pytest_pass"

# 检查 2：冒烟输出包含关键字
smoke_log=$(mktemp)
cd /Users/daisy/Desktop/llm-guided-mod-optimization
HS_POP_SIZE=1 HS_ITERATION=1 uv run python scripts/testEdgeUav.py > "$smoke_log" 2>&1

echo "✓ Smoke test output:"
grep -E "(BCD Iteration|Converged|Cost =|Feasible)" "$smoke_log"

# 检查 3：是否生成结果目录
echo "✓ Result directory created:"
ls -d discussion/2026* 2>/dev/null | tail -1
```

---

**Step 4.2：已知问题快速处理**

| 问题 | 症状 | 修复 |
|------|------|------|
| pytest ImportError | "ModuleNotFoundError: edge_uav" | 确认 conftest.py 已创建且位置正确 |
| SOCP 求解器失败 | "solver_status = None" | 检查约束是否符合 DCP（这通常已在 Phase3 修复） |
| BCD 不收敛 | 迭代达上限但不显示收敛 | 放宽收敛容差 eps_bcd 或增加 MAX_BCD_ITER |
| 冒烟超时 (>3min) | 进程仍在运行 | 检查 LLM API 超时；减少 ITERATION 或增加 BCD timeout |

---

## ✅ 验收标准（必须全部满足）

1. ✅ conftest.py 创建成功
2. ✅ pytest 能收集所有测试（无导入错误）
3. ✅ BCD 单元测试 8/8 通过
4. ✅ Trajectory 单元测试 12/12 通过
5. ✅ 冒烟测试执行成功（exit code = 0）
6. ✅ BCD 循环至少执行 2 次迭代
7. ✅ 成本序列单调非增
8. ✅ 执行时间 < 3 分钟

---

## 📝 Critical Files to Modify/Create

| 文件 | 操作 | 改动量 | 用途 |
|------|------|--------|------|
| `tests/conftest.py` | 创建 | 10 行 | 修复 pytest 导入路径 |
| `edge_uav/__init__.py` | 修改 | 5 行（可选） | 补充模块文档字符串 |
| `edge_uav/model/bcd_loop.py` | 验证只读 | 0 | 确认完整实现 |
| `edge_uav/model/trajectory_opt.py` | 验证只读 | 0 | 确认 SOCP 正确 |
| `testEdgeUav.py` | 验证只读 | 0 | 检查入口点 |

---

## 🔗 Reuse Existing Implementation

- ✅ `bcd_loop.run_bcd_loop()` - 完整实现，无需修改
- ✅ `trajectory_opt.solve_trajectory_sca()` - SOCP 改写完成，无需修改
- ✅ `resource_alloc.solve_resource_allocation()` - 已验证可用
- ✅ `propulsion.solve_propulsion()` - 已验证可用
- ✅ `offloading.OffloadingModel.solveProblem()` - 现有集成点，暂不修改

---

## 📊 Expected Outcome

完成此方案后：
- **快速反馈**：2.5 小时内确认 BCD 系统可运行
- **高置信度**：20 个单元测试全通过 + 冒烟验证通过
- **低风险**：仅涉及 2 个文件创建/轻微修改，无核心逻辑改动
- **为后续做准备**：验证后可开始 Phase⑥ Step4 的 HS 集成（方案 B）

---

**计划创建日期**：2026-03-27
**目标执行日期**：2026-03-27 或 2026-03-28
**状态**：🗂️ 历史实施计划（该“待执行”状态仅对应计划撰写时）

