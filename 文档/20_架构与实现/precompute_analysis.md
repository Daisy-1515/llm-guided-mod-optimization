# A1 预计算模块输入需求分析

> 日期：2026-03-17
> 分析方法：Claude 代码阅读 + Codex 验证 + Gemini 交叉审查
> 关联代码：`edge_uav/model/offloading.py`、`edge_uav/data.py`、`config/config.py`

---

## 1. Level-1 BLP 需要的三个预计算量

`OffloadingModel.__init__` 接收三个预计算字典，作为 BLP 的常量输入：

### 1.1 D_hat_local[i][t] — 本地执行时延（秒）

$$D_{i,i}^t = \frac{F_i}{f_i^{\text{local}}}$$

- **含义**：任务 i 在终端本地执行的总时延
- **输入**：`task.F`（CPU 周期数）、`task.f_local`（本地 CPU 频率）
- **特点**：当前实现中与时隙 t 无关（任务属性固定），按 `[i][t]` 索引仅为统一接口
- **数据来源**：完全来自 `EdgeUavScenario.tasks`

### 1.2 D_hat_offload[i][j][t] — 远程卸载总时延（秒）

$$D_{i,j}^t = T_{i,j}^{\text{up},t} + T_{i,j}^{\text{comp},t} + T_{i,j}^{\text{down},t}$$

三段串行：

| 阶段 | 公式 | 含义 |
|------|------|------|
| 上行 | $T_{i,j}^{\text{up},t} = D_l^i / r_{i,j}^t$ | 终端→UAV 上传原始数据 |
| 计算 | $T_{i,j}^{\text{comp},t} = F_i / f_{j,i}^t$ | UAV 边缘执行 |
| 下行 | $T_{i,j}^{\text{down},t} = D_r^i / r_{j,i}^{\text{down},t}$ | UAV→终端 回传结果 |

其中传输速率依赖信道增益：

$$g_{i,j}^t = \frac{\rho_0}{H^2 + \|\mathbf{pos}_i - \mathbf{q}_j^t\|^2}$$

$$r_{i,j}^t = B_{\text{up}} \cdot \log_2\!\left(1 + \frac{P_i \cdot g_{i,j}^t}{N_0}\right)$$

$$r_{j,i}^{\text{down},t} = B_{\text{down}} \cdot \log_2\!\left(1 + \frac{P_j \cdot g_{i,j}^t}{N_0}\right)$$

- **数据来源**：场景数据（`task.D_l, task.D_r, task.F, task.pos`）+ 配置（`H, B_up, B_down, P_i, P_j, N_0, rho_0`）+ **Level-2 输出**（`q_j^t, f_{j,i}^t`）

### 1.3 E_hat_comp[j][i][t] — 边缘计算能耗（焦耳）

$$E_{j,i}^{\text{comp},t} = \gamma_j \cdot (f_{j,i}^t)^2 \cdot F_i$$

- **含义**：UAV j 为任务 i 执行计算所消耗的能量
- **数据来源**：配置（`gamma_j`）+ 场景（`task.F`）+ **Level-2 输出**（`f_{j,i}^t`）

### 1.4 在 OffloadingModel 中的使用方式

| 用途 | 使用的量 | 代码位置 |
|------|---------|---------|
| 变量创建过滤（L1-C2） | `D_hat_offload[i][j][t] <= task.tau` | `_offload_feasible()` :195 |
| 目标函数 cost1（归一化时延） | `D_hat_local / tau`、`D_hat_offload / tau` | `default_dynamic_obj_func()` :309-323 |
| 目标函数 cost2（归一化能耗） | `E_hat_comp / uav.E_max` | `default_dynamic_obj_func()` :326-333 |
| LLM 动态目标 | 三个量均可由 `self.*` 访问 | `dynamic_obj_func(self)` |

---

## 2. 完整输入依赖链

