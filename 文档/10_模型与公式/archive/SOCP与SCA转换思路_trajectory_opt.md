---
⚠️ **归档文档** — 不再活跃维护

**状态**：存档于 archive/ 目录
**最后更新**：2026-03-10
**理由**：历史设计分析文档，对应 trajectory_opt.py 实现；后续维护直接在代码注释中进行
**当前参考**：[edge_uav/model/trajectory_opt.py](../../edge_uav/model/trajectory_opt.py) 代码注释 + [公式与两层解耦整合版_最新版_2026-03-24.md](公式与两层解耦整合版_最新版_2026-03-24.md)

---

# `trajectory_opt.py` 中 SOCP 与 SCA 的转换思路

## 1. 文档目的

本文说明 `edge_uav/model/trajectory_opt.py` 中两类关键处理：

1. 为什么通信时延约束要先做近似，再改写成 SOCP 友好的形式。
2. 为什么安全距离约束采用 SCA 线性化，并通过 `slack` 做带罚放松。

本文只基于本地代码实现分析，未使用外部检索。

相关代码入口：

- `solve_trajectory_sca(...)`
- `_build_sca_subproblem(...)`
- `_add_communication_delay_socp_constraint(...)`
- `_add_safety_separation_socp_constraint(...)`
- `_rate_lower_bound_expr(...)`

---

## 2. 先区分三个概念

在这份实现里，容易混淆的是下面三件事：

### 2.1 SOCP 重写

SOCP 重写指的是：在不改变约束含义的前提下，引入辅助变量，把约束写成二阶锥规划可接受的形式。

如果这是严格等价变形，那么约束的严格性没有变化，只是表达方式变了。

### 2.2 SCA 近似

SCA, Successive Convex Approximation，指的是：针对原本非凸或不满足 DCP 规则的部分，在某个参考点附近构造一阶近似，把当前子问题改成凸问题。

这一步通常不是全局等价，而是局部近似。是否“更严格”，取决于你构造的是上界还是下界。

### 2.3 Slack 放松

`slack` 的作用是允许某条约束在当前子问题里被临时违反，但违反多少会被加入目标函数惩罚。

因此：

- `slack = 0` 时，约束按近似式严格执行。
- `slack > 0` 时，约束被显式放松。

所以“约束是不是变松了”这个问题，必须分别看：

- 是 SOCP 等价改写导致的，还是
- 是 SCA 近似导致的，还是
- 是 `slack` 明确允许违约导致的。

---

## 3. `trajectory_opt.py` 的整体求解结构

主流程是一个典型的 SCA 外循环 + 凸子问题内循环：

1. 先给定参考轨迹 `q_ref`。
2. 在 `q_ref` 附近构造一个凸子问题 `_build_sca_subproblem(...)`。
3. 用 CVXPY 求解这个子问题。
4. 用解出的新轨迹更新 `q_ref`。
5. 重复直到收敛或达到最大迭代次数。

也就是说，真正进入求解器的不是原始非凸问题，而是“在当前参考点附近得到的凸近似问题”。

---

## 4. 通信时延约束：先做速率下界，再做 SOCP 改写

### 4.1 原始物理形式

代码注释给出的通信时延结构可写成：

\[
\text{Delay}
=
\frac{2\sqrt{H^2 + \|q_j^t - w_i\|_2^2}}{r(H^2 + \|q_j^t - w_i\|_2^2)}
\le \tau_{\text{comm\_budget}}
\]

其中：

- \(q_j^t\) 是 UAV \(j\) 在时隙 \(t\) 的平面位置
- \(w_i\) 是任务或回传基站位置
- \(H\) 是固定高度
- \(r(z)\) 是 Shannon 速率函数

代码里采用的中间变量是：

\[
z = H^2 + \|q_j^t - w_i\|_2^2
\]

于是原式等价于：

\[
\frac{2\sqrt{z}}{r(z)} \le \tau_{\text{comm\_budget}}
\]

### 4.2 为什么原式不能直接放进 CVXPY

难点不在单独的 `sqrt(z)` 或单独的 `1 / r(z)`，而在它们的组合：

\[
\sqrt{z}\cdot \frac{1}{r(z)}
\]

这里同时包含：

- 距离项的平方根
- 速率项对距离平方的非线性依赖
- 两个非常量表达式之间的乘除关系

这不满足 CVXPY 的 DCP 组合规则，因此不能按原式直接建模。

### 4.3 第一步：对速率函数做一阶下界近似

代码中的 `_rate_lower_bound_expr(...)` 对下面这个函数在参考点 `z_ref` 做一阶 Taylor 展开：

\[
r(z)=\frac{B}{\ln 2}\ln\left(1+\frac{\beta}{z}\right)
\]

在 `trajectory_opt.py` 里，构造的是：

\[
r_{\text{safe}}(z)
=
r(z_{\text{ref}})
+
r'(z_{\text{ref}})(z-z_{\text{ref}})
\]

并把它作为 `rate_safe` 使用。

