# 仿真参数说明（Simulation Setup 写作参考）

> 本文档整理所有参数的**公式符号 ↔ 代码名 ↔ 默认值**映射，
> 并区分"数学模型参数"与"场景生成参数"，供论文 Simulation Setup 一节写作使用。

---

## 1. 参数分层说明

项目中的参数分为两层：

| 层次 | 作用 | 论文对应位置 |
|------|------|-------------|
| **模型参数** | 出现在优化公式中，定义问题本身 | Problem Formulation 各公式的符号 |
| **生成参数** | 控制仿真场景如何随机产生，公式中不出现 | Simulation Setup 的参数表 + 文字描述 |

公式层说"给定任务 $U_i^t = (D_i^l, D_i^r, F_i, \tau_i)$"；
生成层说"$D_i^l$ 从 $[5, 50]$ Mbits 均匀采样"。

---

## 2. 模型参数（出现在公式中）

### 2.1 物理环境与时间

| 公式符号 | 代码名 | 默认值 | 单位 | 说明 | 出处 |
|----------|--------|--------|------|------|------|
| $\delta$ | `delta` | 1.0 | s | 时隙长度 | §5 公式(3) |
| $T$ | `T` | 20 | — | 总时隙数 | §5 |
| $x^{\max}$ | `x_max` | 1000 | m | 空域 x 边界 | §5 公式(4a) |
| $y^{\max}$ | `y_max` | 1000 | m | 空域 y 边界 | §5 公式(4b) |
| $H$ | `H` | 100 | m | UAV 固定飞行高度 | §5 |

### 2.2 通信参数

| 公式符号 | 代码名 | 默认值 | 单位 | 说明 | 出处 |
|----------|--------|--------|------|------|------|
| $B_{i,j}$ | `B_up` | 1 | MHz | 上行带宽 | §2 公式(5) |
| $B_{j,i}^{\mathrm{down}}$ | `B_down` | 1 | MHz | 下行带宽 | §2 公式(6) |
| $P_i$ | `P_i` | 0.5 | W | TD 发射功率 | §2 公式(5) |
| $P_j$ | `P_j` | 1.0 | W | UAV 发射功率 | §2 公式(6) |
| $N_0$ | `N_0` | $10^{-10}$ | W | 噪声功率 | §2 公式(5)(6) |
| $\rho_0$ | `rho_0` | $10^{-5}$ | — | 1m 参考信道增益 | 信道模型 |

### 2.3 能耗系数

| 公式符号 | 代码名 | 默认值 | 单位 | 说明 | 出处 |
|----------|--------|--------|------|------|------|
| $\gamma_i$ | `gamma_i` | $10^{-28}$ | — | TD 芯片能耗系数 | §6 公式(19) |
| $\gamma_j$ | `gamma_j` | $10^{-28}$ | — | 边缘节点芯片能耗系数 | §6 公式(19) |

### 2.4 UAV 推进模型

| 公式符号 | 代码名 | 默认值 | 单位 | 说明 | 出处 |
|----------|--------|--------|------|------|------|
| $v_U^{\max}$ | `v_U_max` | 30 | m/s | 最大飞行速度 | §5 公式(4d) |
| $v^{\mathrm{tip}}$ | `v_tip` | 120 | m/s | 桨尖速度 | §6 公式(18) |
| $\eta_1$ | `eta_1` | 79.86 | W | 叶片剖面功率 | §6 公式(18) |
| $\eta_2$ | `eta_2` | 88.63 | W | 诱导功率 | §6 公式(18) |
| $\eta_3$ | `eta_3` | 0.0151 | — | 机身阻力比 | §6 公式(18) |
| $\eta_4$ | `eta_4` | 0.0048 | — | 空气密度系数 | §6 公式(18) |

### 2.5 UAV 硬件与约束

| 公式符号 | 代码名 | 默认值 | 单位 | 说明 | 出处 |
|----------|--------|--------|------|------|------|
| $E_j^{\max}$ | `E_max` | 5000 | J | UAV 能量预算 | §7 公式(20) |
| $f^{\max}$ | `f_max` | 5×10⁹ | Hz | UAV 最大 CPU 频率 | 约束 |
| $d_U^{\mathrm{safe}}$ | `d_U_safe` | 50 | m | UAV 间安全距离 | §5 公式(4f) |