```
                    ┌── 场景 EdgeUavScenario ──┐
                    │  tasks: pos, D_l, D_r,   │
                    │         F, tau, active,   │
                    │         f_local           │
                    │  uavs: pos, E_max, f_max  │
                    │  time_slots, meta         │
                    └────────────┬──────────────┘
                                 │
┌── 配置 configPara ────────┐    │    ┌── Level-2 输出 ─────────┐
│  H, B_up, B_down,        │    │    │  q[j][t]: UAV 2D 位置   │
│  P_i, P_j, N_0, rho_0,  ├────┼────┤  f_edge[j][i][t]: 频率  │
│  gamma_j                  │    │    │  (首次迭代需默认值)      │
└───────────────────────────┘    │    └──────────────────────────┘
                                 ↓
                      ┌── 预计算模块 ──┐
                      │  D_hat_local   │
                      │  D_hat_offload │
                      │  E_hat_comp    │
                      │  diagnostics   │
                      └───────┬────────┘
                              ↓
                     OffloadingModel (L1 BLP)
```

### 2.1 依赖缺口

**缺口 1**：`scenario.meta` 只存了 `T, delta, x_max, y_max, H, depot_pos, active_mode`，不包含通信参数（`B_up, P_i, N_0, rho_0` 等）。预计算模块必须同时接收 `scenario` 和 `config`。

**缺口 2**：`f_edge[j][i][t]` 必须是 **dense**（覆盖所有候选 `(j,i,t)` 对），不能只有"上一轮实际被分配到 UAV j 的任务"。因为当前轮 Level-1 需要评估所有候选对来做决策。

---

## 3. 理论模型 vs 代码特化差异

以下差异为合理的工程简化，不影响模型正确性，**不需要在论文中说明**。论文按通用形式写，代码实现中特化。

### 3.1 μ_i^t（时变工作量） vs task.F（固定）

| 维度 | 理论模型 | 代码实现 |
|------|---------|---------|
| 符号 | μ_i^t | task.F |
| 含义 | 任务 i 在时隙 t 的计算量，可随时隙变化 | 任务 i 的总计算量，生成时固定 |
| 维度 | 二维 (i, t) | 一维 (i) |
| 出处 | 公式.md 公式 (12): D = μ_i^t / f_i^t | data.py:44: self.F = F |
| 特化理由 | 当前场景中一个任务 = 一个固定计算请求（如图像识别），工作量不随时隙变化 |
| 接口预留 | 预计算模块接受可选 `mu[i][t]` 参数，默认回退 `task.F` |

### 3.2 f_i^t（可优化本地频率） vs task.f_local（固定）

| 维度 | 理论模型 | 代码实现 |
|------|---------|---------|
| 符号 | f_i^t | task.f_local |
| 含义 | 终端 i 在时隙 t 的本地 CPU 频率，Level-2 可优化 | 终端固定硬件频率，默认 1 GHz |
| 维度 | 二维 (i, t)，连续决策变量 | 标量，常数 |
| 出处 | 公式.md 公式 (12) | data.py:47: self.f_local = f_local |
| 特化理由 | 优化重点在 UAV 侧（轨迹 + 边缘频率），终端频率为固定硬件能力 |
| 接口预留 | 预计算模块接受可选 `f_local_override[i][t]` 参数，默认回退 `task.f_local` |

### 3.3 时隙索引 1..T vs 0..T-1

| 维度 | 论文公式 | 代码实现 |
|------|---------|---------|
| 范围 | t = 1, 2, ..., T | t = 0, 1, ..., T-1 |
| 惯例 | 数学下标从 1 开始 | Python 索引从 0 开始 |
| 直线插值 | q = q_I + (t-1)/(T-1) * (q_F - q_I) | q = q_I + t/(T-1) * (q_F - q_I) |
| 影响 | 初始化轨迹公式落地时需索引平移 |

**代码实现时的转换规则**：

```python
# 论文: q_j^t = q_I + (t-1)/(T-1) * (q_F - q_I),  t ∈ {1, ..., T}
# 代码: q_j^t = q_I +  t  /(T-1) * (q_F - q_I),  t ∈ {0, ..., T-1}
for t in range(T):
    ratio = t / (T - 1) if T > 1 else 0.0
    q[j][t] = (q_I[0] + ratio * (q_F[0] - q_I[0]),
               q_I[1] + ratio * (q_F[1] - q_I[1]))
```

---

## 4. 首次迭代（冷启动）策略

### 4.1 问题

