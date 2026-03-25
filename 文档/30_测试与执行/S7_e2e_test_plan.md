# S7 端到端测试方案

> 日期：2026-03-18
> 依赖：S6 全部完成（precompute_offloading_inputs 已实现）
> 环境：Gurobi 13.0.1 学术版，Python venv
> **状态：✅ 全部完成（2026-03-18）**

---

## Test A — 退化路径（默认参数，全本地执行）✅ 已通过

### 目的

验证 feasible_ratio=0% 时（全部卸载候选超时），代码路径不崩。

### 流程

```python
from edge_uav.scenario_generator import EdgeUavScenarioGenerator
from edge_uav.model.precompute import (
    PrecomputeParams, make_initial_level2_snapshot,
    precompute_offloading_inputs,
)
from edge_uav.model.offloading import OffloadingModel
from config.config import configPara

config = configPara(None, None)
gen = EdgeUavScenarioGenerator()
scenario = gen.getScenarioInfo(config)

params = PrecomputeParams.from_config(config)
snap = make_initial_level2_snapshot(scenario)
result = precompute_offloading_inputs(scenario, params, snap)

model = OffloadingModel(
    tasks=scenario.tasks,
    uavs=scenario.uavs,
    time_list=scenario.time_slots,
    D_hat_local=result.D_hat_local,
    D_hat_offload=result.D_hat_offload,
    E_hat_comp=result.E_hat_comp,
    alpha=config.alpha,
    gamma_w=config.gamma_w,
)
feasible, cost = model.solveProblem()
outputs = model.getOutputs()
```

### 断言

| # | 断言 | 预期 | 实际结果 |
|---|------|------|---------|
| 1 | `feasible == True` | 全本地可行 | ✅ True |
| 2 | `cost > 0` | 有正成本 | ✅ 178.498 |
| 2.5 | `offload_feasible_ratio == 0` | 退化路径：无可卸载候选 | ✅ 0.0 |
| 3 | 无 KeyError | 索引完整 | ✅ |
| 4 | 每个 active task 在 `outputs[t]["local"]` | 全本地分配 | ✅ 86 个 |
| 5 | 所有 `outputs[t]["offload"][j]` 为空 | 无卸载 | ✅ 0 个 |

### 关键输出

```
Gurobi: 86 rows, 86 columns (全部 x_local，无 x_offload)
Optimal solution: obj=178.498, gap=0.0%
求解时间: 0.01s
```

---

## Test B — 卸载生效路径（放宽参数）✅ 已通过

### 目的

验证存在可卸载候选时，Level-1 实际选择卸载。

### 参数改动

在场景生成后直接覆盖 task 属性（不改 config，不改生成器）：

```python
# 放宽截止期 + 降低本地频率 → 卸载更优
for task in scenario.tasks.values():
    task.tau = 200.0       # 远大于 offload_delay（12~177s）
    task.f_local = 1e6     # 本地极慢 → D_local 极大 → 优化器倾向卸载
```

### 原理

- `tau=200.0`：使 `_offload_feasible()` 返回 True（offload_delay min=12.4s < 200）
- `f_local=1e6`：本地时延 D_local = F/f_local ≈ 1e8/1e6 = 100s，远大于近处 UAV 的卸载时延
- 目标函数 cost1 = D/tau：卸载归一化成本 < 本地归一化成本 → Gurobi 选卸载

### 断言

| # | 断言 | 预期 | 实际结果 |
|---|------|------|---------|
| 1 | `feasible_b == True` | 可行 | ✅ True |
| 2 | `diagnostics["offload_feasible_ratio"] > 0` | 有可卸载候选 | ✅ > 0 |
| 3 | 至少 1 个 task 出现在某个 `outputs_b[t]["offload"][j]` | 实际发生卸载 | ✅ |
| 4 | 被卸载的 (i,j,t)：`D_hat_offload[i][j][t] <= task.tau` | 仅卸载决策满足 deadline | ✅ |
| 5 | `cost_b < all_local_baseline` | 卸载降低了总成本 | ✅ |

> 注：断言 4 仅检查卸载决策的 deadline，本地执行在 L1 中无硬性 deadline 约束（Codex 审查确认）。

---

## Test C — 混合决策（部分本地 + 部分卸载）✅ 已通过（加固测试）

### 目的

验证 x_local 和 x_offload 可在同一求解中共存。

### 参数改动

```python
task_ids = sorted(scenario.tasks.keys())
mid = len(task_ids) // 2
for idx, i in enumerate(task_ids):
    scenario.tasks[i].tau = 200.0
    if idx < mid:
        scenario.tasks[i].f_local = 1e9   # 本地优（D_local 小）
    else:
        scenario.tasks[i].f_local = 1e6    # 卸载优（D_local 大）
```

### 断言

| # | 断言 | 实际结果 |
|---|------|---------|
| 1 | 求解可行 | ✅ |
| 2 | 本地决策 > 0 且卸载决策 > 0 | ✅ |
| 3 | 本地 + 卸载 == 总活跃对数 | ✅ |

---

## Test D — 能耗权重回退（alpha=0, gamma_w=1）✅ 已通过（加固测试）

### 目的

纯能耗目标下，本地无边缘能耗 → 全本地最优，验证目标函数权重机制。

### 参数改动

```python
# 与 Test B 相同的参数，但目标函数权重不同
alpha=0.0, gamma_w=1.0  # 传给 OffloadingModel
```

### 断言

| # | 断言 | 实际结果 |
|---|------|---------|
| 1 | 求解可行 | ✅ |
| 2 | 无卸载发生 | ✅ 0 个 |
| 3 | 目标值 ≈ 0 | ✅ cost ≈ 0.0 |

---

## 完成标准

- [x] Test A 全部断言通过（含退化路径原因断言）
- [x] Test B 全部 5 项断言通过
- [x] Test C 混合决策共存验证通过（加固）
- [x] Test D 能耗权重回退验证通过（加固）
- [x] 无 Gurobi 数值警告
- [x] `precompute.py` 中无剩余 `raise NotImplementedError`

### 测试文件

`tests/test_s7_offloading_e2e.py` — 245 行，4 个测试用例，44/44 全部通过（0.12s）

### 协作记录

| Agent | SESSION_ID | 贡献 |
|-------|-----------|------|
| Codex | `019cff2f-71c5-7a91-8d5f-844ddfd8f240` | Test B 参数验证、断言 4 范围修正、Test C 混合场景建议、code review |
| Gemini | `aff05d4d-b3a5-4e57-952e-a0fef5b50d76` | 执行计划制定、Test D 能耗权重场景建议 |