代码含义是：用 `rate_safe` 代替真实速率 `r(z)`，但这里代替的是一个下界。

即：

\[
r_{\text{safe}}(z) \le r(z)
\]

#### 为什么这是“保守”而不是“放松”

原约束是：

\[
\frac{2\sqrt{z}}{r(z)} \le \tau
\]

实现里改成：

\[
\frac{2\sqrt{z}}{r_{\text{safe}}(z)} \le \tau
\]

由于 `rate_safe` 更小，分母更小，左边更大，因此更难满足。

所以这一步通常是保守近似，不是放松。

换句话说：

- 如果某个解满足近似约束，它更有希望也满足原约束。
- 但反过来不一定成立，因为原问题里可能有些可行点被这条下界约束排掉了。

这正是 SCA 常见的“可行域内收”特征。

### 4.4 第二步：把距离项写成 SOCP epigraph

在有了 `rate_safe` 之后，代码仍然不会直接写

\[
\frac{2\sqrt{H^2 + \|pos\_diff\|_2^2}}{rate\_safe} \le \tau
\]

而是引入辅助变量 \(s\)，写成：

\[
\left\|
\begin{bmatrix}
H \\
dx \\
dy
\end{bmatrix}
\right\|_2
\le s
\]

\[
2s \le \tau \cdot rate_{\text{safe}}
\]

其中 `pos_diff = [dx, dy]`。

第一条约束表示：

\[
\sqrt{H^2 + dx^2 + dy^2} \le s
\]

也就是距离项的 epigraph 形式。它是标准二阶锥约束。

### 4.5 为什么这里可以认为是等价改写

注意，这里的“等价”是针对已经替换成 `rate_safe` 的近似子问题而言。

一旦我们接受近似子问题：

\[
\frac{2\sqrt{H^2+\|pos\_diff\|_2^2}}{rate_{\text{safe}}}\le \tau
\]

那么再引入 \(s\) 写成

\[
\|[H, dx, dy]\|_2 \le s,\quad 2s \le \tau rate_{\text{safe}}
\]

本质上只是把平方根项移入辅助变量，便于 CVXPY 按 SOCP 规则识别。

因此：

- `rate_safe` 的引入是近似。
- `s` 的引入是对这个近似子问题的等价凸表示。

不能把这两步混成一句“SOCP 放松了原约束”。

### 4.6 代码里的额外数值保护

在 `_add_communication_delay_socp_constraint(...)` 中还有一条：

\[
rate_{\text{safe}} \ge 10^{-12}
\]

它的作用不是改变物理模型，而是避免数值上出现分母接近零导致的不稳定。

这属于数值安全保护。

---

## 5. 安全距离约束：不是 SOCP 等价重写，而是 SCA 线性化

### 5.1 原始约束

若两架 UAV 在时隙 \(t\) 的位置分别为 \(q_j^t, q_k^t\)，安全距离要求通常写成：

\[
\|q_j^t - q_k^t\|_2^2 \ge d_{\text{safe}}^2
\]

或者等价地：

\[
\|q_j^t - q_k^t\|_2 \ge d_{\text{safe}}
\]

这个约束的可行域是“两个点之间必须离得足够远”，本质上是非凸的。

原因在于：

- “距离不超过某值”是凸集；
- “距离至少达到某值”一般不是凸集。

因此它不能直接作为凸子问题约束。

### 5.2 SCA 线性化的参考点

代码在参考轨迹 `q_ref` 上定义：

\[
\bar d = q_{j,\text{ref}}^t - q_{k,\text{ref}}^t
\]

把当前变量写作：

\[
\Delta q = q_j^t - q_k^t
\]

然后使用一阶线性下界：

\[
\|\Delta q\|_2^2
\ge
2\bar d^T \Delta q - \|\bar d\|_2^2
\]

于是原来的非凸约束

\[
\|\Delta q\|_2^2 \ge d_{\text{safe}}^2
\]

被替换为仿射约束：

\[
2\bar d^T \Delta q - \|\bar d\|_2^2 \ge d_{\text{safe}}^2
\]

这正是代码中的核心形式。

### 5.3 为什么它是保守近似

因为对凸函数 \(f(x)=\|x\|_2^2\)，其一阶 Taylor 展开是全局下界：

\[
f(x)\ge f(x_0)+\nabla f(x_0)^T(x-x_0)
\]

所以如果线性下界已经大于等于 \(d_{\text{safe}}^2\)，那么真实的平方距离一定也大于等于 \(d_{\text{safe}}^2\)。

因此：

- 线性化可行，则原约束也可行。
- 原约束可行，不代表线性化约束一定可行。

所以这一步也是保守近似，而不是放松。

### 5.4 为什么这里不是 SOCP 变换

虽然整个子问题最终仍是“SOCP-compatible”的，但安全距离这部分本身不是通过引入锥约束得到的。

它本质上是：

- 把非凸约束替换成仿射下界约束；
- 从而让整个子问题保持凸。

所以更准确地说：

- 通信约束里有“SOCP 表达”。
- 安全距离约束里主要是“SCA 线性化”。