BCD 循环中，Level-1 依赖 Level-2 的输出（q, f），Level-2 依赖 Level-1 的输出（x）。第 0 轮必须用默认值打破死锁。

### 4.2 论文默认策略（paper_default）

来源：公式20_两层解耦.md §4.1

- **轨迹**：直线插值 `q_j^(0) = q_I + t/(T-1) * (q_F - q_I)`
- **频率**：均分 `f_{j,i}^(0) = f_max / |I|`（|I| 为任务总数）

**当前代码的退化问题**：场景生成器中 `uav.pos == uav.pos_final == depot`，直线插值退化为全时隙停在 depot。若 depot 在地图中心 (500, 500)，尚可接受；若在角落则远处任务全不可卸载。

### 4.3 扩展策略（备选）

| 策略名 | 轨迹初始化 | 频率初始化 | 适用场景 |
|--------|-----------|-----------|---------|
| paper_default | 直线插值 | 均分 f_max/|I| | pos ≠ pos_final 时 |
| stationary_depot | 全时隙停 depot | 均分 f_max/|I| | pos == pos_final == depot |
| kmeans_hover | K-Means 聚类到任务密集区悬停 | 按任务量比例分配 | 打破 depot 死锁 |

**建议**：MVP 实现 `paper_default`，接口支持 `policy` 参数可扩展。

### 4.4 后续迭代

```
第 k 轮 (k >= 1):
  snapshot_k = Level2Snapshot(q=q^(k-1), f_edge=f^(k-1), source="prev_bcd")
  D_hat, E_hat = precompute(scenario, config, snapshot_k)
```

严格使用**上一轮** Level-2 输出，不使用当前轮正在求的值，保证 BCD 收敛性。

---

## 5. 数值边界问题

### 5.1 除零与溢出

| 场景 | 原因 | 处理方案 |
|------|------|---------|
| r_up ≈ 0 | 任务距 UAV 极远，g → 0 | `rate < eps_rate → D_hat = INF` |
| f_edge = 0 | Level-2 未分配频率 | 直接标记为 infeasible |
| f_local = 0 | 不应出现，防御性检查 | 直接标记为 infeasible |

### 5.2 浮点精度

| 场景 | 原因 | 处理方案 |
|------|------|---------|
| log2(1+SNR) 丢精度 | SNR 极小时 | 用 `math.log1p(snr) / math.log(2)` |
| D_hat_offload ≤ tau 浮点误杀 | 浮点比较 | `_offload_feasible` 使用容差 `tau + 1e-9` |

### 5.3 Gurobi 数值稳定性

| 场景 | 原因 | 处理方案 |
|------|------|---------|
| 系数跨度 > 10^6 | D_hat 设为 1e10 等极大值 | 封顶 `D_hat = min(D_hat, 100 * tau_max)` |
| E_hat 与 D_hat 量纲差异 | gamma_j=1e-28, f=1e9, F=1e8 → E≈1e-2 | 诊断输出 min/max/mean，必要时调权重 |

### 5.4 静默失败

`_offload_feasible()` 在 `D_hat_offload` 缺 key 时静默返回 False（`except (KeyError, IndexError): return False`），会把预计算 bug 伪装为"无可用 UAV"。预计算模块必须保证输出完整性，覆盖所有 active 的 `(i, j, t)` 组合。

### 5.5 默认参数下的可行性

实测估算：默认 `tau_max=2.0s`，最乐观的远程卸载下界约 1.98s。大量 `(i,j,t)` 天然不可卸载。预计算模块应原生支持大比例 infeasible 候选，诊断输出中报告 infeasible 比例。

---

## 6. 接口设计建议

### 6.1 两步分离

```python
# Step 1: 构造 Level-2 快照（首次用默认值，后续用 Level-2 输出）
snapshot = make_initial_level2_snapshot(
    scenario, config, policy="paper_default"
)

# Step 2: 执行预计算（无状态，可复用）
result = precompute_offloading_inputs(scenario, config, snapshot)
# result.D_hat_local, result.D_hat_offload, result.E_hat_comp, result.diagnostics
```

### 6.2 数据结构