### 2.6 目标函数权重

| 公式符号 | 代码名 | 默认值 | 说明 | 出处 |
|----------|--------|--------|------|------|
| $\alpha$ | `alpha` | 1.0 | 时延成本权重 | §7 公式(20) 第1项 |
| $\gamma$ | `gamma_w` | 1.0 | 计算能耗成本权重 | §7 公式(20) 第2项 |
| $\lambda$ | `lambda_w` | 1.0 | 飞行能耗成本权重 | §7 公式(20) 第3项 |

### 2.7 任务属性（公式中作为给定输入）

| 公式符号 | 说明 | 公式中角色 |
|----------|------|-----------|
| $D_i^l$ | 上行数据量 | 任务参数（给定常数） |
| $D_i^r$ | 下行数据量 | 任务参数（给定常数） |
| $F_i$ | CPU 周期需求 | 任务参数（给定常数） |
| $\tau_i$ | 截止时间 | 时延约束上界 |
| $\zeta_i^t$ | 设备 $i$ 在时隙 $t$ 是否活跃 | 0/1 已知指示量 |
| $\mathbf{q}_j^I, \mathbf{q}_j^F$ | UAV 起/止位置 | 边界条件 |

> 以上参数在公式中是**已知输入**，不是优化变量。
> 公式不关心它们怎么取值，但仿真实验需要具体的生成方式——见下节。

---

## 3. 生成参数（公式中不出现，仅用于仿真）

这些参数控制"如何随机生成上述给定输入"，论文中放在 Simulation Setup 的参数表里。

### 3.1 任务属性采样范围

| 代码名 | 默认值 | 单位 | 对应公式符号 | 说明 |
|--------|--------|------|-------------|------|
| `D_l_min` | 5×10⁶ | bits | $D_i^l$ 的下界 | 上行数据量 ∼ Uniform[5, 50] Mbits |
| `D_l_max` | 5×10⁷ | bits | $D_i^l$ 的上界 | |
| `D_r_min` | 1×10⁵ | bits | $D_i^r$ 的下界 | 下行数据量 ∼ Uniform[0.1, 1] Mbits |
| `D_r_max` | 1×10⁶ | bits | $D_i^r$ 的上界 | |
| `F_min` | 1×10⁸ | cycles | $F_i$ 的下界 | CPU 周期 ∼ Uniform[10⁸, 5×10⁹] |
| `F_max` | 5×10⁹ | cycles | $F_i$ 的上界 | |
| `tau_min` | 0.5 | s | $\tau_i$ 的下界 | 截止时间 ∼ Uniform[0.5, 2.0] s |
| `tau_max` | 2.0 | s | $\tau_i$ 的上界 | |

### 3.2 终端设备硬件

| 代码名 | 默认值 | 单位 | 说明 |
|--------|--------|------|------|
| `f_local_default` | 1×10⁹ | Hz | TD 本地 CPU 频率上限（公式中 $f_i^t$ 的物理上界） |

### 3.3 活跃时间窗（$\zeta_i^t$ 的生成方式）

| 代码名 | 默认值 | 说明 |
|--------|--------|------|
| `active_mode` | `contiguous_window` | 每个 TD 在 $T$ 个时隙中选一段连续窗口为活跃期 |
| `active_window_min` | 5 | 活跃窗口最小长度（时隙数） |
| `active_window_max` | 15 | 活跃窗口最大长度（时隙数） |

> **物理含义**：TD 不是全程在线，只在某段时间有计算需求。
> 窗口长度 ∼ Uniform[5, 15] 时隙，起始位置随机。
> 窗口内 $\zeta_i^t = 1$，窗口外 $\zeta_i^t = 0$。

### 3.4 场景规模与拓扑

| 代码名 | 默认值 | 对应公式符号 | 说明 |
|--------|--------|-------------|------|
| `numTasks` | 10 | $\|\mathcal{I}\|$ | 终端设备数量 |
| `numUAVs` | 3 | $\|\mathcal{U}\|$ | UAV 数量 |
| `depot_x` | 500 | $\mathbf{q}_j^I$ 的 x 分量 | 基站/起止位置 x 坐标 (m) |
| `depot_y` | 500 | $\mathbf{q}_j^I$ 的 y 分量 | 基站/起止位置 y 坐标 (m) |
| `scenario_seed` | 42 | — | 随机种子（可复现性） |

