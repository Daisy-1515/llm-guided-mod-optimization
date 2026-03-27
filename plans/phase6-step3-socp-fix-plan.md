# Phase⑥ Step3：DCP 约束非凸性问题修复计划

**日期**：2026-03-25
**版本**：1.0（最终版）
**状态**：🗂️ 历史修复计划（后续已由 `fd723e3` 执行）
**优先级**：🔴 阻塞项（Phase④ 里程碑）

> 说明：本文是 Step3 修复前的执行计划。实际实施结果见
> `文档/40_审查与诊断/Phase6_Step3_SOCP_实施总结.md`，后续 Phase⑥ Step4
> 状态请以 `CLAUDE.md` 和 `文档/70_工作日记/2026-03-27.md` 为准。

---

## 【Context】为什么要做这个

### 两个不同层次的问题

#### Level 1：公式 (20) 整体凸性分析（已有文档）
- **文档**：`文档/10_模型与公式/公式20_凸性分析.md` (491 行)
- **问题**：原始联合优化问题 $\min_{x,f,P,q} C(x,f,P,q)$ 是**混合整数非凸**的
- **结论**：不能直接用凸优化求解，需要**分解**（BCD）
- **对策**：固定 $x,f,P$，只优化 $q$（轨迹）→ 得到 Level 2 子问题

#### Level 2：轨迹优化子问题的 CVXPY 建模问题（当前卡点）
- **问题**：在已固定 $x,f,P$ 的条件下，优化 $q$ 的子问题 $\min_q \phi(q)$
- **理论上**：这个子问题是**凸的**（固定了离散和功率变量后）
- **实施层面**：但在 CVXPY 中的**约束表达式**违反了 DCP 规则
  1. **通信延迟约束**（行 490-533）：`sqrt(distance²) × inv_pos(rate)` 是非凸乘积
  2. **安全分离约束**（行 535-554）：SCA 线性化中参考点迭代导致约束集非凸
- **症状**：11 个测试全部卡在 SCA 求解器阶段（CLARABEL/ECOS/SCS 返回 None）

### 为什么文档的分析不能直接解决当前问题

✓ **文档做对了**：证明了原问题是非凸的，说明需要分解策略
❌ **文档的局限**：只是诊断问题（"你是非凸的"），不是规定 CVXPY 代码该怎么写（"这是 DCP 规范约束"）

**比喻**：医生诊断你有高血压（凸性分析），但不能直接告诉你在 CVXPY 中如何写约束（SOCP 建模）。

### 当前卡点与修复方向
- **现象**：固定了 $x,f,P$ 后，理论上的凸子问题变成了 CVXPY 无法识别的**非 DCP 表达式**
- **原因**：代码中用了 `sqrt × inv_pos` 这样的"虽然凸但不符合 DCP 规则"的表达
- **修复**：将约束改写成 SOCP 形式，使其符合 DCP 规范 → CVXPY 求解器才能工作

### 修复的意义
- **技术**：不是改变问题本身，而是改变**代码表达方式**，使其符合 CVXPY DCP 规范
- **时间表**：解锁 Phase⑥ Step4（集成验证），为论文第 3 章提供可验证的数值结果
- **论文**：SOCP 形式更规范，便于学术发表和复现

---

## 【新增文档章节】方案 A：SOCP 修复方案

本章节将被添加到 `文档/10_模型与公式/公式20_凸性分析.md` 作为**第 8 节**。

### 章节标题
**第 8 节：SOCP 重新建模——从理论凸性到 CVXPY DCP 规范实现**

### 核心内容结构

#### 8.1 问题引入：为什么需要 SOCP

**背景**：
- 凸性分析证明了原问题是混合整数非凸的
- BCD 分解后，轨迹子问题 Level 2b 理论上是凸的
- **但在 CVXPY 代码实现中**，约束表达式违反 DCP 规范
- 求解器无法识别这些约束的凸性，返回失败

**具体违规例子**：
```python
# ❌ 违规：凹×凸乘积（CVXPY 无法识别）
sqrt(distance²) × inv_pos(rate) ≤ τ_comm
```