```python
@dataclass(frozen=True)
class PrecomputeParams:
    """从 configPara 提取的预计算所需物理参数"""
    H: float          # UAV 飞行高度 (m)
    B_up: float       # 上行带宽 (Hz)
    B_down: float     # 下行带宽 (Hz)
    P_i: float        # 终端发射功率 (W)
    P_j: float        # UAV 发射功率 (W)
    N_0: float        # 噪声功率 (W)
    rho_0: float      # 1m 参考信道增益
    gamma_j: float    # 边缘节点芯片能耗系数
    # 数值保护
    eps_dist_sq: float = 1e-12  # 距离平方下限
    eps_rate: float = 1e-12     # 速率下限
    tau_tol: float = 1e-9       # tau 比较容差

@dataclass(frozen=True)
class Level2Snapshot:
    """Level-2 输出的快照，或首次迭代的默认值"""
    q: dict[int, dict[int, tuple[float, float]]]   # q[j][t] = (x, y)
    f_edge: dict[int, dict[int, dict[int, float]]]  # f_edge[j][i][t] = Hz
    f_local: dict[int, dict[int, float]] | None = None  # 可选覆盖
    source: str = "init"  # "init" | "prev_bcd"

@dataclass(frozen=True)
class PrecomputeResult:
    """预计算输出"""
    D_hat_local: dict[int, dict[int, float]]              # [i][t]
    D_hat_offload: dict[int, dict[int, dict[int, float]]]  # [i][j][t]
    E_hat_comp: dict[int, dict[int, dict[int, float]]]     # [j][i][t]
    diagnostics: dict  # min/max/mean, infeasible_ratio, etc.
```

### 6.3 函数签名

```python
def make_initial_level2_snapshot(
    scenario: EdgeUavScenario,
    config: configPara,
    *,
    policy: str = "paper_default",  # "paper_default" | "stationary_depot" | "kmeans_hover"
) -> Level2Snapshot:
    """构造首次迭代的 Level-2 默认快照"""
    ...

def precompute_offloading_inputs(
    scenario: EdgeUavScenario,
    config: configPara,
    snapshot: Level2Snapshot,
    *,
    mu: dict[int, dict[int, float]] | None = None,  # 可选时变工作量，默认 task.F
    active_only: bool = True,  # 是否只计算 active 时隙
) -> PrecomputeResult:
    """无状态预计算函数，根据场景+配置+Level-2 快照计算三个预计算量"""
    ...
```

---

## 7. A2 详细接口设计

> 日期：2026-03-17
> 三方协同：Claude 设计 + Codex 骨架验证 + Gemini 交叉审查
> 目标文件：`edge_uav/model/precompute.py`

### 7.1 设计决策记录

| 决策 | 选项 | 结论 | 理由 |
|------|------|------|------|
| 架构风格 | A) 纯函数 B) Precomputer 类 | **A) 纯函数** | 预计算无状态；PrecomputeParams 已封装参数；类增加 ceremony 无收益（Codex+Claude 共识） |
| 主函数入参 | A) 传 config B) 传 PrecomputeParams | **B) PrecomputeParams** | 依赖注入，易测试；调用方先 `from_config()` 提取参数（Gemini 建议） |
| 初始化入参 | A) 传 scenario+config B) 仅 scenario | **B) 仅 scenario** | 初始化只需 uav.pos/pos_final/f_max 和 task 数量，均在 scenario 中（Codex 验证） |
| 上下行速率 | A) 两个函数 B) 合并 `_rate_from_gain` | **B) 合并** | 同一公式不同参数，避免重复接口（Codex 建议） |
| 信道增益缓存 | A) 全局缓存 B) 局部变量复用 | **B) 局部复用** | 同一 (i,j,t) 上下行共享，在循环内层用局部变量即可（Gemini 建议） |
| infeasible 表示 | A) float('inf') B) 缺 key C) BIG_M 封顶 | **C) BIG_M 封顶** | inf 会污染 Gurobi 系数矩阵；缺 key 被 `_offload_feasible` 静默吞掉；BIG_M 封顶安全且可控 |

### 7.2 类型别名

