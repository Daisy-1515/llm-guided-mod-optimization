# 时间窗约束的学术定义与分类：UAV-MEC 系统视角

> 理论分析报告 | 2026-04-06

---

## 1. 时间窗的核心定义

### 1.1 基本形式化

时间窗（Time Window）是对服务/任务执行时间的区间约束。对于节点（客户/任务）$i$，时间窗定义为闭区间：

$$[a_i, b_i] \quad \text{或等价记为} \quad [e_i, l_i]$$

其中 $a_i$（或 $e_i$，earliest）为最早允许服务时间，$b_i$（或 $l_i$，latest）为最晚允许服务时间。

在 VRPTW 经典文献（Solomon, 1987）中，车辆 $k$ 到达客户 $i$ 的时间 $s_i$ 必须满足：

$$a_i \leq s_i \leq b_i$$

若车辆早到（$s_i < a_i$），则需等待至 $a_i$ 再开始服务。

### 1.2 硬时间窗 vs 软时间窗

**硬时间窗（Hard Time Window）**：时间窗是可行性约束，违反即不可行。

$$s_i \notin [a_i, b_i] \implies \text{解不可行（infeasible）}$$

在数学规划中，这对应刚性约束（hard constraint），求解器直接将违反窗口的解剪枝。

**软时间窗（Soft Time Window）**：窗口外的服务是允许的，但会产生惩罚。目标函数中引入额外代价项：

$$\text{penalty}_i = c_e \cdot \max(a_i - s_i, 0) + c_l \cdot \max(s_i - b_i, 0)$$

其中 $c_e$ 为早到惩罚系数，$c_l$ 为迟到惩罚系数。当 $c_l \to \infty$ 时，软窗退化为硬窗。

**区别的数学本质**：硬窗是约束空间的边界（可行域的面），软窗是目标空间的结构（目标函数的形状）。两者的优化行为完全不同——硬窗通过约束传播（constraint propagation）剪枝搜索空间，软窗通过梯度/代价引导搜索方向。

---

## 2. UAV-MEC 系统中的三类时间窗

### 2.1 任务截止时间窗（Deadline Window）

**定义**：每个计算任务 $i$ 必须在生成后的 $\tau_i$ 时间内完成执行（本地或卸载），否则视为超时。

**形式化**：设任务 $i$ 在时隙 $t$ 生成，完成时间为 $c_i$，则：

$$c_i - t \cdot \delta \leq \tau_i$$

其中 $\delta$ 为时隙长度（秒）。这定义了一个**单边时间窗** $[t \cdot \delta, \; t \cdot \delta + \tau_i]$，左端点由任务生成时刻确定，右端点由截止期确定。

**在 MEC 文献中的典型形式**：

- 本地执行：$t_i^{\text{local}} = F_i / f_i^{\text{local}} \leq \tau_i$
- 卸载执行：$t_i^{\text{offload}} = t_i^{\text{up}} + t_i^{\text{comp}} + t_i^{\text{down}} \leq \tau_i$

其中 $t_i^{\text{up}}, t_i^{\text{comp}}, t_i^{\text{down}}$ 分别为上行传输、边缘计算、下行传输时延。

### 2.2 服务时间窗（Service Window / Active Window）

**定义**：任务 $i$ 仅在特定时隙集合 $\mathcal{A}_i \subseteq \{0, 1, \ldots, T-1\}$ 内活跃（可被服务）。

**形式化**：活跃标志函数 $\zeta_i^t$：

$$\zeta_i^t = \begin{cases} 1 & \text{if } t \in \mathcal{A}_i \\ 0 & \text{otherwise} \end{cases}$$

任务分配约束：

$$\sum_{t \in \mathcal{A}_i} \left( x_i^{\text{local}}(t) + \sum_{j} x_i^j(t) \right) = 1 \quad \forall i$$

这要求每个任务在其活跃窗口内被恰好分配一次。

**窗口结构**：
- 连续窗口（contiguous window）：$\mathcal{A}_i = \{t_{\text{start}}, t_{\text{start}}+1, \ldots, t_{\text{end}}\}$，对应 VRPTW 的经典区间形式。
- 离散窗口（scattered window）：$\mathcal{A}_i$ 为任意子集，更一般但组合复杂度更高。

