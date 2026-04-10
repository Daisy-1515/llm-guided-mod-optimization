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
from edge_uav.model.propulsion import total_flight_energy

_LN2 = math.log(2.0)


# =====================================================================
# 类型别名 — 与 OffloadingModel 的嵌套 dict 接口一致
# =====================================================================

Scalar2D = dict[int, dict[int, float]]                    # [i][t] 或 [j][t]
Scalar3D = dict[int, dict[int, dict[int, float]]]         # [i][j][t] 或 [j][i][t]
Trajectory2D = dict[int, dict[int, tuple[float, float]]]  # q[j][t] = (x, y)

Level2Source = Literal["init", "prev_bcd", "history_avg", "custom"]
InitPolicy = Literal["paper_default", "greedy", "custom", "random_visit"]


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

    # ---- 推进参数（用于飞行能量计算） ----
    eta_1: float      # 叶片剖面功率 (W)
    eta_2: float      # 诱导功率 (W)
    eta_3: float      # 机身阻力比
    eta_4: float      # 空气密度系数
    v_tip: float      # 桨尖速度 (m/s)
    delta: float      # 时隙长度 (s)

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
        """从 configPara 提取物理参数和推进参数，合并数值保护默认值。

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
            # 推进参数
            "eta_1": float(config.eta_1),
            "eta_2": float(config.eta_2),
            "eta_3": float(config.eta_3),
            "eta_4": float(config.eta_4),
            "v_tip": float(config.v_tip),
            "delta": float(config.delta),
            # 数值保护
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
            eta_1=raw["eta_1"],
            eta_2=raw["eta_2"],
            eta_3=raw["eta_3"],
            eta_4=raw["eta_4"],
            v_tip=raw["v_tip"],
            delta=raw["delta"],
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

    聚合归一化因子（用于系统成本公式 (20)）:
        N_act = Σ_t Σ_i ζ_i^t  (全时域 active task-slot 总数)
        N_fly = |U| × (T-1)    (全时域 UAV 移动段总数)
    """

    D_hat_local: Scalar2D       # [i][t] — 本地执行时延 (s)
    D_hat_offload: Scalar3D     # [i][j][t] — 远程卸载总时延 (s)
    E_hat_comp: Scalar3D        # [j][i][t] — 边缘计算能耗 (J)
    E_prop: dict[int, float]    # [j] — UAV j 的总推进能量 (J)
    N_act: int                  # 聚合归一化因子：active task-slot 总数
    N_fly: int                  # 聚合归一化因子：UAV 移动段总数 = |U| × (T-1)
    diagnostics: dict[str, Any]  # 诊断信息（见 precompute_analysis.md §7.6）


# =====================================================================
# 公开 API
# =====================================================================