```python
from __future__ import annotations
from typing import Any, Literal, Mapping

# 嵌套 dict 类型别名，与 OffloadingModel 的接口一致
Scalar2D = dict[int, dict[int, float]]               # [i][t] 或 [j][t]
Scalar3D = dict[int, dict[int, dict[int, float]]]     # [i][j][t] 或 [j][i][t]
Trajectory2D = dict[int, dict[int, tuple[float, float]]]  # q[j][t] = (x, y)

Level2Source = Literal["init", "prev_bcd", "history_avg", "custom"]
InitPolicy = Literal["paper_default", "custom"]
```

### 7.3 数据结构

#### 7.3.1 PrecomputeParams

```python
@dataclass(frozen=True)
class PrecomputeParams:
    """从 configPara 提取的预计算所需物理参数。

    frozen=True 保证不可变，可安全在迭代间复用。
    """

    # ---- 物理参数 ----
    H: float          # UAV 飞行高度 (m)
    B_up: float       # 上行带宽 (Hz)
    B_down: float     # 下行带宽 (Hz)
    P_i: float        # 终端发射功率 (W)
    P_j: float        # UAV 发射功率 (W)
    N_0: float        # 噪声功率 (W)
    rho_0: float      # 1m 参考信道增益
    gamma_j: float    # 边缘节点芯片能耗系数

    # ---- 数值保护 ----
    eps_dist_sq: float = 1e-12   # 距离平方下限，防 g → ∞
    eps_rate: float = 1e-12      # 速率下限，防除零
    eps_freq: float = 1e-12      # 频率下限，防除零
    tau_tol: float = 1e-9        # tau 比较容差
    big_m_delay: float = 1e6     # BIG_M 封顶值（秒），兜底 infeasible

    @classmethod
    def from_config(
        cls,
        config: configPara,
        *,
        eps_dist_sq: float = 1e-12,
        eps_rate: float = 1e-12,
        eps_freq: float = 1e-12,
        tau_tol: float = 1e-9,
        big_m_delay: float = 1e6,
    ) -> "PrecomputeParams":
        """从 configPara 提取 8 个物理参数，合并数值保护默认值。

        调用方式：
            params = PrecomputeParams.from_config(config)
            params = PrecomputeParams.from_config(config, big_m_delay=200.0)
        """
        return cls(
            H=config.H,
            B_up=config.B_up,
            B_down=config.B_down,
            P_i=config.P_i,
            P_j=config.P_j,
            N_0=config.N_0,
            rho_0=config.rho_0,
            gamma_j=config.gamma_j,
            eps_dist_sq=eps_dist_sq,
            eps_rate=eps_rate,
            eps_freq=eps_freq,
            tau_tol=tau_tol,
            big_m_delay=big_m_delay,
        )
```

#### 7.3.2 Level2Snapshot

```python
@dataclass(frozen=True)
class Level2Snapshot:
    """Level-2 输出的快照，或首次迭代的默认值。

    q 和 f_edge 必须是 dense 的：覆盖所有候选 (j,t) 和 (j,i,t)。
    否则 precompute 无法为 OffloadingModel 生成完整的决策空间。

    维度约定：
        q[j][t] = (x, y)         — UAV j 在时隙 t 的 2D 水平位置
        f_edge[j][i][t] = Hz     — UAV j 为任务 i 在时隙 t 分配的 CPU 频率
        f_local_override[i][t]   — 可选，覆盖 task.f_local 的本地频率
    """

    q: Trajectory2D
    f_edge: Scalar3D
    f_local_override: Scalar2D | None = None
    source: Level2Source = "init"

    def validate(
        self,
        scenario: EdgeUavScenario,
        *,
        require_dense: bool = True,
    ) -> None:
        """校验快照的索引覆盖与值合法性。

        检查项：
        1. q 覆盖所有 (j, t) ∈ uavs × time_slots
        2. f_edge 覆盖所有 (j, i, t) ∈ uavs × tasks × time_slots（当 require_dense=True）
        3. 所有频率值 > 0
        4. 所有位置在地图边界内（如 meta 中有 x_max/y_max）
        5. f_local_override 若非 None，覆盖所有 (i, t) ∈ tasks × time_slots

        Raises:
            ValueError: 累积所有错误后一次性抛出。
        """
        raise NotImplementedError
```