#### 8.2 SOCP 基础概述

**定义**：二阶锥规划问题的标准形式
$$
\min_{\mathbf{x}} \quad \mathbf{c}^T \mathbf{x}

\text{s.t.} \quad \|\mathbf{A}_i \mathbf{x} + \mathbf{b}_i\|_2 \leq \mathbf{c}_i^T \mathbf{x} + d_i, \quad i=1,\ldots,m
$$

**关键特性**：
- 约束集是二阶锥（second-order cone）的交集
- SOCP 问题本身是凸问题
- CVXPY 完全支持 SOCP（DCP 规范）
- 求解器：CLARABEL、ECOS、SCS 都可以高效求解

**凸性地位**：
```
LP (线性规划)
  ↓ 更强的表达能力
SOCP (二阶锥规划) ← 通常比 LP 更容易表达非线性约束
  ↓
SDP (半定规划)
```

#### 8.3 通信延迟约束的 SOCP 改写

**原约束**（非 DCP）：
$$
\text{Delay}_{ij}^t = \frac{2\sqrt{H^2 + \|\mathbf{q}_j^t - \mathbf{w}_i\|^2}}{r_{ij}^t(\mathbf{q}_j^t, P_i^t)} \leq \tau_i - \frac{\mu_i^t}{f_{j,i}^t}
$$

其中 $r_{ij}^t$ 是速率函数，$\tau_i$ 是任务时延预算。

**问题分析**：
- `sqrt(H² + distance²)` 是凹函数
- `inv_pos(rate)` 是凸函数
- 乘积：凹×凸 ⟹ 不在 DCP 规范内 ❌

**SOCP 改写**（方案 1：辅助变量 $s_{ji}^t$）：

引入辅助变量 $s_{ji}^t \geq 0$ 表示 UAV $j$ 与节点 $i$ 的空间距离：

$$
\text{(SOC-Comm-1)} \quad \|\mathbf{A}_{ji}^t\|_2 \leq s_{ji}^t
$$

其中 $\mathbf{A}_{ji}^t = [H, (q_j^t)_x - (w_i)_x, (q_j^t)_y - (w_i)_y]^T$（3 维向量）

**推导**：
$$
\sqrt{H^2 + \|\mathbf{q}_j^t - \mathbf{w}_i\|^2} = \|\mathbf{A}_{ji}^t\|_2 \leq s_{ji}^t
$$

然后改写通信延迟约束：

$$
\text{(SOC-Comm-2)} \quad 2 s_{ji}^t \cdot r_{ij}^t(\mathbf{q}_j^t, P_i^t) \geq D_i^{\mathrm{up}} + D_i^{\mathrm{down}}
$$

**CVXPY 形式**（伪代码）：
```python
# (SOC-Comm-1): 距离约束 — SOC 形式
dist_components = cp.hstack([H, q_var[j][t] - w_i])
s_jit = cp.Variable()
constraints.append(cp.norm(dist_components, 2) <= s_jit)

# (SOC-Comm-2): 延迟约束 — 改为 rate 的倒数形式（避免乘积）
rate_jit = _rate_lower_bound_expr(...)  # 凸函数
constraints.append(2.0 * s_jit <= rate_jit * tau_comm_jit)
```

**DCP 合规性验证**：
- `cp.norm(..., 2) <= s` ✅ SOC 约束，CVXPY 规范
- `2.0 * s * rate <= tau` ✅ 线性约束（线性组合），CVXPY 规范

#### 8.4 安全分离约束的 SCA 改进

**原约束**（非凸性来自 SCA 线性化）：
$$
\|\mathbf{q}_j^t - \mathbf{q}_k^t\|^2 \geq d_{\mathrm{safe}}^2
$$

**问题**：原约束是非凸的（右侧是常数）。SCA 在参考点 $\mathbf{q}^{\text{ref}}$ 处线性化：
$$
2 (\mathbf{q}_j^{\text{ref},t} - \mathbf{q}_k^{\text{ref},t})^T (\mathbf{q}_j^t - \mathbf{q}_k^t) - \|\mathbf{q}_j^{\text{ref},t} - \mathbf{q}_k^{\text{ref},t}\|^2 \geq d_{\mathrm{safe}}^2
$$

