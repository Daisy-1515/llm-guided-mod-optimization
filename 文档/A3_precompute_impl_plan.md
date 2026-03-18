# A3 预计算模块实现计划

> 日期：2026-03-18
> 目标文件：`edge_uav/model/precompute.py`
> 依赖文档：`文档/precompute_analysis.md` §7（A2 接口设计）
> 上游：`edge_uav/data.py`、`config/config.py`
> 下游：`edge_uav/model/offloading.py`（OffloadingModel）

---

## 进度总览（2026-03-18 更新）

| 步骤 | 内容 | 函数数 | 状态 |
|------|------|--------|------|
| S1 | 骨架 + `from_config` | 13 签名 + 1 实现 | ✅ 完成 |
| S2 | 物理纯函数 | 5 | ✅ 完成 |
| S3 | 初始化 Helper | 2 | ✅ 完成 |
| S4 | `Level2Snapshot.validate` | 1 | ✅ 完成 |
| S5 | `make_initial_level2_snapshot` | 1 | ⬜ 待实现 |
| S6 | `precompute_offloading_inputs` + 诊断 | 3 | ⬜ 待实现 |
| S7 | 端到端测试 + Level-1 联调 | — | ⬜ 待开始 |

**已实现 9/13 函数，剩余 4 个 + 测试。**

## 依赖关系总览

```
S1（骨架）           ✅
 ├── S2（物理纯函数）    ✅ ──┐
 ├── S3（初始化 Helper）  ✅ ──┼── Phase 1 全部完成
 └── S4（validate）       ✅ ──┘
                                ↓
                           S5（make_initial_level2_snapshot）  ⬜ ← 下一步
                                ↓
                           S6（precompute_offloading_inputs + 诊断）  ⬜
                                ↓
                           S7（端到端测试 + Level-1 联调）  ⬜
```

**当前位置**：Phase 1 全部完成，进入 Phase 2（S5）

---

## S1 — 骨架搭建 ✅

### 目标

创建 `edge_uav/model/precompute.py`，包含全部类型定义和函数签名，函数体均为 `raise NotImplementedError`。
`PrecomputeParams.from_config` 已实现（Codex 协作，16/16 验收通过）。

### 输入

- A2 接口设计（`precompute_analysis.md` §7.2–§7.5）

### 交付物

`edge_uav/model/precompute.py` 包含：

```
# 类型别名（§7.2）
Scalar2D    = dict[int, dict[int, float]]
Scalar3D    = dict[int, dict[int, dict[int, float]]]
Trajectory2D = dict[int, dict[int, tuple[float, float]]]
Level2Source = Literal["init", "prev_bcd", "history_avg", "custom"]
InitPolicy   = Literal["paper_default", "custom"]

# 数据结构（§7.3）
@dataclass(frozen=True) PrecomputeParams   — 8 物理参数 + 5 数值保护 + from_config()
@dataclass(frozen=True) Level2Snapshot     — q, f_edge, f_local_override, source + validate()
@dataclass(frozen=True) PrecomputeResult   — D_hat_local, D_hat_offload, E_hat_comp, diagnostics

# 公开 API（§7.4）
make_initial_level2_snapshot()
precompute_offloading_inputs()

# 私有 Helper — 初始化（§7.5.1）
_init_trajectory_linear()
_init_frequency_uniform()

# 私有 Helper — 物理计算（§7.5.2）
_channel_gain()
_rate_from_gain()
_local_delay()
_offload_delay()
_edge_energy()

# 私有 Helper — 诊断（§7.5.3）
_finite_stats()
_build_diagnostics()
```

### 验收标准

```bash
cd E:/desktop/llm-guided-mod-optimization
python -c "from edge_uav.model.precompute import PrecomputeParams, Level2Snapshot, PrecomputeResult, make_initial_level2_snapshot, precompute_offloading_inputs; print('OK')"
```

输出 `OK`，无 ImportError。

---