#### 7.3.3 PrecomputeResult

```python
@dataclass(frozen=True)
class PrecomputeResult:
    """预计算输出，字段直接对齐 OffloadingModel.__init__ 参数。

    调用方式：
        result = precompute_offloading_inputs(scenario, params, snapshot)
        model = OffloadingModel(
            tasks=scenario.tasks,
            uavs=scenario.uavs,
            time_list=scenario.time_slots,
            D_hat_local=result.D_hat_local,
            D_hat_offload=result.D_hat_offload,
            E_hat_comp=result.E_hat_comp,
        )
    """

    D_hat_local: Scalar2D       # [i][t] — 本地执行时延 (s)
    D_hat_offload: Scalar3D     # [i][j][t] — 远程卸载总时延 (s)
    E_hat_comp: Scalar3D        # [j][i][t] — 边缘计算能耗 (J)
    diagnostics: dict[str, Any]  # 诊断信息（见 §7.6）
```

### 7.4 公开 API

#### 7.4.1 make_initial_level2_snapshot

```python
def make_initial_level2_snapshot(
    scenario: EdgeUavScenario,
    *,
    policy: InitPolicy = "paper_default",
) -> Level2Snapshot:
    """构造首次迭代（k=0）的 Level-2 默认快照。

    policy="paper_default"（公式20_两层解耦.md §4.1）：
        轨迹：直线插值 q_j^t = q_I + t/(T-1) * (q_F - q_I)
        频率：均分 f_edge[j][i][t] = f_max / |I|

    返回的 Level2Snapshot 已通过 validate() 校验。
    """
    if policy == "paper_default":
        q = _init_trajectory_linear(scenario)
        f_edge = _init_frequency_uniform(scenario)
    else:
        raise ValueError(f"Unsupported init policy: {policy!r}")

    snap = Level2Snapshot(q=q, f_edge=f_edge, source="init")
    snap.validate(scenario)
    return snap
```

#### 7.4.2 precompute_offloading_inputs

```python
def precompute_offloading_inputs(
    scenario: EdgeUavScenario,
    params: PrecomputeParams,
    snapshot: Level2Snapshot,
    *,
    mu: Mapping[int, Mapping[int, float]] | None = None,
    active_only: bool = True,
) -> PrecomputeResult:
    """无状态预计算主函数。

    参数
    ----------
    scenario : EdgeUavScenario
        场景数据（tasks, uavs, time_slots）。
    params : PrecomputeParams
        物理参数 + 数值保护。
    snapshot : Level2Snapshot
        Level-2 输出快照（q, f_edge）。
    mu : Mapping[int, Mapping[int, float]] | None
        可选时变工作量 mu[i][t]，默认使用 task.F。
    active_only : bool
        True 时仅计算 active 时隙，非 active 跳过。

    返回
    -------
    PrecomputeResult
        D_hat_local, D_hat_offload, E_hat_comp, diagnostics。

    计算流程
    --------
    1. 初始化 guard_hits 计数器
    2. 遍历 tasks × time_slots → D_hat_local[i][t]
    3. 遍历 tasks × uavs × time_slots:
       a. 计算信道增益 g（局部变量复用）
       b. 计算上行速率 r_up、下行速率 r_down（复用 g）
       c. 计算 D_hat_offload[i][j][t] = T_up + T_comp + T_down
       d. 计算 E_hat_comp[j][i][t] = gamma_j * f^2 * F
       e. 累计 guard_hits
    4. 构建 diagnostics
    """
    raise NotImplementedError
```

### 7.5 私有 Helper 函数

#### 7.5.1 初始化 Helper

```python
def _init_trajectory_linear(scenario: EdgeUavScenario) -> Trajectory2D:
    """直线插值轨迹初始化。

    公式（代码版，0-indexed）：
        q_j^t = q_I + t/(T-1) * (q_F - q_I),  t ∈ {0, ..., T-1}

    当 T=1 时 ratio=0，全部停在起点。
    当 pos == pos_final（depot）时退化为全时隙停 depot。
    """
    raise NotImplementedError


def _init_frequency_uniform(scenario: EdgeUavScenario) -> Scalar3D:
    """均分频率初始化。

    f_edge[j][i][t] = uav_j.f_max / len(scenario.tasks)

    输出是 dense 的：覆盖全部 (j, i, t) 候选对。
    """
    raise NotImplementedError
```