每次 SCA 迭代更新参考点时，约束形式改变 ⟹ 约束族非凸 ❌

**改进策略（方案 1：动态 Slack 权重）**：

添加松弛变量 $\delta_{jk}^t \geq 0$，在优化中逐步紧化其权重：

$$
\min \quad \Phi(\mathbf{q}, f, ...) + \rho_k \sum_{j,k,t} \delta_{jk}^t

\text{s.t.} \quad 2 \mathbf{d}_{\mathrm{bar}}^T (\mathbf{q}_j^t - \mathbf{q}_k^t) - \|\mathbf{d}_{\mathrm{bar}}\|^2 + \delta_{jk}^t \geq d_{\mathrm{safe}}^2
$$

其中：
- $\mathbf{d}_{\mathrm{bar}} = \mathbf{q}_j^{\text{ref},t} - \mathbf{q}_k^{\text{ref},t}$（当前参考点）
- 权重 $\rho_k$ 随迭代 $k$ 单调递增（如 $\rho_k = \rho_0 \cdot (1 + k)^{\alpha}$）

**效果**：
- 初期：约束宽松，SCA 易收敛
- 后期：$\delta$ 权重大，约束逐步紧化到原约束
- 最终：$\delta \approx 0$，满足原安全约束

#### 8.5 完整 Level 2b 问题的 SOCP 重新建模

**固定条件**：卸载决策 $\hat{\mathbf{x}}$、频率 $\hat{\mathbf{f}}$、功率 $\hat{\mathbf{P}}$ 已确定

**优化变量**：轨迹 $\mathbf{q}_j^t$、辅助距离变量 $s_{ji}^t$、安全 slack $\delta_{jk}^t$

**完整问题**：
$$
\min_{\mathbf{q}, s, \delta} \quad \phi_b(\mathbf{q}) + \rho \sum_{j,k,t} \delta_{jk}^t

\text{s.t.}
\begin{cases}
\text{(SOC-Comm-1)} & \|\mathbf{A}_{ji}^t\|_2 \leq s_{ji}^t, \quad \forall j,i,t \\
\text{(SOC-Comm-2)} & 2 s_{ji}^t \cdot r_{ij}^t \geq D_i^{\mathrm{up}} + D_i^{\mathrm{down}}, \quad \forall j,i,t \\
\text{(Lin-Safe)} & 2 \mathbf{d}_{\mathrm{bar}}^T (\mathbf{q}_j^t - \mathbf{q}_k^t) - \|\mathbf{d}_{\mathrm{bar}}\|^2 + \delta_{jk}^t \geq d_{\mathrm{safe}}^2, \quad \forall j>k,t \\
\text{(Lin-Bound)} & \mathbf{q}_j^t \in [\mathbf{q}_{\min}, \mathbf{q}_{\max}], \quad \forall j,t \\
\text{(Slack)} & \delta_{jk}^t \geq 0, \quad s_{ji}^t \geq 0
\end{cases}
$$

**DCP 规范验证**：
| 约束 | 形式 | DCP 规范 | 求解器 |
|------|------|---------|--------|
| SOC-Comm-1 | $\|\cdot\|_2 \leq s$ | ✅ 二阶锥 | CLARABEL/ECOS/SCS |
| SOC-Comm-2 | 线性（$2s \cdot r \geq D$） | ✅ 线性 | 所有 |
| Lin-Safe | 仿射 + Slack | ✅ 线性 | 所有 |
| Lin-Bound | 线性不等式 | ✅ 线性 | 所有 |

**CVXPY 问题状态**：`problem.is_dcp()` 应返回 `True` ✓

#### 8.6 实施步骤与验证

**步骤概览**：
1. 在 `trajectory_opt.py` 中实现 SOC-Comm-1/2 约束生成函数
2. 保留原有安全分离约束，仅改进权重策略
3. SCA 外层循环中逐步增加权重系数 $\rho_k$
4. 验证 CVXPY 问题 DCP 合规性
5. 单元测试：12 个测试用例全通过

