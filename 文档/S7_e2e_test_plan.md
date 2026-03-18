# S7 端到端测试方案

> 日期：2026-03-18
> 依赖：S6 全部完成（precompute_offloading_inputs 已实现）
> 环境：Gurobi 13.0.1 学术版，Python venv

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

## Test B — 卸载生效路径（放宽参数）⬜ 待执行

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

### 流程

```python
# 复用 Test A 的 config/gen/scenario
for task in scenario.tasks.values():
    task.tau = 200.0
    task.f_local = 1e6

# 重新预计算（tau 和 f_local 变了）
snap_b = make_initial_level2_snapshot(scenario)
result_b = precompute_offloading_inputs(scenario, params, snap_b)

model_b = OffloadingModel(
    tasks=scenario.tasks,
    uavs=scenario.uavs,
    time_list=scenario.time_slots,
    D_hat_local=result_b.D_hat_local,
    D_hat_offload=result_b.D_hat_offload,
    E_hat_comp=result_b.E_hat_comp,
    alpha=config.alpha,
    gamma_w=config.gamma_w,
)
feasible_b, cost_b = model_b.solveProblem()
outputs_b = model_b.getOutputs()
```

### 断言

| # | 断言 | 预期 |
|---|------|------|
| 1 | `feasible_b == True` | 可行 |
| 2 | `result_b.diagnostics["offload_feasible_ratio"] > 0` | 有可卸载候选 |
| 3 | 至少 1 个 task 出现在某个 `outputs_b[t]["offload"][j]` | 实际发生卸载 |
| 4 | 被卸载的 (i,j,t)：`D_hat_offload[i][j][t] <= task.tau` | L1-C2 约束成立 |
| 5 | `cost_b < cost_a_equiv`（同 tau 下对比） | 卸载降低了总成本 |

### Codex 验证结论

- 全不可卸载时 `x_local + 0 == 1` → 可行（Test A 原理）
- `getOutputs()` 全本地时正常返回
- 放宽 tau 让 `_offload_feasible()` 通过；降低 f_local 让卸载成本 < 本地 → 优化器选卸载
- Codex SESSION_ID: `019cff2f-71c5-7a91-8d5f-844ddfd8f240`

---

## 完成标准

- [ ] Test A 全部 5 项断言通过 ← ✅ 已通过
- [ ] Test B 全部 5 项断言通过
- [ ] 无 Gurobi 数值警告
- [ ] `precompute.py` 中无剩余 `raise NotImplementedError`
