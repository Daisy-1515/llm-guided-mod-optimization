"""
Level-1 目标函数规范源（Canonical Source）

本模块统一定义 Level-1 目标函数的数学、Python 和 Harmony Search 三种形式，
确保 offloading.py / base_prompt.py / hsIndividualEdgeUav.py 三处同步应用。

修复历程：
  - 2026-03-30：新建本文件，解决三处目标函数分散问题
  - 2026-03-31：移除 drop 失败机制，回退到纯 cost1+cost2 公式
"""

# ===== 第 1 部分：数学规范和完整推导 =====

CANONICAL_OBJECTIVE_V1 = r"""
标准 Level-1 目标函数（版本 1.1，2026-03-31）

定义：
    minimize: Σ_{i∈I} Σ_{t∈T} [ α·D̂_{i,⊙}(x) / τ_i
                                 + γ_w·Ê_{comp}(x,f_edge) / E_{max,edge} ]

其中：
    - x_{i,i}^t, x_{i,j}^t: Layer-1 分配决策变量
    - D̂_{i,⊙}(x): 执行时延（本地或卸载）
    - Ê_{comp}: 计算能耗

    - α = config.alpha（时延权重，默认 1.0）
    - γ_w = config.gamma_w（能耗权重，默认 1.0）

约束：
    同时参见 offloading.py 的 L1-C1 ~ L1-C3

语义：每个任务在所有活跃时隙中恰好分配一次（本地或卸载到某 UAV），
超时通过 D/τ > 1 自然反映在目标值中。
"""


# ===== 第 2 部分：Harmony Search 字符串形式（供 exec() 编译）=====

DEFAULT_OBJECTIVE_CODE = """
# 标准 Level-1 目标函数（Harmony Search 兼容格式）
# 在 hsIndividualEdgeUav.py 中使用此代码作为默认目标
# 对应文档: edge_uav/model/objectives.py / 第 2 部分

cost = 0.0

# 时延项
for i in range(n_tasks):
    for t in range(n_slots):
        if i not in active_tasks or t not in active_tasks[i]:
            continue

        # 本地执行时延
        if (i, t) in x_local:
            cost += alpha * D_local[i][t] / tau[i] * x_local[(i, t)]

        # 卸载执行时延
        for j in range(n_uavs):
            if (i, j, t) in x_offload:
                cost += alpha * D_offload[i][j][t] / tau[i] * x_offload[(i, j, t)]

# 能耗项
for j in range(n_uavs):
    for i in range(n_tasks):
        for t in range(n_slots):
            if (i, j, t) in x_offload:
                cost += gamma_w * E_comp[j][i][t] / E_max[j] * x_offload[(i, j, t)]

objective_value = cost
"""


# ===== 第 3 部分：纯 Python 实现（用于诊断和非 Gurobi 评估）=====

def compute_objective_value(
    assignments: dict,  # {(i,t): ("local"|"offload", j_opt or None)}
    D_local: dict,      # [i][t]
    D_offload: dict,    # [i][j][t]
    E_comp: dict,       # [j][i][t]
    tau_list: dict,     # [i]
    E_max_list: dict,   # [j]
    alpha=1.0,
    gamma_w=1.0,
) -> float:
    """
    纯 Python 计算目标函数值。
    用于验证、诊断或离线评估。

    参数
    ----------
    assignments : dict
        {(i,t): ("local", None) | ("offload", j)}
    D_local : dict
        D_local[i][t] — 本地执行时延
    D_offload : dict
        D_offload[i][j][t] — 卸载执行时延
    E_comp : dict
        E_comp[j][i][t] — 计算能耗
    tau_list : dict
        tau_list[i] — 任务截止期
    E_max_list : dict
        E_max_list[j] — UAV 能量预算
    alpha : float
        时延权重
    gamma_w : float
        能耗权重

    返回
    -------
    float
        目标函数值
    """
    cost = 0.0

    for (i, t), (mode, j_opt) in assignments.items():
        if mode == "local":
            delay = D_local[i][t]
            tau_i = float(tau_list[i])
            cost += alpha * delay / tau_i
        elif mode == "offload":
            delay = D_offload[i][j_opt][t]
            energy = E_comp[j_opt][i][t]
            tau_i = float(tau_list[i])
            E_max_j = float(E_max_list[j_opt])
            cost += alpha * delay / tau_i
            cost += gamma_w * energy / E_max_j

    return cost


# ===== 第 4 部分：文档参考 =====

CONSTRAINT_REFERENCE = """
约束文档参考（见 offloading.py）

L1-C1：分配约束（按 i 聚合）
    对于每个任务 i：
    sum_t x_local[i,t] + sum_j sum_t x_offload[i,j,t] == 1

    说明：每个任务在所有活跃时隙中恰好分配一次（本地或卸载到某 UAV）。

L1-C3（UAV 承载量约束，可选）：
    sum_i x_offload[i,j,t] ≤ N_max[j]
"""