---

## 6. Slack 的作用：显式允许违约，但要付代价

### 6.1 代码中的形式

在 `_add_safety_separation_socp_constraint(...)` 中，安全距离线性化约束实际写成：

\[
2\bar d^T \Delta q - \|\bar d\|_2^2 + \delta_{jk}^t \ge d_{\text{safe}}^2
\]

其中：

\[
\delta_{jk}^t \ge 0
\]

并且在目标函数中加入罚项：

\[
\rho \sum_{j,k,t}\delta_{jk}^t
\]

代码里对应的是 `safe_slack_penalty * slack_var`。

### 6.2 这一步为什么是“放松”

如果没有 `slack`，那么安全距离线性化约束必须严格满足。

加上 `slack` 之后，即便某个时隙下两架 UAV 没有达到要求的分离度，只要用正的 `slack` 把缺口补上，子问题仍然可以求解。

因此：

- 这是显式放松，不是近似副作用。
- 放松是受控的，因为 `slack` 越大，目标函数代价越高。

### 6.3 为什么这里需要 `slack`

SCA 在早期迭代常见的问题是：

- 参考点本身可能不安全；
- 线性化可行域可能过窄；
- 若完全不允许违约，子问题可能直接 infeasible。

加入 `slack` 的目的是给算法留出“从不可行参考点逐步修正回可行轨迹”的空间。

因此它更像是一个数值与收敛稳定性工具。

---

## 7. 一张表看清：等价重写、保守近似、显式放松

| 对象 | 代码位置 | 性质 | 是否更松 |
|---|---|---|---|
| `rate_safe` 代替真实速率 `r(z)` | `_rate_lower_bound_expr(...)` | SCA 一阶下界，保守近似 | 否，通常更严格 |
| 距离项引入辅助变量 `s` | `_add_communication_delay_socp_constraint(...)` | 对近似子问题的等价 SOCP 表达 | 否，不变 |
| 安全距离的一阶线性化 | `_add_safety_separation_socp_constraint(...)` | SCA 仿射下界，保守近似 | 否，通常更严格 |
| 安全距离 `slack_var >= 0` | `_add_safety_separation_socp_constraint(...)` | 带罚显式放松 | 是，可控地变松 |
| `rate_safe >= 1e-12` | `_add_communication_delay_socp_constraint(...)` | 数值保护约束 | 不属于模型放松 |

---

## 8. 对“重写后是不是不严格了”的准确回答

更准确的说法应该是：

### 8.1 通信时延约束

通信时延约束经历了两步：

1. 用 `rate_safe` 替代真实速率，这一步是保守近似。
2. 把近似后的约束写成 SOCP 形式，这一步是等价重写。

因此不能简单说“SOCP 重写后不严格了”。真正改变严格性的，是前面的 SCA 速率下界，而它通常使约束更保守。

### 8.2 安全距离约束

安全距离约束本身是非凸的，所以采用 SCA 线性化。线性化本身通常也是保守的。

但这里又叠加了 `slack`，所以最终求解子问题时，安全距离实际上被“带罚放松”了。

因此这部分确实可能比“无 slack 的严格安全距离约束”更松。

### 8.3 总结成一句话

- 通信约束：`SCA 保守近似 + SOCP 等价表达`。
- 安全距离约束：`SCA 保守线性化 + slack 带罚放松`。

所以“重写后不严格了”只对带 `slack` 的部分成立，不应归因于 SOCP 本身。

---

## 9. 代码映射

下面给出文档结论与代码的直接对应关系：

- SCA 主循环：`edge_uav/model/trajectory_opt.py` 中 `solve_trajectory_sca(...)`
- SCA 子问题构建：`edge_uav/model/trajectory_opt.py` 中 `_build_sca_subproblem(...)`
- 通信约束 SOCP 表达：`edge_uav/model/trajectory_opt.py` 中 `_add_communication_delay_socp_constraint(...)`
- 安全距离线性化与 `slack`：`edge_uav/model/trajectory_opt.py` 中 `_add_safety_separation_socp_constraint(...)`
- Shannon 速率一阶下界：`edge_uav/model/trajectory_opt.py` 中 `_rate_lower_bound_expr(...)`

如果后续要继续扩展，建议把这份文档和 `文档/10_模型与公式/公式20_凸性分析.md` 配合阅读：

- 前者解决“代码里具体怎么重写”
- 后者更适合解释“哪些公式为什么凸/非凸”

---

## 10. 一个最简判断框架

以后遇到类似问题，可以直接按下面三步判断：

1. 先问：只是换写法，还是换了函数本身。
2. 再问：近似用的是上界还是下界。
3. 最后问：有没有额外 `slack` 允许违约。

如果答案分别是：

- “只是换写法” -> 通常是等价重写。
- “用了下界来替代分母里的真实量” -> 通常更保守。
- “引入了非负 slack 并加罚项” -> 明确是带罚放松。

这三层拆开后，`trajectory_opt.py` 的建模思路就比较清楚了。