**代码框架**（伪代码）：
```python
def build_sca_subproblem(scenario, params, q_ref):
    # 定义优化变量
    q_var = {j: {t: cp.Variable(2) for t in range(T)} for j in range(num_uavs)}
    s_var = {(j,i,t): cp.Variable() for (j,i,t) in active_offloads}
    delta_var = {(j,k,t): cp.Variable() for (j,k,t) in safety_pairs}

    # 目标函数
    objective = ... + cp.sum([w_delta * delta_var[(j,k,t)]
                             for (j,k,t) in safety_pairs])

    # 约束
    constraints = []

    # (1) SOC 通信约束
    for j, i, t in active_offloads:
        dist_vec = cp.hstack([H, q_var[j][t] - w_i])
        constraints.append(cp.norm(dist_vec, 2) <= s_var[(j,i,t)])

        rate = _rate_lower_bound(...)
        constraints.append(2 * s_var[(j,i,t)] * rate >= data_size)

    # (2) 安全约束 + Slack
    for j, k, t in safety_pairs:
        d_bar = q_ref[j][t] - q_ref[k][t]
        lhs = 2 * d_bar @ (q_var[j][t] - q_var[k][t]) - norm(d_bar)**2
        constraints.append(lhs + delta_var[(j,k,t)] >= d_safe**2)

    # (3) 其他约束（边界、可达性等）
    ...

    # 构建问题
    problem = cp.Problem(cp.Minimize(objective), constraints)

    # 验证 DCP
    assert problem.is_dcp(), "Problem violates DCP rules!"

    return problem, (q_var, s_var, delta_var)
```

#### 8.7 与论文的关联

**贡献明确**：
- 从理论凸性分析（第 7 节 BCD 分解）→ 实施层 SOCP 建模
- 补全了"如何用 CVXPY 求解 Level 2b"这一重要环节
- SOCP 形式更规范，便于复现和学术发表

**论文中的表述**（建议）：
> Level 2b（轨迹优化）子问题虽然在理论上是凸的（固定卸载与资源分配后），但其约束涉及距离函数与非线性通信模型的耦合。为了与 CVXPY 等规范锥规划求解器兼容，我们采用二阶锥规划（SOCP）重新建模，将通信延迟约束改写为标准 SOC 形式（公式 ...），并对安全分离约束应用动态 Slack 权重策略，确保 SCA 迭代的数值稳定性。

---

## 【问题分析】DCP 违规的数学根源

### 违规1：通信延迟约束非凸乘积

**当前代码**（行 529-531）：
```python
dist_from_height = cp.sqrt(z)                           # 凹函数
delay_ub = 2.0 * dist_from_height * cp.inv_pos(rate)   # ❌ 凹×凸=非DCP
constraints.append(delay_ub <= tau_comm_budget + 1e-9)
```

**数学问题**：
- `√z` 是**凹函数**（在凹上下文中允许）
- `1/rate` 是**凸函数**（在凸上下文中允许）
- 两个非仿射函数的**乘积不在 DCP 规范内**
- CVXPY 求解器无法识别此约束的凸性

**影响**：所有含通信约束的测试失败（T4, T6, T7, T8, T9）

### 违规2：安全分离约束的 SCA 线性化非凸性

**当前代码**（行 546-554）：
```python
d_bar = np.array(q_ref[j][t]) - np.array(q_ref[k][t])
delta_q = q_var[j][t] - q_var[k][t]
lhs = 2.0 * d_bar @ delta_q - d_bar_norm_sq + slack_jkt
constraints.append(lhs >= traj_params.d_safe ** 2)
```

**数学问题**：
- **单个约束形式**：`2·d_bar^T·(q_j - q_k) - ||d_bar||² + slack ≥ d_safe²` 是线性的 ✓
- **根本问题**：SCA 算法每迭代一次就生成新的线性化约束（因为 q_ref 更新）
- **多个线性化约束的叠加** → **约束集非凸**（外壳（hull）可能非凸）
- 这不是单约束的凸性问题，而是约束族的凸性问题