## S2 — 物理计算纯函数（5 个） ✅

### 目标

实现 5 个无状态物理计算函数，每个函数输入标量、输出标量。

### 依赖

- S1 骨架（函数签名已存在）

### 函数清单

| 函数 | 公式 | 关键边界处理 |
|------|------|------------|
| `_channel_gain(pos_i, q_jt, *, H, rho_0, eps_dist_sq)` | g = ρ₀ / max(H² + ‖pos_i − q_jt‖², eps) | eps_dist_sq 防 g→∞ |
| `_rate_from_gain(gain, *, bandwidth, tx_power, noise_power, eps_rate)` | r = B · log1p(P·g/N₀) / ln(2) | log1p 精度；r < eps_rate 时兜底 |
| `_local_delay(workload, freq, *, eps_freq, big_m_delay)` | D = F / max(f, eps_freq) | f < eps_freq → big_m_delay |
| `_offload_delay(*, D_l, D_r, workload, r_up, r_down, f_edge, eps_rate, eps_freq, big_m_delay)` | T_up + T_comp + T_down | 总和 > big_m → 封顶 |
| `_edge_energy(*, gamma_j, f_edge, workload, eps_freq, big_m_delay)` | E = γ · f² · F | f < eps_freq → 0.0 |

### 实现要点

1. **全部纯函数**，无副作用，不访问 self 或全局状态
2. `_rate_from_gain` 使用 `math.log1p(snr) / math.log(2)` 而非 `math.log2(1 + snr)`
3. guard hit 不在这些函数内计数，由调用方（S6 主循环）判断并累计
4. `_offload_delay` 的三段：`T_up = D_l / r_up`、`T_comp = workload / f_edge`、`T_down = D_r / r_down`

### 验收标准

为每个函数编写独立单元测试，覆盖：

| 测试场景 | 预期 |
|---------|------|
| 正常值（手算对照） | 误差 < 1e-9 |
| 极近距离（pos_i ≈ q_jt） | gain 被 eps 兜底，不爆 inf |
| 零频率 | local_delay → big_m；energy → 0.0 |
| 零速率 | offload_delay → big_m |
| 超大时延 | 封顶 big_m_delay |

### 手算参考值

```python
# _channel_gain 参考
# pos_i=(200,300), q_jt=(500,500), H=100
# dist_sq = (500-200)^2 + (500-300)^2 = 90000+40000 = 130000
# denom = H^2 + dist_sq = 10000 + 130000 = 140000
# g = rho_0 / denom = 1e-5 / 140000 = 7.142857e-11

# _rate_from_gain 参考（上行）
# B_up=1e6, P_i=0.5, g=7.142857e-11, N_0=1e-10
# SNR = 0.5 * 7.142857e-11 / 1e-10 = 0.357143
# r = 1e6 * log1p(0.357143) / ln(2) = 1e6 * 0.30538 / 0.69315 = 440,691 bps
```

---

## S3 — 初始化 Helper（2 个） ✅

### 目标

实现首次迭代（k=0）的 Level-2 默认值生成。

### 依赖

- S1 骨架（函数签名已存在）
- `edge_uav/data.py`（EdgeUavScenario, UAV, ComputeTask 的属性）

### 函数清单

#### `_init_trajectory_linear(scenario) -> Trajectory2D`

```
对每架 UAV j，对每个时隙 t ∈ [0, T-1]:
    ratio = t / (T-1)    if T > 1 else 0.0
    q[j][t] = (
        uav.pos[0] + ratio * (uav.pos_final[0] - uav.pos[0]),
        uav.pos[1] + ratio * (uav.pos_final[1] - uav.pos[1]),
    )
```

- 当 `pos == pos_final`（depot 出发返回同一点），退化为全时隙停 depot — 这是预期行为
- T=1 时 ratio=0，停在起点

#### `_init_frequency_uniform(scenario) -> Scalar3D`