#### 7.5.2 物理计算纯函数

```python
def _channel_gain(
    pos_i: tuple[float, float],
    q_jt: tuple[float, float],
    *,
    H: float,
    rho_0: float,
    eps_dist_sq: float,
) -> float:
    """空地信道增益。

    g = rho_0 / max(H^2 + ||pos_i - q_jt||^2, eps_dist_sq)

    eps_dist_sq 防止 UAV 恰好在终端正上方时 d^2=H^2 过小导致 g 爆大。
    实际上 H >= 100m 时不太可能触发，但作为防御性保护保留。
    """
    raise NotImplementedError


def _rate_from_gain(
    gain: float,
    *,
    bandwidth: float,
    tx_power: float,
    noise_power: float,
    eps_rate: float,
) -> float:
    """Shannon 速率，统一用于上行和下行。

    r = bandwidth * log2(1 + tx_power * gain / noise_power)
      = bandwidth * log1p(tx_power * gain / noise_power) / log(2)

    使用 log1p 避免 SNR 极小时精度丢失。
    当 r < eps_rate 时返回 eps_rate（触发 guard_hit 由调用方计数）。
    """
    raise NotImplementedError


def _local_delay(
    workload: float,
    freq: float,
    *,
    eps_freq: float,
    big_m_delay: float,
) -> float:
    """本地计算时延。

    D = workload / max(freq, eps_freq)
    若 freq < eps_freq 则返回 big_m_delay。
    """
    raise NotImplementedError


def _offload_delay(
    *,
    D_l: float,
    D_r: float,
    workload: float,
    r_up: float,
    r_down: float,
    f_edge: float,
    eps_rate: float,
    eps_freq: float,
    big_m_delay: float,
) -> float:
    """远程卸载总时延 = 上行 + 计算 + 下行。

    T_up   = D_l / max(r_up, eps_rate)
    T_comp = workload / max(f_edge, eps_freq)
    T_down = D_r / max(r_down, eps_rate)
    total  = T_up + T_comp + T_down

    若 total > big_m_delay 则封顶为 big_m_delay。
    """
    raise NotImplementedError


def _edge_energy(
    *,
    gamma_j: float,
    f_edge: float,
    workload: float,
    eps_freq: float,
    big_m_delay: float,
) -> float:
    """边缘计算能耗。

    E = gamma_j * f_edge^2 * workload

    当 f_edge < eps_freq 时返回 0.0（频率为零 = 不计算 = 无能耗）。
    注意：big_m_delay 参数此处保留用于未来的能耗封顶。
    """
    raise NotImplementedError
```

#### 7.5.3 诊断 Helper

```python
def _finite_stats(values: list[float]) -> dict[str, float | int | None]:
    """对 finite 值（排除 inf/nan）计算 min/max/mean/count。

    若无 finite 值返回 {min: None, max: None, mean: None, count: 0}。
    """
    raise NotImplementedError


def _build_diagnostics(
    *,
    D_hat_local: Scalar2D,
    D_hat_offload: Scalar3D,
    E_hat_comp: Scalar3D,
    tasks: dict,
    snapshot_source: Level2Source,
    guard_hits: dict[str, int],
    active_task_slots: int,
    candidate_offload_pairs: int,
    deadline_feasible_pairs: int,
    uplink_rates: list[float],
    downlink_rates: list[float],
    tasks_all_uavs_infeasible: list[int],
    tasks_local_over_tau: list[int],
) -> dict[str, Any]:
    """构建紧凑诊断字典。"""
    raise NotImplementedError
```

### 7.6 diagnostics 字段规格