**影响**：所有含安全分离约束的测试失败（T5, T11, T12）

---

## 【修复方案】三个候选方案对比

### 方案 A：SOCP 重新建模（✓ 推荐）

#### 核心思路
将非凸乘积转化为 DCP 规范的 **SOCP**（二阶锥规划）约束。

#### 数学变换
```
原约束（非凸）：
  2·√(H² + ||q_j - w_i||²) · (1/rate) ≤ τ_comm

改写为 SOCP（DCP 规范）：
  (SOCP-1) 辅助变量 s 定义距离：
           ||[H, (q_j - w_i)_x, (q_j - w_i)_y]||_2 ≤ s

  (SOCP-2) 通信延迟约束（透视形式）：
           2·s·rate ≥ D_i  （乘积改为除法形式）

优点：
  - 完全 DCP 规范，CVXPY CLARABEL/ECOS 可直接求解
  - 数学精确，无近似误差
  - 约束形式标准，便于论文撰写

缺点：
  - 代码改动量中等（+50-70 行新约束代码）
  - SOCP 参数化相对复杂，需数学验证

工作量：
  - 代码改动：50-70 行
  - 测试修改：6 个测试用例调整
  - 迭代轮数：2-3 轮验证
```

---

### 方案 B：凸松弛或分段线性（快速但有误差）

#### 核心思路
避免乘积，改用分段线性或凸上界近似。

#### 优缺点
```
优点：改动快（<30 行），无需复杂参数化
缺点：
  - B1（直接松弛）仍含乘积，不解决 DCP 问题
  - B2（分段线性）增加约束数量，计算成本高
  - B3（凸上界）通信约束过度松弛，优化效果可能不佳

总体评分：⭐⭐（快但不彻底）
```

---

### 方案 C：改进 SCA 算法（二阶 Taylor 或 Trust Region）

#### 核心思路
增加 SCA 的线性化精度或限制参考点变化范围。

#### 优缺点
```
优点：保持现有 SCA 框架，算法改进相对独立
缺点：
  - Hessian 计算复杂且数值不稳定
  - McCormick 包络参数化繁琐
  - 仍无法完全解决非凸性，只是改善近似
  - 需要 3-4 轮调优迭代

总体评分：⭐⭐⭐（较好但改动大，风险高）
```

---

## 【推荐方案】A 方案详细实施

### 为什么选 A

1. **严格性**：完全消除 DCP 违规（不是近似）
2. **可靠性**：SOCP 是成熟的凸优化形式，求解器支持好
3. **可维护性**：标准数学形式，便于他人理解和论文发表
4. **成本-收益平衡**：工作量适中（25-26 小时），效果最佳

---

### 分步实施计划

#### 【步骤 1】通信延迟约束 SOCP 建模（3.5 小时）

**关键文件**：`edge_uav/model/trajectory_opt.py`（行 390-562）

**数学推导** *(用户可跳过)*：
```
原约束：
  Delay ≤ τ_comm
  其中 Delay = 2·√(H² + ||q_j - w_i||²) / rate(distance, power)

等价变换：
  rate(dist) ≥ 2·dist / τ_comm

引入辅助变量：
  s_ji = √(H² + ||q_j - w_i||²)  [距离项，用 SOC 约束表达]

SOCP 约束形式：
  (SOCP-1)  ||[H, (q_j - w_i)_x, (q_j - w_i)_y]||₂ ≤ s_ji
  (SOCP-2)  rate_ji·τ_comm_ji ≥ 2·s_ji + ε  [改写为乘积除法]
```

**代码改动**：
- 删除行 525-531（现有非 DCP 约束）
- 新增约束生成函数（50-70 行）
- 在 `_build_sca_subproblem` 中调用新函数

**验证清单**：
- [ ] CVXPY 确认 problem.is_dcp() == True
- [ ] CLARABEL 求解器能成功求解（status = "optimal"）

---

#### 【步骤 2】安全分离约束 SCA 改进（2.5 小时）