### 2.3 资源可用时间窗（Resource Availability Window）

**定义**：UAV $j$ 的服务能力受飞行能量、CPU 频率等资源约束，这些资源在时间维度上具有有限可用性。

**形式化**：

- 能量因果约束（Energy Causality）：$\sum_{t'=0}^{t} E_j^{t'} \leq E_j^{\max} \quad \forall t, j$

- CPU 容量约束：$\sum_{i: x_i^j(t)=1} f_{ij}^t \leq f_j^{\max} \quad \forall t, j$

- 承载约束：$\sum_{i: x_i^j(t)=1} 1 \leq N_j^{\max} \quad \forall t, j$

这些约束隐式地定义了 UAV 在哪些时隙仍有能力服务新任务——当能量耗尽或 CPU 饱和时，该 UAV 的"服务窗口"事实上已关闭。

**与前两类的区别**：截止窗口和服务窗口是**任务侧**属性（task-centric），资源窗口是**服务器侧**属性（server-centric）。三者的交集决定了实际可行的分配方案。

---

## 3. 当前项目的 `tau`（时隙）与时间窗的关系

### 3.1 现有建模分析

基于对项目代码的审查，当前系统中存在两种时间约束：

**约束 A：任务截止期 `tau`**
- 定义位置：`ComputeTask.tau`（`edge_uav/data.py:24`）
- 取值范围：$[\tau_{\min}, \tau_{\max}] = [0.5, 2.0]$ 秒（`config.py:115-116`）
- 约束类型：**硬时间窗**
- 实施方式：
  - L1 层（`offloading.py`）中通过 `_offload_feasible(i, j, t)` 判断 $D\_hat\_offload[i][j][t] \leq \tau_i$
  - 不满足时直接将 $x\_offload[i,j,t] = 0$（硬约束剪枝）
  - 同时在目标函数中作为归一化分母：$D\_hat / \tau$（软感知）

**约束 B：活跃窗口 `active`**
- 定义位置：`ComputeTask.active`（`edge_uav/data.py:25`）
- 窗口长度：$[5, 15]$ 个时隙（`config.py:119-120`）
- 模式：连续窗口（`contiguous_window`，`config.py:118`）
- 约束类型：**硬时间窗**
- 实施方式：所有 L1 求和中通过 `if self.task[i].active[t]` 门控

### 3.2 `tau` 是固定窗口还是动态窗口？

当前 `tau` 是**静态固定窗口**：
- 每个任务的 $\tau_i$ 在场景生成时从 $U[\tau_{\min}, \tau_{\max}]$ 随机采样，之后不变
- 不随 BCD 迭代、UAV 位置或通信条件动态调整
- 属于**先验参数**（a priori parameter），非**在线变量**（online variable）

对比文献中的**动态时间窗**概念：
- 在线调度场景中，时间窗可能随系统状态变化（如排队拥塞导致有效截止期缩短）
- 本项目未实现此机制——BCD 循环中 L1/L2 交替迭代，但 $\tau_i$ 始终固定

### 3.3 硬窗 vs 软窗的混合模式

当前项目实际上采用了**硬软混合**策略：

| 层级 | 约束类型 | 实现 |
|------|---------|------|
| L1 可行性 | 硬窗 | `_offload_feasible()` 直接裁剪不可行的 $(i,j,t)$ 对 |
| L1 目标函数 | 软窗 | `D_hat / tau` 归一化，接近截止期的任务代价更高 |
| Prompt 规则 10 | 软窗建议 | 建议 LLM 添加 `max(D_hat - tau, 0)` 惩罚 |
| L2b 轨迹优化 | 无窗口感知 | SCA 优化通信时延+飞行能耗，不直接约束任务截止期 |

这种混合模式的理论依据：硬窗保证可行性（不产生超时解），软窗引导搜索方向（优先服务紧迫任务）。

---

## 4. 时间窗引入后对三层架构的影响

### 4.1 LLM 层（Layer 1）：时间窗感知能力

**当前状态**：LLM 已具备基本的时间窗感知：
- Prompt 中暴露了 `self.task[i].tau`（截止期）
- 规则 10 明确建议 deadline-aware 设计
- 规则 16 鼓励使用 `math.exp(D/tau)` 等非线性变换

**引入更丰富时间窗后的影响**：