```python
diagnostics = {
    # ---- 来源与规模 ----
    "snapshot_source": str,             # "init" | "prev_bcd"
    "active_task_slots": int,           # 活跃 (i,t) 对总数
    "candidate_offload_pairs": int,     # 全部 (i,j,t) 候选数
    "deadline_feasible_pairs": int,     # D_hat_offload <= tau + tau_tol 的数量
    "offload_feasible_ratio": float,    # = feasible / candidate

    # ---- 物理量统计（仅 finite 值）----
    "local_delay_stats": {"min": float, "max": float, "mean": float, "count": int},
    "offload_delay_stats": {"min": float, "max": float, "mean": float, "count": int},
    "edge_energy_stats": {"min": float, "max": float, "mean": float, "count": int},
    "uplink_rate_stats": {"min": float, "max": float, "mean": float, "count": int},   # bps
    "downlink_rate_stats": {"min": float, "max": float, "mean": float, "count": int}, # bps

    # ---- 数值保护触发计数 ----
    "guard_hits": {
        "rate_floor": int,              # r < eps_rate 触底次数
        "freq_floor": int,              # f < eps_freq 触底次数
        "big_m_cap": int,               # delay > big_m 封顶次数
        "tau_tol_borderline": int,      # |D_hat - tau| < tau_tol 边界次数
    },

    # ---- 告警 ----
    "tasks_all_uavs_infeasible": list[int],  # 所有 UAV 都不可卸载的任务 ID
    "tasks_local_over_tau": list[int],        # 本地也超时的任务 ID
}
```

### 7.7 与 OffloadingModel 的桥接

PrecomputeResult 的三个字段直接解包传入 OffloadingModel：

```python
# 典型调用链
params = PrecomputeParams.from_config(config)
snapshot = make_initial_level2_snapshot(scenario)
result = precompute_offloading_inputs(scenario, params, snapshot)

model = OffloadingModel(
    tasks=scenario.tasks,           # {i: ComputeTask}
    uavs=scenario.uavs,            # {j: UAV}
    time_list=scenario.time_slots,  # [0, 1, ..., T-1]
    D_hat_local=result.D_hat_local,       # [i][t]
    D_hat_offload=result.D_hat_offload,   # [i][j][t]
    E_hat_comp=result.E_hat_comp,         # [j][i][t]
    alpha=config.alpha,
    gamma_w=config.gamma_w,
)
```

### 7.8 OffloadingModel 接口对齐验证

| OffloadingModel 参数 | 类型 | PrecomputeResult 字段 | 对齐 |
|---------------------|------|----------------------|------|
| D_hat_local | `dict`, `[i][t]` 访问 | `result.D_hat_local` (Scalar2D) | ✓ |
| D_hat_offload | `dict`, `[i][j][t]` 访问 | `result.D_hat_offload` (Scalar3D) | ✓ |
| E_hat_comp | `dict`, `[j][i][t]` 访问 | `result.E_hat_comp` (Scalar3D) | ✓ |
| tasks | `{i: ComputeTask}` | 直接传 `scenario.tasks` | ✓ |
| uavs | `{j: UAV}` | 直接传 `scenario.uavs` | ✓ |
| time_list | `list[int]` | 直接传 `scenario.time_slots` | ✓ |

OffloadingModel 内部访问路径：
- `self.D_hat_local[i][t]` → `default_dynamic_obj_func` :311, `_offload_feasible` 未使用
- `self.D_hat_offload[i][j][t]` → `_offload_feasible` :198, `default_dynamic_obj_func` :317
- `self.E_hat_comp[j][i][t]` → `default_dynamic_obj_func` :327

注意 **E_hat_comp 的索引顺序是 [j][i][t]**（先 UAV 后 task），与 D_hat_offload 的 [i][j][t] 相反。

---

## 8. 后续行动项

| 编号 | 任务 | 依赖 | 状态 |
|------|------|------|------|
| A1 | 分析 offloading.py 输入需求 | — | ✅ 完成 |
| A2 | 设计预计算模块详细接口 | A1 | ✅ 完成 |
| A3 | 实现 `edge_uav/model/precompute.py` | A2 | ✅ 完成（675行，13/13 函数） |
| A4 | 测试 + 与 Level-1 BLP 联调 | A3 | ✅ 完成（S7 端到端，4 场景，44/44 通过） |
| P2 补 | `底层变量清单.md` 补充预计算常数命名 | A2 | ⬜ 低优先级 |