**关键文件**：`edge_uav/model/trajectory_opt.py`（行 540-554）

**策略**：采用**动态 slack 权重**，逐步紧化约束
```python
# 修改方案（无需改约束形式）：
for sca_iter in range(max_sca_iter):
    slack_weight = base_weight * (1.0 + sca_iter) ** 1.5  # 指数衰减
    objective += slack_weight * cp.sum(slack_vars_safe)
    # 求解...
```

**验证清单**：
- [ ] SCA 收敛性（迭代 10 次内到达局部最优）
- [ ] 最终轨迹中 ||q_j - q_k|| ≥ d_safe（安全距离满足）

---

#### 【步骤 3】代码实现 & 单元测试（5.5 小时）

**任务 3.1：新增约束函数**（1 小时）
```python
def _comm_socp_constraint_expr(
    q_var: dict,
    scenario: EdgeUavScenario,
    active_offloads: list,
    traj_params: TrajectoryOptParams,
) -> tuple[list, dict]:
    """生成通信延迟的 DCP-compliant SOCP 约束。"""
    constraints = []
    aux_vars = {}
    for j, i, t in active_offloads:
        s_jit = cp.Variable(name=f"dist_aux_{j}_{i}_{t}")
        aux_vars[(j, i, t)] = s_jit

        # SOC 约束：||[H, pos_diff]||₂ ≤ s
        pos_diff = q_var[j][t] - np.array(w_i)
        constraints.append(cp.norm(cp.hstack([H, pos_diff])) <= s_jit)

        # 速率下界：rate ≥ 2·s / τ_comm
        rate_expr = _rate_lower_bound_expr(...)
        constraints.append(2.0 * s_jit <= rate_expr * tau_comm_jit)

    return constraints, aux_vars
```

**任务 3.2：重构 `_build_sca_subproblem`**（2 小时）
- 替换通信约束调用（行 495-533）
- 保留安全分离约束，仅改权重策略

**任务 3.3：单元测试**（1.5 小时）
- 新增 2 个测试验证 SOCP DCP 合规性
- 修改 6 个失败测试的预期值

**任务 3.4：集成测试**（1 小时）
```bash
pytest tests/test_trajectory_opt.py::test_hover_path -v
pytest tests/test_trajectory_opt.py::test_comm_constraint -v
```

---

#### 【步骤 4】逐个测试修复（6 小时）

**修复顺序**（基础→高级）：
| 测试 | 问题 | 修复工作 | 工作量 |
|------|------|--------|-------|
| T3 | 端点可达性（独立） | 无 | 0 |
| T1 | 悬停路径 | 删除非 DCP 约束 | 30min |
| T2 | 速度约束验证 | 验证约束兼容 | 20min |
| T7 | 空卸载（无通信） | 验证条件路径 | 15min |
| T4 | 通信约束影响 | 验证 SOCP 趋势 | 45min |
| T8 | 不安全初始状态 | slack 权重调整 | 40min |
| T5 | 安全分离 | SCA 线性化验证 | 50min |
| T10 | 求解器回退 | 验证 CLARABEL/ECOS/SCS | 25min |
| T6/T9/T11/T12 | 各种组合场景 | 综合验证 | 60min |

**预计时间**：总计 6 小时

---

#### 【步骤 5】整体集成验证（2.5 小时）

**验证套件**：
```bash
# 确保 propulsion & resource_alloc 不受影响
pytest tests/test_propulsion.py tests/test_resource_alloc.py -v

# trajectory_opt 所有 12 个测试通过
pytest tests/test_trajectory_opt.py -v

# 其他 Edge UAV 模块
pytest tests/test_evaluator.py tests/test_hs_individual_edge_uav.py -v
```

**成功标准**：
- [ ] 62+ 个测试通过（100% 覆盖 propulsion/resource_alloc/trajectory_opt）
- [ ] 无回归（propulsion/resource_alloc 的 14 个测试仍全部通过）

---

#### 【步骤 6】完整管道验证（3.5 小时）