def make_initial_level2_snapshot(
    scenario: EdgeUavScenario,
    *,
    policy: InitPolicy = "greedy",
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
    elif policy == "greedy":
        q = _init_trajectory_greedy(scenario)
        f_edge = _init_frequency_uniform(scenario)
    elif policy == "random_visit":
        import random as _random
        q = _init_trajectory_random_visit(scenario, _random.Random())
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

    # ---- Step 0: SINR 预计算 — 收集活跃信道增益，构造最坏情形干扰总量 ----
    # _sinr_gains[(i, j, t)]: 活跃 task i 在时隙 t 至 UAV j 的信道增益
    _sinr_gains: dict[tuple[int, int, int], float] = {}
    for _i, _task in tasks.items():
        for _t in time_slots:
            if not bool(_task.active.get(_t, False)):
                continue
            for _j in uavs:
                _sinr_gains[(_i, _j, _t)] = _channel_gain(
                    _task.pos,
                    snapshot.q[_j][_t],
                    H=params.H,
                    rho_0=params.rho_0,
                    eps_dist_sq=params.eps_dist_sq,
                )

    # _total_interf[(j, t)] = Σ_k P_i * g_{k,j,t}，k 遍历全部活跃 task
    # 计算单 task 干扰时减去自身：I_{i,j,t} = _total_interf[(j,t)] - P_i * g_{i,j,t}
    _total_interf: dict[tuple[int, int], float] = {}
    for _j in uavs:
        for _t in time_slots:
            _total_interf[(_j, _t)] = sum(
                params.P_i * _sinr_gains.get((_k, _j, _t), 0.0)
                for _k in tasks
            )

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
                gain = _sinr_gains.get((i, j, t))
                if gain is None:
                    # 非活跃时隙（active_only=False 时出现），退回内联计算
                    gain = _channel_gain(
                        task.pos,
                        snapshot.q[j][t],
                        H=params.H,
                        rho_0=params.rho_0,
                        eps_dist_sq=params.eps_dist_sq,
                    )
                    interference_up = 0.0
                else:
                    # 最坏情形 SINR：干扰 = 所有活跃 task 总干扰 - 自身
                    interference_up = max(
                        0.0, _total_interf[(j, t)] - params.P_i * gain
                    )
                r_up = _rate_from_gain_sinr(
                    gain,
                    bandwidth=params.B_up,
                    tx_power=params.P_i,
                    noise_power=params.N_0,
                    interference=interference_up,
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
        snapshot=snapshot,
        eps_freq=params.eps_freq,
    )

    # ---- 计算 N_act 和 N_fly 聚合归一化因子 ----
    # N_act = Σ_t Σ_i ζ_i^t (全时域 active task-slot 总数)
    # 注意: active_task_slots 已在 Step 1 中累加，直接使用
    N_act = active_task_slots

    # N_fly = |U| × (T-1) (全时域 UAV 移动段总数)
    N_fly = len(uavs) * (len(time_slots) - 1)

    # ---- 计算 E_prop: UAV 推进能量 ----
    E_prop = total_flight_energy(
        snapshot.q,
        params.delta,
        eta_1=params.eta_1,
        eta_2=params.eta_2,
        eta_3=params.eta_3,
        eta_4=params.eta_4,
        v_tip=params.v_tip,
    )

    return PrecomputeResult(
        D_hat_local=D_hat_local,
        D_hat_offload=D_hat_offload,
        E_hat_comp=E_hat_comp,
        E_prop=E_prop,
        N_act=N_act,
        N_fly=N_fly,
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


def _dist_sq(a: tuple[float, float], b: tuple[float, float]) -> float:
    """平方欧氏距离（仅用于比较，避免 sqrt）。"""
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return dx * dx + dy * dy


def _interpolate_waypoints(
    waypoints: list[tuple[float, float]],
    time_slots: list[int],
) -> dict[int, tuple[float, float]]:
    """按段距比例分配时隙 + 线性插值。

    waypoints: 至少 2 个点 [start, wp1, wp2, ..., end]
    time_slots: 长度 T 的列表

    返回 {t: (x, y)}，保证首尾精确对齐。
    """
    T = len(time_slots)
    n_seg = len(waypoints) - 1

    assert len(waypoints) >= 2, f"waypoints must have >= 2 points, got {len(waypoints)}"
    assert len(time_slots) >= 1, f"time_slots must be non-empty"

    if T == 1:
        return {time_slots[0]: waypoints[0]}

    # 各段欧氏距离
    seg_dists: list[float] = []
    for s in range(n_seg):
        seg_dists.append(math.sqrt(_dist_sq(waypoints[s], waypoints[s + 1])))

    total_dist = sum(seg_dists)

    # 按距离比例分配 T-1 个间隔给各段
    intervals = T - 1  # 总可分配间隔数
    slots_per_seg: list[int] = [0] * n_seg

    if total_dist < 1e-12:
        # 所有航路点重合，均分间隔给第一段
        slots_per_seg[0] = intervals
    else:
        # 按比例分配，保证总和 = intervals
        fractional = [seg_dists[s] / total_dist * intervals for s in range(n_seg)]
        # floor 分配
        for s in range(n_seg):
            slots_per_seg[s] = int(fractional[s])
        # 分配余数给误差最大的段
        remainder = intervals - sum(slots_per_seg)
        errors = [(fractional[s] - slots_per_seg[s], s) for s in range(n_seg)]
        errors.sort(reverse=True)
        for idx in range(remainder):
            slots_per_seg[errors[idx][1]] += 1

    # 保证第一段至少分到 1 个 slot，防止起点丢失
    if slots_per_seg[0] == 0:
        # 从最后一个有 >1 slot 的段借一个
        for donor in range(n_seg - 1, 0, -1):
            if slots_per_seg[donor] > 1:
                slots_per_seg[donor] -= 1
                slots_per_seg[0] = 1
                break
        else:
            # 所有段都只有 0 或 1 个 slot，把最后一段的给第一段
            for donor in range(n_seg - 1, 0, -1):
                if slots_per_seg[donor] > 0:
                    slots_per_seg[donor] -= 1
                    slots_per_seg[0] = 1
                    break

    # 段内线性插值
    q: dict[int, tuple[float, float]] = {}
    t_cursor = 0  # 当前已填充的 time_slots 索引

    for s in range(n_seg):
        n_slots_in_seg = slots_per_seg[s]
        x0, y0 = waypoints[s]
        x1, y1 = waypoints[s + 1]

        for k in range(n_slots_in_seg):
            ratio = k / n_slots_in_seg if n_slots_in_seg > 0 else 0.0
            q[time_slots[t_cursor]] = (x0 + (x1 - x0) * ratio, y0 + (y1 - y0) * ratio)
            t_cursor += 1

    # 最后一个时隙精确对齐终点
    q[time_slots[-1]] = waypoints[-1]

    return q


def _init_trajectory_greedy(scenario: EdgeUavScenario) -> Trajectory2D:
    """贪心经由任务点的多样化轨迹初始化。

    算法:
    1. Round-robin 贪心分配任务：UAV 0/1/2 轮流选离自己当前位置最近的未访问任务
    2. 构造航路点 [depot, task_a, task_b, ..., depot_end]
    3. 按段距比例分配时隙 + 线性插值
    4. 无任务时退化为直线
    """
    uav_ids = sorted(scenario.uavs.keys())
    task_ids = sorted(scenario.tasks.keys())
    time_slots = scenario.time_slots

    # 每架 UAV 的任务分配列表
    uav_tasks: dict[int, list[int]] = {j: [] for j in uav_ids}
    # 每架 UAV 的当前位置（用于贪心选择）
    uav_cursor: dict[int, tuple[float, float]] = {
        j: (float(scenario.uavs[j].pos[0]), float(scenario.uavs[j].pos[1]))
        for j in uav_ids
    }

    remaining = set(task_ids)
    n_uavs = len(uav_ids)
    turn = 0  # round-robin 计数器

    while remaining:
        j = uav_ids[turn % n_uavs]
        cur = uav_cursor[j]

        # 找最近的未访问任务
        best_i = None
        best_d = float("inf")
        for i in remaining:
            d = _dist_sq(cur, scenario.tasks[i].pos)
            if d < best_d or (d == best_d and (best_i is None or i < best_i)):
                best_d = d
                best_i = i

        assert best_i is not None
        uav_tasks[j].append(best_i)
        uav_cursor[j] = scenario.tasks[best_i].pos
        remaining.discard(best_i)
        turn += 1

    # 构造航路点并插值
    q: Trajectory2D = {}
    for j in uav_ids:
        uav = scenario.uavs[j]
        start = (float(uav.pos[0]), float(uav.pos[1]))
        end = (float(uav.pos_final[0]), float(uav.pos_final[1]))

        waypoints: list[tuple[float, float]] = [start]
        for i in uav_tasks[j]:
            waypoints.append(scenario.tasks[i].pos)
        waypoints.append(end)

        q[j] = _interpolate_waypoints(waypoints, time_slots)

    return q


def _init_trajectory_random_visit(
    scenario: EdgeUavScenario,
    rng: "random.Random",
) -> "Trajectory2D":
    """随机任务访问顺序的轨迹初始化，专用于 BCD 多起点重启。

    与 _init_trajectory_greedy 相同逻辑，但先随机打乱任务顺序，
    保证每次重启产生不同轨迹，帮助 BCD 跳出鞍点。
    """
    import random as _random  # noqa: F401（仅用于类型标注 fallback）

    uav_ids = sorted(scenario.uavs.keys())
    task_ids = list(scenario.tasks.keys())
    rng.shuffle(task_ids)  # 核心：随机打乱，产生不同轨迹

    uav_tasks: dict = {j: [] for j in uav_ids}
    n_uavs = len(uav_ids)
    for turn, i in enumerate(task_ids):
        uav_tasks[uav_ids[turn % n_uavs]].append(i)

    q: dict = {}
    time_slots = scenario.time_slots
    for j in uav_ids:
        waypoints = (
            [scenario.uavs[j].pos]
            + [scenario.tasks[i].pos for i in uav_tasks[j]]
            + [scenario.uavs[j].pos_final]
        )
        q[j] = _interpolate_waypoints(waypoints, time_slots)

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


def _rate_from_gain_sinr(
    gain: float,
    *,
    bandwidth: float,
    tx_power: float,
    noise_power: float,
    interference: float,
    eps_rate: float,
) -> float:
    """Shannon SINR 速率: r = B * log1p(P*g/(N0+I)) / ln(2)。低速率兜底 eps_rate。

    interference 为同频其他 UE 的干扰功率之和（W）。
    """
    sinr = tx_power * gain / (noise_power + interference)
    rate = bandwidth * math.log1p(sinr) / _LN2
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
    snapshot: "Level2Snapshot | None" = None,
    eps_freq: float = 1e-12,
) -> dict[str, Any]:
    """汇总预计算统计信息与数值保护触发情况。

    如提供 snapshot，会额外计算分离统计：
    - 已分配对（f > eps_freq）的可行率
    - 未分配对（f ≤ eps_freq）理论在 f_max 下的可行率
    - 系统分配率
    """
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

    result = {
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

    # ---- 分离统计：区分已分配对 vs 未分配对 ----
    # 目的：区分两类诊断故障
    #   1. 已分配对无法满足 deadline（真实 deadline 压力）
    #   2. 未分配对（f_edge=0）导致时延爆炸（实现口径混淆）
    #
    # 定义：
    #   - 已分配对：f_edge[j][i][t] > eps_freq（在 BCD 优化中被显式频率分配）
    #   - 未分配对：f_edge[j][i][t] ≤ eps_freq（在 adapt_f_edge_for_snapshot 中填 0.0）
    #
    # 指标说明：
    #   - assigned_pairs：总的已分配对数
    #   - assigned_feasible_pairs：其中满足 deadline 的对数
    #   - assigned_feasible_ratio：已分配可行率
    #     * 若 assigned_pairs == 0，则为 None（无法计算比例）
    #     * 若 assigned_pairs > 0，则为 assigned_feasible_pairs / assigned_pairs
    #   - unassigned_pairs：未分配对数（f=0 后的虚假时延）
    #   - assigned_pair_ratio：已分配对占总卸载候选对的比例
    if snapshot is not None and D_hat_offload and tasks:
        assigned_pairs = 0
        assigned_feasible = 0
        unassigned_pairs = 0

        for i, task in tasks.items():
            if i not in D_hat_offload:
                continue
            for j in D_hat_offload[i]:
                for t in D_hat_offload[i][j]:
                    f_val = float(snapshot.f_edge.get(j, {}).get(i, {}).get(t, 0.0))
                    d_val = D_hat_offload[i][j][t]

                    if f_val > eps_freq:
                        # 已分配对（f > eps_freq）
                        assigned_pairs += 1
                        if d_val <= float(task.tau):
                            assigned_feasible += 1
                    else:
                        # 未分配对（f ≤ eps_freq → 在 adapt_f_edge_for_snapshot 中被填 0.0）
                        unassigned_pairs += 1

        result["assigned_pairs"] = assigned_pairs
        result["assigned_feasible_pairs"] = assigned_feasible
        # 关键修正：assigned_feasible_ratio = None 当 assigned_pairs == 0
        # 原因：0.0 和 None 语义不同
        #   - None 表示"无已分配对，无法计算可行率"（不做 deadline 压力判断）
        #   - 0.0 表示"有已分配对但全部不可行"（即真实 deadline 压力很大）
        result["assigned_feasible_ratio"] = (
            assigned_feasible / assigned_pairs if assigned_pairs > 0 else None
        )
        result["unassigned_pairs"] = unassigned_pairs
        result["assigned_pair_ratio"] = (
            assigned_pairs / candidate_offload_pairs if candidate_offload_pairs > 0 else 0.0
        )

    # ---- 新增 2026-03-30：(i,t) 级可行性网格 ----
    # 初版最小化：仅本地可行性 bool，供 BCD 循环快速查询
    per_slot_feasibility = {}
    for i, task in tasks.items():
        if i in D_hat_local:
            for t in D_hat_local[i]:
                local_feasible = D_hat_local[i][t] <= float(task.tau)
                per_slot_feasibility[f"{i}_{t}"] = local_feasible

    result["per_slot_feasibility"] = per_slot_feasibility

    return result