```
n_tasks = len(scenario.tasks)
对每架 UAV j，对每个任务 i，对每个时隙 t:
    f_edge[j][i][t] = uav.f_max / n_tasks
```

- **必须 dense**：覆盖全部 (j, i, t) 组合，即使任务在该时隙不 active
- 原因：precompute 需要为所有候选对计算 D_hat_offload

### 验收标准

```python
# 用默认参数场景（3 UAV × 10 task × 20 slot）
scenario = EdgeUavScenarioGenerator(config).generate()

q = _init_trajectory_linear(scenario)
assert len(q) == 3                      # 3 UAV
assert len(q[0]) == 20                  # 20 时隙
assert q[0][0] == scenario.uavs[0].pos  # t=0 在起点
assert q[0][19] == scenario.uavs[0].pos_final  # t=T-1 在终点

f = _init_frequency_uniform(scenario)
assert len(f) == 3                      # 3 UAV
assert len(f[0]) == 10                  # 10 task
assert len(f[0][0]) == 20              # 20 时隙
expected_f = scenario.uavs[0].f_max / 10
assert f[0][0][0] == expected_f
```

---

## S4 — Level2Snapshot.validate() ✅

### 目标

实现快照校验方法，累积所有错误一次性 raise。

### 依赖

- S1 骨架（Level2Snapshot dataclass 已定义）
- `edge_uav/data.py`（EdgeUavScenario 的结构）

### 检查项

| 序号 | 检查内容 | 错误消息模板 |
|------|---------|------------|
| 1 | q 覆盖所有 (j, t) ∈ uavs × time_slots | `"q missing key (j={j}, t={t})"` |
| 2 | f_edge 覆盖所有 (j, i, t)（require_dense=True） | `"f_edge missing key (j={j}, i={i}, t={t})"` |
| 3 | 所有频率值 > 0 | `"f_edge[{j}][{i}][{t}] = {v} <= 0"` |
| 4 | 位置在地图边界内（meta 有 x_max/y_max 时） | `"q[{j}][{t}] = {pos} out of bounds"` |
| 5 | f_local_override 非 None 时覆盖所有 (i, t) | `"f_local_override missing (i={i}, t={t})"` |

### 实现模式

```python
def validate(self, scenario, *, require_dense=True):
    errors: list[str] = []
    # ... 逐项检查，errors.append(...)
    if errors:
        raise ValueError(
            f"Level2Snapshot validation failed ({len(errors)} errors):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
```

### 验收标准

| 测试 | 输入 | 预期 |
|------|------|------|
| 合法快照 | S3 生成的 snapshot | 无异常 |
| 缺 q key | 删除 q[0][5] | ValueError 含 `"q missing key (j=0, t=5)"` |
| 负频率 | f_edge[0][0][0] = -1.0 | ValueError 含 `"<= 0"` |
| 越界位置 | q[0][0] = (-10, 500) | ValueError 含 `"out of bounds"` |
| 多错误累积 | 同时缺 key + 负频率 | ValueError 包含 ≥2 条消息 |

---

## S5 — make_initial_level2_snapshot()

### 目标

接线公开 API，组装 S3 + S4 的结果。

### 依赖

- S3（_init_trajectory_linear, _init_frequency_uniform）
- S4（Level2Snapshot.validate）

### 实现

```python
def make_initial_level2_snapshot(scenario, *, policy="paper_default"):
    if policy == "paper_default":
        q = _init_trajectory_linear(scenario)
        f_edge = _init_frequency_uniform(scenario)
    else:
        raise ValueError(f"Unsupported init policy: {policy!r}")

    snap = Level2Snapshot(q=q, f_edge=f_edge, source="init")
    snap.validate(scenario)
    return snap
```

### 验收标准

```python
from edge_uav.scenario_generator import EdgeUavScenarioGenerator
from config.config import configPara

config = configPara("config/setting.cfg", ".env")
config.getConfigInfo()
scenario = EdgeUavScenarioGenerator(config).generate()

snap = make_initial_level2_snapshot(scenario)
assert snap.source == "init"
assert isinstance(snap.q, dict)
assert isinstance(snap.f_edge, dict)
# validate 已在内部调用，到此无异常即通过
```

