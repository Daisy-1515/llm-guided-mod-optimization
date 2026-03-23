"""Edge UAV 计算卸载 — Level-1 BLP 预计算输入模块。

根据 Level-2 的 UAV 轨迹与频率分配快照，预先计算 OffloadingModel 所需的三组常量：
  - D_hat_local[i][t]      本地执行时延
  - D_hat_offload[i][j][t]  远程卸载总时延
  - E_hat_comp[j][i][t]     边缘计算能耗

设计文档: 文档/precompute_analysis.md §7
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, Mapping

from config.config import configPara
from edge_uav.data import ComputeTask, UAV, EdgeUavScenario

_LN2 = math.log(2.0)


# =====================================================================
# 类型别名 — 与 OffloadingModel 的嵌套 dict 接口一致
# =====================================================================

Scalar2D = dict[int, dict[int, float]]                    # [i][t] 或 [j][t]
Scalar3D = dict[int, dict[int, dict[int, float]]]         # [i][j][t] 或 [j][i][t]
Trajectory2D = dict[int, dict[int, tuple[float, float]]]  # q[j][t] = (x, y)

Level2Source = Literal["init", "prev_bcd", "history_avg", "custom"]
InitPolicy = Literal["paper_default", "custom"]


# =====================================================================
# 数据结构
# =====================================================================

@dataclass(frozen=True)
class PrecomputeParams:
    """从 configPara 提取的预计算所需物理参数。

    frozen=True 保证不可变，可安全在 BCD 迭代间复用。
    """

    # ---- 物理参数 ----
    H: float          # UAV 飞行高度 (m)
    B_up: float       # 上行带宽 (Hz)
    B_down: float     # 下行带宽 (Hz)
    P_i: float        # 终端发射功率 (W)
    P_j: float        # UAV 发射功率 (W)
    N_0: float        # 总噪声功率 (W)，非功率谱密度(PSD)，上下行共用
    rho_0: float      # 1m 参考信道增益
    gamma_j: float    # 边缘节点芯片能耗系数

    # ---- 数值保护 ----
    eps_dist_sq: float = 1e-12   # 距离平方下限，防 g → ∞
    eps_rate: float = 1e-12      # 速率下限，防除零
    eps_freq: float = 1e-12      # 频率下限，防除零
    tau_tol: float = 1e-9        # tau 比较容差
    big_m_delay: float = 1e6     # BIG_M 封顶值 (s)

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
    ) -> PrecomputeParams:
        """从 configPara 提取 8 个物理参数，合并数值保护默认值。

        Raises:
            ValueError: 物理参数非正或非有限值时。
        """
        raw = {
            "H": float(config.H),
            "B_up": float(config.B_up),
            "B_down": float(config.B_down),
            "P_i": float(config.P_i),
            "P_j": float(config.P_j),
            "N_0": float(config.N_0),
            "rho_0": float(config.rho_0),
            "gamma_j": float(config.gamma_j),
            "eps_dist_sq": float(eps_dist_sq),
            "eps_rate": float(eps_rate),
            "eps_freq": float(eps_freq),
            "big_m_delay": float(big_m_delay),
        }
        for name, value in raw.items():
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(
                    f"PrecomputeParams.from_config: {name} must be finite and > 0, got {value!r}"
                )
        tau_tol_val = float(tau_tol)
        if not math.isfinite(tau_tol_val) or tau_tol_val < 0.0:
            raise ValueError(
                f"PrecomputeParams.from_config: tau_tol must be finite and >= 0, got {tau_tol_val!r}"
            )

        return cls(
            H=raw["H"],
            B_up=raw["B_up"],
            B_down=raw["B_down"],
            P_i=raw["P_i"],
            P_j=raw["P_j"],
            N_0=raw["N_0"],
            rho_0=raw["rho_0"],
            gamma_j=raw["gamma_j"],
            eps_dist_sq=raw["eps_dist_sq"],
            eps_rate=raw["eps_rate"],
            eps_freq=raw["eps_freq"],
            tau_tol=tau_tol_val,
            big_m_delay=raw["big_m_delay"],
        )


@dataclass(frozen=True)
class Level2Snapshot:
    """Level-2 输出快照，或首次迭代的默认值。

    q 和 f_edge 必须是 dense 的：覆盖所有候选 (j,t) 和 (j,i,t)。
    否则 precompute 无法为 OffloadingModel 生成完整的决策空间。

    维度约定:
        q[j][t] = (x, y)         — UAV j 在时隙 t 的 2D 水平位置
        f_edge[j][i][t] = Hz     — UAV j 为任务 i 在时隙 t 分配的 CPU 频率
        f_local_override[i][t]   — 可选，覆盖 task.f_local 的本地频率
    """

    q: Trajectory2D                          # [j][t] = (x, y)
    f_edge: Scalar3D                         # [j][i][t] = Hz
    f_local_override: Scalar2D | None = None  # [i][t]，可选覆盖
    source: Level2Source = "init"

    def validate(
        self,
        scenario: EdgeUavScenario,
        *,
        require_dense: bool = True,
    ) -> None:
        """校验快照的索引覆盖与值合法性。

        检查项:
          1. q 覆盖所有 (j, t) ∈ uavs × time_slots
          2. f_edge 覆盖所有 (j, i, t)（require_dense=True 时）
          3. 所有频率值 > 0
          4. 位置在地图边界内（meta 含 x_max/y_max 时）
          5. f_local_override 非 None 时覆盖所有 (i, t)

        累积所有错误后一次性 raise ValueError。
        """
        errors: list[str] = []
        time_slots = scenario.time_slots
        meta = scenario.meta or {}
        has_bounds = "x_max" in meta and "y_max" in meta
        x_max = float(meta["x_max"]) if has_bounds else 0.0
        y_max = float(meta["y_max"]) if has_bounds else 0.0

        # ---- 检查 1 & 4: q 覆盖 + 地图边界 ----
        for j in scenario.uavs:
            q_j = self.q.get(j)
            if q_j is None:
                for t in time_slots:
                    errors.append(f"q missing key (j={j}, t={t})")
                continue
            for t in time_slots:
                if t not in q_j:
                    errors.append(f"q missing key (j={j}, t={t})")
                    continue
                if has_bounds:
                    pos = q_j[t]
                    if not (0.0 <= pos[0] <= x_max and 0.0 <= pos[1] <= y_max):
                        errors.append(f"q[{j}][{t}] = {pos} out of bounds")

        # ---- 检查 2: f_edge 覆盖（仅 require_dense 时） ----
        if require_dense:
            for j in scenario.uavs:
                f_j = self.f_edge.get(j)
                if f_j is None:
                    for i in scenario.tasks:
                        for t in time_slots:
                            errors.append(f"f_edge missing key (j={j}, i={i}, t={t})")
                    continue
                for i in scenario.tasks:
                    f_ji = f_j.get(i)
                    if f_ji is None:
                        for t in time_slots:
                            errors.append(f"f_edge missing key (j={j}, i={i}, t={t})")
                        continue
                    for t in time_slots:
                        if t not in f_ji:
                            errors.append(f"f_edge missing key (j={j}, i={i}, t={t})")

        # ---- 检查 3: f_edge 值 > 0 且有限（始终检查已有条目） ----
        for j, f_j in self.f_edge.items():
            for i, f_ji in f_j.items():
                for t, v in f_ji.items():
                    if not math.isfinite(v) or v <= 0:
                        errors.append(f"f_edge[{j}][{i}][{t}] = {v} <= 0 or non-finite")

        # ---- 检查 5: f_local_override 覆盖 + 值校验 ----
        if self.f_local_override is not None:
            for i in scenario.tasks:
                f_i = self.f_local_override.get(i)
                if f_i is None:
                    for t in time_slots:
                        errors.append(f"f_local_override missing (i={i}, t={t})")
                    continue
                for t in time_slots:
                    if t not in f_i:
                        errors.append(f"f_local_override missing (i={i}, t={t})")
                        continue
                    v = f_i[t]
                    if not math.isfinite(v) or v <= 0:
                        errors.append(
                            f"f_local_override[{i}][{t}] = {v} <= 0 or non-finite"
                        )

        if errors:
            raise ValueError(
                f"Level2Snapshot validation failed ({len(errors)} errors):\n"
                + "\n".join(f"  - {e}" for e in errors)
            )


@dataclass(frozen=True)
class PrecomputeResult:
    """预计算输出，字段直接对齐 OffloadingModel.__init__ 参数。

    调用方式:
        result = precompute_offloading_inputs(scenario, params, snapshot)
        model = OffloadingModel(
            ...,
            D_hat_local=result.D_hat_local,
            D_hat_offload=result.D_hat_offload,
            E_hat_comp=result.E_hat_comp,
        )
    """

    D_hat_local: Scalar2D       # [i][t] — 本地执行时延 (s)
    D_hat_offload: Scalar3D     # [i][j][t] — 远程卸载总时延 (s)
    E_hat_comp: Scalar3D        # [j][i][t] — 边缘计算能耗 (J)
    diagnostics: dict[str, Any]  # 诊断信息（见 precompute_analysis.md §7.6）


# =====================================================================
# 公开 API
# =====================================================================

def make_initial_level2_snapshot(
    scenario: EdgeUavScenario,
    *,
    policy: InitPolicy = "paper_default",
) -> Level2Snapshot:
    """构造首次 BCD 迭代（k=0）的 Level-2 默认快照。

    policy="paper_default":
        轨迹 — 直线插值 q_j^t = q_I + t/(T-1) * (q_F - q_I)
        频率 — 均分 f_edge[j][i][t] = f_max / |I|

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
        True 时仅计算 active 时隙。

    返回
    -------
    PrecomputeResult
        D_hat_local, D_hat_offload, E_hat_comp, diagnostics。
    """
    tasks = scenario.tasks
    uavs = scenario.uavs
    time_slots = scenario.time_slots

    # ---- 输出容器 ----
    D_hat_local: Scalar2D = {i: {} for i in tasks}
    D_hat_offload: Scalar3D = {
        i: {j: {} for j in uavs} for i in tasks
    }
    E_hat_comp: Scalar3D = {
        j: {i: {} for i in tasks} for j in uavs
    }

    # ---- 统计变量 ----
    guard_hits: dict[str, int] = {
        "rate_floor": 0,
        "freq_floor": 0,
        "big_m_cap": 0,
        "tau_tol_borderline": 0,
    }
    active_task_slots = 0
    candidate_offload_pairs = 0
    deadline_feasible_pairs = 0
    uplink_rates: list[float] = []
    downlink_rates: list[float] = []

    # ---- Step 1 + Step 2: 本地时延 / 卸载时延 / 能耗 ----
    for i, task in tasks.items():
        tau_limit = float(task.tau) + params.tau_tol
        default_workload = float(task.F)
        default_local_freq = float(task.f_local)
        mu_i = mu.get(i) if mu is not None else None
        f_local_override_i = (
            snapshot.f_local_override.get(i)
            if snapshot.f_local_override is not None
            else None
        )

        for t in time_slots:
            is_active = bool(task.active.get(t, False))
            if is_active:
                active_task_slots += 1
            if active_only and not is_active:
                continue

            workload = (
                float(mu_i[t])
                if mu_i is not None and t in mu_i
                else default_workload
            )
            local_freq = (
                float(f_local_override_i[t])
                if f_local_override_i is not None and t in f_local_override_i
                else default_local_freq
            )

            # 本地时延
            D_hat_local[i][t] = _local_delay(
                workload,
                local_freq,
                eps_freq=params.eps_freq,
                big_m_delay=params.big_m_delay,
            )

            # 遍历 UAV：卸载时延 + 能耗
            for j in uavs:
                gain = _channel_gain(
                    task.pos,
                    snapshot.q[j][t],
                    H=params.H,
                    rho_0=params.rho_0,
                    eps_dist_sq=params.eps_dist_sq,
                )
                r_up = _rate_from_gain(
                    gain,
                    bandwidth=params.B_up,
                    tx_power=params.P_i,
                    noise_power=params.N_0,
                    eps_rate=params.eps_rate,
                )
                r_down = _rate_from_gain(
                    gain,
                    bandwidth=params.B_down,
                    tx_power=params.P_j,
                    noise_power=params.N_0,
                    eps_rate=params.eps_rate,
                )
                f_edge_val = float(snapshot.f_edge[j][i][t])

                d_offload = _offload_delay(
                    D_l=float(task.D_l),
                    D_r=float(task.D_r),
                    workload=workload,
                    r_up=r_up,
                    r_down=r_down,
                    f_edge=f_edge_val,
                    eps_rate=params.eps_rate,
                    eps_freq=params.eps_freq,
                    big_m_delay=params.big_m_delay,
                )

                D_hat_offload[i][j][t] = d_offload
                E_hat_comp[j][i][t] = _edge_energy(
                    gamma_j=params.gamma_j,
                    f_edge=f_edge_val,
                    workload=workload,
                    eps_freq=params.eps_freq,
                )

                # 统计
                candidate_offload_pairs += 1
                uplink_rates.append(r_up)
                downlink_rates.append(r_down)

                if r_up <= params.eps_rate:
                    guard_hits["rate_floor"] += 1
                if r_down <= params.eps_rate:
                    guard_hits["rate_floor"] += 1
                if f_edge_val < params.eps_freq:
                    guard_hits["freq_floor"] += 1
                if d_offload >= params.big_m_delay:
                    guard_hits["big_m_cap"] += 1
                if abs(d_offload - float(task.tau)) < params.tau_tol:
                    guard_hits["tau_tol_borderline"] += 1
                if d_offload <= tau_limit:
                    deadline_feasible_pairs += 1

    # ---- Step 3: 后处理 — 不可行标记 ----
    tasks_all_uavs_infeasible: set[int] = set()
    tasks_local_over_tau: set[int] = set()

    for i, task in tasks.items():
        tau_limit = float(task.tau) + params.tau_tol

        if any(d > tau_limit for d in D_hat_local[i].values()):
            tasks_local_over_tau.add(i)

        for t in D_hat_local[i]:
            if all(
                D_hat_offload[i][j].get(t, params.big_m_delay) > tau_limit
                for j in uavs
            ):
                tasks_all_uavs_infeasible.add(i)
                break

    # ---- 诊断 ----
    diagnostics = _build_diagnostics(
        D_hat_local=D_hat_local,
        D_hat_offload=D_hat_offload,
        E_hat_comp=E_hat_comp,
        tasks=tasks,
        snapshot_source=snapshot.source,
        guard_hits=guard_hits,
        active_task_slots=active_task_slots,
        candidate_offload_pairs=candidate_offload_pairs,
        deadline_feasible_pairs=deadline_feasible_pairs,
        uplink_rates=uplink_rates,
        downlink_rates=downlink_rates,
        tasks_all_uavs_infeasible=sorted(tasks_all_uavs_infeasible),
        tasks_local_over_tau=sorted(tasks_local_over_tau),
    )

    return PrecomputeResult(
        D_hat_local=D_hat_local,
        D_hat_offload=D_hat_offload,
        E_hat_comp=E_hat_comp,
        diagnostics=diagnostics,
    )


# =====================================================================
# 私有 Helper — 初始化
# =====================================================================

def _init_trajectory_linear(scenario: EdgeUavScenario) -> Trajectory2D:
    """直线插值轨迹初始化。

    代码版（0-indexed）:
        q_j^t = q_I + t/(T-1) * (q_F - q_I),  t ∈ {0, ..., T-1}
    T=1 时 ratio=0，全部停在起点。
    """
    time_slots = scenario.time_slots
    T = len(time_slots)
    q: Trajectory2D = {}

    for j, uav in scenario.uavs.items():
        x0, y0 = float(uav.pos[0]), float(uav.pos[1])
        dx = float(uav.pos_final[0]) - x0
        dy = float(uav.pos_final[1]) - y0
        q_j: dict[int, tuple[float, float]] = {}

        # 注: 用 t_idx 而非 t，使插值在 time_slots 非 0-based 时仍正确。
        # 当前场景生成器保证 time_slots == list(range(T))，两者等价。
        for t_idx, t in enumerate(time_slots):
            ratio = t_idx / (T - 1) if T > 1 else 0.0
            q_j[t] = (x0 + dx * ratio, y0 + dy * ratio)

        q[j] = q_j

    return q


def _init_frequency_uniform(scenario: EdgeUavScenario) -> Scalar3D:
    """均分频率初始化: f_edge[j][i][t] = f_max / |tasks|。

    输出是 dense 的：覆盖全部 (j, i, t) 候选对。
    """
    n_tasks = len(scenario.tasks)
    time_slots = scenario.time_slots

    if n_tasks == 0:
        return {j: {} for j in scenario.uavs}

    f_edge: Scalar3D = {}
    for j, uav in scenario.uavs.items():
        per_task: float = float(uav.f_max) / n_tasks
        f_edge[j] = {
            i: {t: per_task for t in time_slots}
            for i in scenario.tasks
        }

    return f_edge


# =====================================================================
# 私有 Helper — 物理计算纯函数
# =====================================================================

def _channel_gain(
    pos_i: tuple[float, float],
    q_jt: tuple[float, float],
    *,
    H: float,
    rho_0: float,
    eps_dist_sq: float,
) -> float:
    """空地信道增益: g = rho_0 / max(H^2 + ||pos_i - q_jt||^2, eps_dist_sq)。"""
    dx = pos_i[0] - q_jt[0]
    dy = pos_i[1] - q_jt[1]
    dist_sq = dx * dx + dy * dy
    denom = max(H * H + dist_sq, eps_dist_sq)
    return rho_0 / denom


def _rate_from_gain(
    gain: float,
    *,
    bandwidth: float,
    tx_power: float,
    noise_power: float,
    eps_rate: float,
) -> float:
    """Shannon 速率: r = B * log1p(P*g/N0) / ln(2)。低速率兜底 eps_rate。"""
    snr = tx_power * gain / noise_power
    rate = bandwidth * math.log1p(snr) / _LN2
    if rate < eps_rate:
        return eps_rate
    return rate


def _local_delay(
    workload: float,
    freq: float,
    *,
    eps_freq: float,
    big_m_delay: float,
) -> float:
    """本地计算时延: D = F / max(f, eps_freq)。频率不可用时返回 big_m_delay。"""
    if freq < eps_freq:
        return big_m_delay
    return workload / freq


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
    """远程卸载总时延 = 上行 + 计算 + 下行。超出 big_m_delay 时封顶。"""
    t_up = D_l / max(r_up, eps_rate)
    t_comp = workload / max(f_edge, eps_freq)
    t_down = D_r / max(r_down, eps_rate)
    total = t_up + t_comp + t_down
    if total > big_m_delay:
        return big_m_delay
    return total


def _edge_energy(
    *,
    gamma_j: float,
    f_edge: float,
    workload: float,
    eps_freq: float,
) -> float:
    """边缘计算能耗: E = gamma_j * f^2 * F。频率为零时返回 0.0。"""
    if f_edge < eps_freq:
        return 0.0
    return gamma_j * f_edge * f_edge * workload


# =====================================================================
# 私有 Helper — 诊断
# =====================================================================

def _finite_stats(values: list[float]) -> dict[str, float | int | None]:
    """对 finite 值（排除 inf/nan）计算 min/max/mean/count。"""
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        return {"min": None, "max": None, "mean": None, "count": 0}
    return {
        "min": min(finite),
        "max": max(finite),
        "mean": sum(finite) / len(finite),
        "count": len(finite),
    }


def _build_diagnostics(
    *,
    D_hat_local: Scalar2D,
    D_hat_offload: Scalar3D,
    E_hat_comp: Scalar3D,
    tasks: dict[int, ComputeTask],
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
    """汇总预计算统计信息与数值保护触发情况。"""
    local_values = [v for inner in D_hat_local.values() for v in inner.values()]
    offload_values = [
        v for i_dict in D_hat_offload.values()
        for j_dict in i_dict.values()
        for v in j_dict.values()
    ]
    energy_values = [
        v for j_dict in E_hat_comp.values()
        for i_dict in j_dict.values()
        for v in i_dict.values()
    ]

    return {
        "snapshot_source": snapshot_source,
        "active_task_slots": active_task_slots,
        "candidate_offload_pairs": candidate_offload_pairs,
        "deadline_feasible_pairs": deadline_feasible_pairs,
        "offload_feasible_ratio": (
            deadline_feasible_pairs / candidate_offload_pairs
            if candidate_offload_pairs > 0 else 0.0
        ),
        "local_delay_stats": _finite_stats(local_values),
        "offload_delay_stats": _finite_stats(offload_values),
        "edge_energy_stats": _finite_stats(energy_values),
        "uplink_rate_stats": _finite_stats(uplink_rates),
        "downlink_rate_stats": _finite_stats(downlink_rates),
        "guard_hits": guard_hits,
        "tasks_all_uavs_infeasible": tasks_all_uavs_infeasible,
        "tasks_local_over_tau": tasks_local_over_tau,
    }