**命令**：
```bash
python testEdgeUav.py --popsize=3 --iteration=3 --run-dir discussion/phase6_step3_test/
python analyze_results.py --run-dir discussion/phase6_step3_test/
```

**验证项**：
- [ ] 生成 population_result_*.json（3 代 × 3 个体 = 9 个文件）
- [ ] ≥1 个体 llm_status == "ok" 且 used_default_obj == False
- [ ] ≥1 个体 feasible == True
- [ ] 运行时间 < 10 分钟

---

#### 【步骤 7】最终报告生成（1.5 小时）

**输出目录**：`discussion/phase6_step3_final_YYYYMMDD/`

**文件清单**：
```
├── REPORT_Phase6_Step3.md           # 总结（500 字）
├── CONSTRAINTS_FORMULATION.md       # SOCP 推导（200 字）
├── solver_diagnostics.json          # 性能指标
└── test_results_summary.txt         # 12/12 通过汇总
```

---

## 【关键依赖与风险】

### 关键文件（必须修改）
- `edge_uav/model/trajectory_opt.py`：主要修改
- `tests/test_trajectory_opt.py`：测试更新（6 个）
- `edge_uav/model/resource_alloc.py`：无需改动（参考）
- `edge_uav/model/propulsion.py`：无需改动（参考）

### 关键依赖（不能破坏）
- `heuristics/hsIndividualEdgeUav.py`：调用 trajectory_opt，输入输出接口不能变
- Phase⑤ LLM 框架：不涉及

### 关键风险与回滚

| 风险 | 症状 | 回滚策略 |
|------|------|--------|
| SOCP 求解器超时 | status == "unknown" | 降低活动卸载数，改用 SCS 求解器 |
| 不可行约束 | status == "infeasible" | 检查 s 的下界约束，调整 τ_comm 解释 |
| 轨迹质量下降 | obj_value > 之前 20% | 增加 SCA 迭代次数，调整 slack 权重 |
| 与 resource_alloc 不兼容 | 运行时崩溃 | 检查 f_fixed 输入格式（应无变化） |

**回滚检查清单**：
- [ ] 执行 `git commit -m "checkpoint: before Phase6-Step3-SOCP"` 保存当前状态
- [ ] 运行 `pytest tests/ -v --tb=short > baseline.log` 记录基准
- [ ] 修改后若任何测试失败 >30 分钟，执行 `git reset --hard HEAD~1` 恢复

---

## 【工作量与日程】

### 总工作量：25-26 小时

| 步骤 | 内容 | 小时 |
|------|------|------|
| 1 | 通信约束 SOCP 建模 | 3.5 |
| 2 | 安全分离 SCA 改进 | 2.5 |
| 3 | 代码实现 & 单元测试 | 5.5 |
| 4 | 逐个测试修复 | 6.0 |
| 5 | 整体集成验证 | 2.5 |
| 6 | 管道验证 | 3.5 |
| 7 | 报告生成 | 1.5 |
| **总计** | | **25-26** |

### 建议日程
- **Day 1**：步骤 1-2（6 小时）
- **Day 2**：步骤 3-4（11 小时）
- **Day 3**：步骤 5-7（8-9 小时）

---

## 【执行入口检查】

在开始前，确认以下：
- [ ] Git 当前分支：master，状态：clean（无未提交变更）
- [ ] 当前测试基准：`pytest tests/test_trajectory_opt.py --tb=no` → 1 pass, 11 fail
- [ ] 环境：cvxpy ≥ 1.4.0，CLARABEL 求解器可用
- [ ] 理解本计划的数学基础（特别是 SOCP 形式）

---

## 【后续里程碑】

完成此计划后：
- ✅ Phase⑥ Step3 完成：轨迹优化模块可用
- 🔲 Phase⑥ Step4：完整 HS + BCD 集成验证
- 🔲 论文第 3 章：用修复后的数值结果
- 🔲 提交前最终验证：对标 Phase⑤ G 的运行结果

---

**计划版本**：1.0 (Final)
**最后更新**：2026-03-25 12:30
**状态**：✅ Ready for execution
**优先级**：🔴 Blocking Phase④ milestone