---

## S6 — precompute_offloading_inputs() + 诊断

### 目标

实现核心预计算主函数和诊断输出。

### 依赖

- S2（5 个物理纯函数）
- S5（Level2Snapshot 已可生成）

### 主循环伪代码

```
初始化:
    guard_hits = {rate_floor: 0, freq_floor: 0, big_m_cap: 0, tau_tol_borderline: 0}
    D_hat_local = {}, D_hat_offload = {}, E_hat_comp = {}
    uplink_rates = [], downlink_rates = []
    deadline_feasible_pairs = 0

Step 1 — 本地时延:
    for i in tasks:
        D_hat_local[i] = {}
        for t in time_slots:
            if active_only and not task.active[t]: continue
            workload = mu[i][t] if mu else task.F
            freq = snapshot.f_local_override[i][t] if override else task.f_local
            D_hat_local[i][t] = _local_delay(workload, freq, ...)

Step 2 — 卸载时延 + 能耗:
    for i in tasks:
        D_hat_offload[i] = {}
        for j in uavs:
            D_hat_offload[i][j] = {}
            E_hat_comp.setdefault(j, {}).setdefault(i, {})
            for t in time_slots:
                if active_only and not task.active[t]: continue

                # 信道增益（局部复用）
                g = _channel_gain(task.pos, snapshot.q[j][t], ...)

                # 上行速率
                r_up = _rate_from_gain(g, bandwidth=B_up, tx_power=P_i, ...)
                if r_up <= eps_rate: guard_hits["rate_floor"] += 1
                uplink_rates.append(r_up)

                # 下行速率
                r_down = _rate_from_gain(g, bandwidth=B_down, tx_power=P_j, ...)
                if r_down <= eps_rate: guard_hits["rate_floor"] += 1
                downlink_rates.append(r_down)

                # 卸载时延
                workload = mu[i][t] if mu else task.F
                f_e = snapshot.f_edge[j][i][t]
                d = _offload_delay(D_l=task.D_l, D_r=task.D_r, workload=workload,
                                   r_up=r_up, r_down=r_down, f_edge=f_e, ...)
                D_hat_offload[i][j][t] = d

                # 能耗（注意索引 [j][i][t]）
                E_hat_comp[j][i][t] = _edge_energy(gamma_j=..., f_edge=f_e, workload=workload, ...)

                # 可行性统计
                if d <= task.tau + tau_tol:
                    deadline_feasible_pairs += 1

Step 3 — 诊断:
    diagnostics = _build_diagnostics(...)
```

### _finite_stats() 实现

```python
def _finite_stats(values):
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        return {"min": None, "max": None, "mean": None, "count": 0}
    return {
        "min": min(finite),
        "max": max(finite),
        "mean": sum(finite) / len(finite),
        "count": len(finite),
    }
```

### _build_diagnostics() 输出字段

完整字段规格见 `precompute_analysis.md` §7.6，此处列核心：

```python
{
    "snapshot_source": str,
    "active_task_slots": int,
    "candidate_offload_pairs": int,
    "deadline_feasible_pairs": int,
    "offload_feasible_ratio": float,
    "local_delay_stats": {...},
    "offload_delay_stats": {...},
    "edge_energy_stats": {...},
    "uplink_rate_stats": {...},
    "downlink_rate_stats": {...},
    "guard_hits": {...},
    "tasks_all_uavs_infeasible": [...],
    "tasks_local_over_tau": [...],
}
```

### 验收标准