若引入异构时间窗（如每个任务有不同的 $[a_i, b_i]$ 而非统一的 $\tau_i$），LLM 需要：

1. **额外变量暴露**：将 $a_i, b_i$ 加入 `precomputed constants` 列表
2. **统计信息更新**：在 `set_scenario_info()` 中报告时间窗分布特征（紧窗/宽窗比例、窗口重叠度）
3. **设计模式引导**：prompt 中添加时间窗相关的设计模式，如：
   - 窗口紧张度：$(b_i - a_i) / \bar{\tau}$ 作为归一化紧迫度
   - 窗口重叠惩罚：多任务同时截止时增加分散化激励

**LLM 的核心限制**：LLM 生成的是 L1 目标函数（BLP 的目标），无法直接修改约束。因此时间窗的硬约束部分仍需在 `setupCons()` 中预设，LLM 只能通过软惩罚项来"感知"时间窗。

### 4.2 Harmony Search 层（Layer 2 / HS）：时间窗下的进化

**当前进化机制**：HS 在目标函数代码空间中搜索，每个"音"（harmony）对应一个 LLM 生成的目标函数。适应度通过运行完整 BCD 循环后的系统总代价评估。

**时间窗引入后的影响**：

1. **适应度景观变化**：时间窗越紧，可行域越小，BCD 更可能不收敛或产生高代价解。HS 需要在"可行性"和"目标值"之间平衡。

2. **约束违反率作为辅助指标**：可将时间窗违反比例纳入适应度评估：
   $$\text{fitness} = \text{cost} + \lambda \cdot \text{violation\_ratio}$$
   但当前 L1 硬窗已确保可行性，故此项在硬窗模式下恒为 0。

3. **HS 参数适应**：紧时间窗场景下，目标函数的微小变化可能导致可行/不可行的翻转。HMCR（Harmony Memory Considering Rate）可能需要提高（更多利用已知好解），PAR 降低（减少随机扰动幅度）。

### 4.3 优化器层（Layer 3）：约束求解

**L1 (Gurobi BLP)**：
- 硬时间窗已通过 `_offload_feasible()` 实现预筛选
- 若改为显式 Gurobi 约束（$D\_hat[i][j][t] \cdot x[i,j,t] \leq \tau_i$），可利用 Gurobi 的 lazy constraint 和 cutting plane 机制，可能提升求解效率

**L2a (资源分配)**：
- 当前无时间窗约束，CPU 频率分配仅受能量预算约束
- 引入时间窗后，频率分配需满足：$F_i / f_{ij} \leq \tau_i - t_i^{\text{comm}}$（计算时间 ≤ 截止期减去通信时间）

**L2b (SCA 轨迹优化)**：
- 当前已知瓶颈：能耗项远大于通信时延项，导致轨迹退化为直线
- 时间窗可提供新的牵引力：UAV 必须在特定时间到达特定位置附近才能满足任务截止期
- 形式化：$\|q_j^t - p_i\| \leq r_{\text{comm}}(\tau_i, t)$，其中 $r_{\text{comm}}$ 是满足截止期所需的最大通信距离

---

## 5. 总结与建议

### 关键发现

1. **当前系统已实现两种硬时间窗**（`tau` 截止期 + `active` 服务窗口），但二者独立运作，缺乏联合建模。

2. **`tau` 是静态先验参数**，不随优化过程动态调整。这限制了系统对实时变化的适应能力。

3. **L1 层采用硬软混合策略**：硬窗保可行性（`_offload_feasible`），软窗引搜索方向（`D/tau` 归一化）。这是合理的分层设计。

4. **L2b 层对时间窗无感知**：SCA 轨迹优化仅考虑通信时延和飞行能耗，不直接约束任务截止期。这是导致"轨迹退化为直线"问题的理论根源之一——缺少将 UAV 牵引到任务位置的时间驱动力。

### 理论建议

- 时间窗的引入应优先在 **L2b 层**体现，通过"UAV 必须在任务截止期前到达可服务距离内"的约束，为 SCA 提供轨迹分化的物理动力。
- L1 层的 LLM prompt 可增加**时间窗紧张度**统计（窗口利用率、截止期分布偏度），帮助 LLM 更精确地设计权重。
- HS 层可将**时间窗满足率**作为适应度的辅助评估维度。