### 3.5 TD 位置生成

代码中 TD 位置从 $[0, x^{\max}] \times [0, y^{\max}]$ 均匀采样（不作为单独参数，直接复用 `x_max`, `y_max`）。

---

## 4. 论文 Simulation Setup 草稿

以下为建议的论文写法，可直接作为初稿使用。

### 参数表（Table X: Simulation Parameters）

| Parameter | Symbol | Value |
|-----------|--------|-------|
| Number of TDs | $\|\mathcal{I}\|$ | 10 |
| Number of UAVs | $\|\mathcal{U}\|$ | 3 |
| Time horizon | $T$ | 20 slots |
| Slot duration | $\delta$ | 1 s |
| Area size | $x^{\max} \times y^{\max}$ | 1000 × 1000 m² |
| UAV altitude | $H$ | 100 m |
| Uplink/downlink bandwidth | $B$ | 1 MHz |
| TD transmit power | $P_i$ | 0.5 W |
| UAV transmit power | $P_j$ | 1.0 W |
| Noise power | $N_0$ | $10^{-10}$ W |
| Reference channel gain | $\rho_0$ | $10^{-5}$ |
| Chip energy coefficient | $\gamma_i, \gamma_j$ | $10^{-28}$ |
| Max UAV speed | $v_U^{\max}$ | 30 m/s |
| Rotor tip speed | $v^{\mathrm{tip}}$ | 120 m/s |
| Propulsion params | $\eta_1, \eta_2, \eta_3, \eta_4$ | 79.86, 88.63, 0.0151, 0.0048 |
| UAV energy budget | $E_j^{\max}$ | 5000 J |
| UAV max CPU freq | $f^{\max}$ | 5 GHz |
| Inter-UAV safe distance | $d_U^{\mathrm{safe}}$ | 50 m |
| Task input data | $D_i^l$ | Uniform[5, 50] Mbits |
| Task output data | $D_i^r$ | Uniform[0.1, 1] Mbits |
| CPU cycles per task | $F_i$ | Uniform[$10^8$, $5 \times 10^9$] cycles |
| Task deadline | $\tau_i$ | Uniform[0.5, 2.0] s |
| TD local CPU freq | $f_i^{\max}$ | 1 GHz |
| Active window length | — | Uniform[5, 15] slots |
| Cost weights | $\alpha, \gamma, \lambda$ | 1.0, 1.0, 1.0 |

### 正文段落

> We consider a 1 km × 1 km area where $|\mathcal{I}| = 10$ ground terminal devices (TDs) are uniformly distributed and served by $|\mathcal{U}| = 3$ UAVs flying at a fixed altitude $H = 100$ m. The planning horizon consists of $T = 20$ time slots, each of duration $\delta = 1$ s. All UAVs depart from and return to a central depot at (500, 500) m.
>
> Task parameters are independently and uniformly sampled: input data size $D_i^l \sim \mathcal{U}[5, 50]$ Mbits, output data size $D_i^r \sim \mathcal{U}[0.1, 1]$ Mbits, computational demand $F_i \sim \mathcal{U}[10^8, 5 \times 10^9]$ cycles, and deadline $\tau_i \sim \mathcal{U}[0.5, 2.0]$ s. Each TD is active within a random contiguous time window of length uniformly drawn from [5, 15] slots; outside this window, the activity indicator $\zeta_i^t = 0$. The TD local CPU frequency is set to 1 GHz.
>
> The UAV propulsion model follows [ref], with parameters listed in Table X. The remaining communication and energy parameters are summarized in Table X.

---

## 5. 已知问题与调参备注

- **tau 偏紧**：默认 `tau_max = 2.0s` 下 Smoke Test 显示约 90% 任务不可行。后续实验可能需要增大 `tau_max` 或增大 `B_up/B_down`。
- **权重均为 1.0**：$\alpha = \gamma = \lambda = 1.0$ 意味着三项成本等权，实际论文可能需要根据量级做归一化或调整权重。
- **ComputeTask.__eq__ 忽略 active 和 f_local**：测试比对时用 `to_dict()` 绕过。