```python
params = PrecomputeParams.from_config(config)
snap = make_initial_level2_snapshot(scenario)
result = precompute_offloading_inputs(scenario, params, snap)

# 1. 维度完整性
for i in scenario.tasks:
    for t in scenario.time_slots:
        if scenario.tasks[i].active[t]:
            assert t in result.D_hat_local[i]
            for j in scenario.uavs:
                assert t in result.D_hat_offload[i][j]
                assert t in result.E_hat_comp[j][i]

# 2. 值域合理性
for i in result.D_hat_local:
    for t in result.D_hat_local[i]:
        assert 0 < result.D_hat_local[i][t] <= 1e6

# 3. 诊断完整性
diag = result.diagnostics
assert "offload_feasible_ratio" in diag
assert 0.0 <= diag["offload_feasible_ratio"] <= 1.0
assert diag["snapshot_source"] == "init"

# 4. 默认参数下 feasible_ratio 约 5%~15%（tau 偏紧）
assert diag["offload_feasible_ratio"] < 0.25
```

---

## S7 — 端到端测试 + Level-1 联调

### 目标

验证 precompute 输出能正确驱动 OffloadingModel 求解。

### 依赖

- S6（precompute 完整可用）
- Gurobi 已安装且可导入

### 测试流程

```python
from edge_uav.scenario_generator import EdgeUavScenarioGenerator
from edge_uav.model.precompute import (
    PrecomputeParams, make_initial_level2_snapshot,
    precompute_offloading_inputs,
)
from edge_uav.model.offloading import OffloadingModel
from config.config import configPara

# 1. 场景生成
config = configPara("config/setting.cfg", ".env")
config.getConfigInfo()
gen = EdgeUavScenarioGenerator(config)
scenario = gen.generate()

# 2. 预计算
params = PrecomputeParams.from_config(config)
snap = make_initial_level2_snapshot(scenario)
result = precompute_offloading_inputs(scenario, params, snap)

# 3. 打印诊断
import json
print(json.dumps(result.diagnostics, indent=2, default=str))

# 4. Level-1 求解
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

# 5. 验收
assert feasible, "Model should be feasible"
assert cost > 0, "Cost should be positive"
outputs = model.getOutputs()
assert len(outputs) > 0, "Should have outputs for at least one time slot"
```

### 检查清单

- [ ] 无 KeyError（索引覆盖完整）
- [ ] 无 Gurobi 数值警告（系数跨度合理）
- [ ] status = OPTIMAL 或 feasible
- [ ] `getOutputs()` 中每个 active 任务分配到恰好一个目标
- [ ] 卸载到 UAV 的任务 D_hat_offload ≤ tau（L1-C2 满足）

---

## 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 默认参数 tau 偏紧（~90% 不可行） | Level-1 几乎全部本地执行，解虽可行但意义有限 | S7 联调时观察 feasible_ratio；必要时临时调 `tau_max=5.0` 验证 |
| pos == pos_final == depot | 初始轨迹退化为全时隙停 depot，远处任务不可达 | MVP 接受；接口保留 policy 参数扩展 kmeans_hover |
| Gurobi 未安装 / 无 license | S7 无法执行 | S1-S6 不依赖 Gurobi；S7 前先 `python -c "import gurobipy"` 检查 |
| config 未加载 setting.cfg | from_config 取到默认值 | 测试中显式调用 `config.getConfigInfo()` |

---

## 并行分工建议

| Agent | Phase | 任务 | 状态 |
|-------|-------|------|------|
| Claude+Codex | Phase 0 | S1 骨架 + from_config | ✅ 完成 |
| 用户 | Phase 1 | S2 物理纯函数 | ✅ 完成 |
| 用户 | Phase 1 | S3 初始化 Helper | ✅ 完成 |
| 用户 | Phase 1 | S4 validate | ✅ 完成 |
| — | Phase 2 | S5 接线 | ⬜ 待实现 |
| — | Phase 3 | S6 主函数 + 诊断 | ⬜ 待实现 |
| — | Phase 4 | S7 端到端联调 | ⬜ 待开始 |

**关键路径**：~~S1 → S2 → S6 → S7~~ → 当前：S5 → S6 → S7
