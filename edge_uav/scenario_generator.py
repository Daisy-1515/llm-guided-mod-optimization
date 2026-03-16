"""Edge UAV 场景生成器。

与原有 scenarioGenerator.py 并行共存，不继承原项目中的任何类。
当前阶段只冻结类接口、方法签名和主流程调用骨架，具体生成逻辑在后续步骤实现。
"""

import math
import warnings

import numpy as np

from config.config import configPara
from edge_uav.data import ComputeTask, UAV, EdgeUavScenario


class EdgeUavScenarioGenerator:
    """Edge UAV 场景生成器。

    职责：
        1. 从 config 读取 Edge UAV 场景参数。
        2. 生成时隙、终端设备、UAV 和场景元信息。
        3. 组装为 EdgeUavScenario 容器并执行前置/后置校验。

    设计原则：
        - 无状态：所有随机性通过局部 numpy RNG 管理，不污染全局随机状态。
        - 只"出题"：生成场景数据，不做任何优化计算。
        - 与原 scenarioGenerator.py 并行共存，不影响旧 HS 链路。
    """

    def __init__(self):
        """初始化场景生成器（无状态，空构造）。"""
        pass

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def getScenarioInfo(self, config: configPara) -> EdgeUavScenario:
        """主入口：读取配置并返回 Edge UAV 场景对象。

        调用流程：
            1. _validate_config  — 前置校验配置参数
            2. 创建局部 RNG     — np.random.default_rng(scenario_seed)
            3. _generate_time_slots — 生成 [0, 1, ..., T-1]
            4. _generate_tasks     — 生成终端设备集合
            5. _generate_uavs      — 生成 UAV 集合（固定基站）
            6. _build_meta         — 组装元信息字典
            7. 组装 EdgeUavScenario 容器
            8. _validate_scenario  — 后置校验
            9. 返回场景对象

        Args:
            config: 已完成 getConfigInfo() 加载的配置对象。

        Returns:
            封装 tasks、uavs、time_slots、seed 和 meta 的场景对象。
        """
        # 1. 前置校验：检查配置参数范围、边界和内部一致性
        self._validate_config(config)

        # 2. 创建局部 RNG：使用 scenario_seed，避免影响其他模块的随机状态
        rng = np.random.default_rng(config.scenario_seed)

        # 3. 生成时隙列表
        time_slots = self._generate_time_slots(config.T)

        # 4. 生成终端设备（ComputeTask）集合
        tasks = self._generate_tasks(config, rng)

        # 5. 生成 UAV 集合（固定基站方案，不依赖随机数）
        uavs = self._generate_uavs(config)

        # 6. 组装元信息字典
        meta = self._build_meta(config)

        # 7. 组装场景容器
        scenario = EdgeUavScenario(
            tasks=tasks,
            uavs=uavs,
            time_slots=time_slots,
            seed=config.scenario_seed,
            meta=meta,
        )

        # 8. 后置校验：检查生成结果是否满足设计约束
        self._validate_scenario(scenario, config)

        # 9. 返回场景对象
        return scenario

    # ------------------------------------------------------------------
    # 前置校验
    # ------------------------------------------------------------------

    def _validate_config(self, config: configPara) -> None:
        """前置校验：验证配置参数是否满足生成要求。

        检查内容包括：
            - numTasks / numUAVs > 0
            - min <= max（D_l, D_r, F, tau, active_window）
            - active_window_max <= T
            - depot 位置在地图边界内
            - 其他参数合法性

        Args:
            config: Edge UAV 场景相关配置对象。

        Raises:
            ValueError: 配置参数不合法时抛出。
        """
        errors = []

        # 正值检查：场景规模与物理参数
        for name, val in (
            ("T", config.T), ("delta", config.delta),
            ("x_max", config.x_max), ("y_max", config.y_max),
            ("H", config.H),
        ):
            if float(val) <= 0.0:
                errors.append(f"{name} must be > 0, got {val}")
        for name, val in (
            ("numTasks", config.numTasks), ("numUAVs", config.numUAVs),
        ):
            if int(val) <= 0:
                errors.append(f"{name} must be > 0, got {val}")

        # 范围对检查：min <= max
        for name, lower, upper in (
            ("D_l", config.D_l_min, config.D_l_max),
            ("D_r", config.D_r_min, config.D_r_max),
            ("F", config.F_min, config.F_max),
            ("tau", config.tau_min, config.tau_max),
            ("active_window", config.active_window_min, config.active_window_max),
        ):
            if lower > upper:
                errors.append(f"{name}_min must be <= {name}_max, got {lower} > {upper}")

        # 活跃窗口约束
        if int(config.active_window_min) < 1:
            errors.append(f"active_window_min must be >= 1, got {config.active_window_min}")
        if int(config.active_window_max) > int(config.T):
            errors.append(
                f"active_window_max must be <= T, got {config.active_window_max} > {config.T}"
            )
        if config.active_mode not in ("contiguous_window",):
            errors.append(f"Unsupported active_mode: {config.active_mode!r}")

        # 基站边界
        if not (0.0 <= float(config.depot_x) <= float(config.x_max)):
            errors.append(f"depot_x must be in [0, x_max], got {config.depot_x}")
        if not (0.0 <= float(config.depot_y) <= float(config.y_max)):
            errors.append(f"depot_y must be in [0, y_max], got {config.depot_y}")

        # 通信/硬件参数正值检查
        for name, val in (
            ("B_up", config.B_up), ("B_down", config.B_down),
            ("P_i", config.P_i), ("P_j", config.P_j),
            ("N_0", config.N_0), ("rho_0", config.rho_0),
            ("f_max", config.f_max), ("f_local_default", config.f_local_default),
            ("E_max", config.E_max),
        ):
            if float(val) <= 0.0:
                errors.append(f"{name} must be > 0, got {val}")

        # 任务参数下界正值检查
        for name, val in (
            ("D_l_min", config.D_l_min), ("D_r_min", config.D_r_min),
            ("F_min", config.F_min), ("tau_min", config.tau_min),
        ):
            if float(val) <= 0.0:
                errors.append(f"{name} must be > 0, got {val}")

        if errors:
            raise ValueError("Invalid Edge UAV config:\n- " + "\n- ".join(errors))

    # ------------------------------------------------------------------
    # 生成方法
    # ------------------------------------------------------------------

    def _generate_time_slots(self, T: int) -> list[int]:
        """生成仿真时隙序列 [0, 1, ..., T-1]。

        Args:
            T: 总时隙数。

        Returns:
            时隙索引列表。
        """
        return list(range(T))

    def _generate_tasks(
        self, config: configPara, rng: np.random.Generator
    ) -> dict[int, ComputeTask]:
        """生成终端设备集合。

        根据 config 中的任务规模、位置边界、任务参数范围和活跃窗口规则，
        循环创建 ComputeTask 实例。内部调用 _generate_active_slots 为每个
        设备生成活跃时隙。

        Args:
            config: Edge UAV 场景相关配置对象。
            rng: 局部随机数生成器，用于位置和参数采样。

        Returns:
            以任务索引为键、ComputeTask 实例为值的字典。
        """
        tasks = {}
        for i in range(config.numTasks):
            pos = (
                float(rng.uniform(0.0, config.x_max)),
                float(rng.uniform(0.0, config.y_max)),
            )
            tasks[i] = ComputeTask(
                index=i,
                pos=pos,
                D_l=float(rng.uniform(config.D_l_min, config.D_l_max)),
                D_r=float(rng.uniform(config.D_r_min, config.D_r_max)),
                F=float(rng.uniform(config.F_min, config.F_max)),
                tau=float(rng.uniform(config.tau_min, config.tau_max)),
                active=self._generate_active_slots(config, rng),
                f_local=float(config.f_local_default),
            )
        return tasks

    def _generate_uavs(self, config: configPara) -> dict[int, UAV]:
        """生成 UAV 集合（固定基站方案）。

        所有 UAV 的起点和终点均为 depot_pos，硬件参数从 config 读取。
        当前方案下不依赖随机数。

        Args:
            config: Edge UAV 场景相关配置对象。

        Returns:
            以 UAV 索引为键、UAV 实例为值的字典。
        """
        depot_pos = (float(config.depot_x), float(config.depot_y))
        uavs = {}
        for j in range(config.numUAVs):
            uavs[j] = UAV(
                index=j,
                pos=depot_pos,
                pos_final=depot_pos,
                E_max=float(config.E_max),
                f_max=float(config.f_max),
                N_max=None,
            )
        return uavs

    def _generate_active_slots(
        self, config: configPara, rng: np.random.Generator
    ) -> dict[int, bool]:
        """生成单个终端设备的活跃时隙映射。

        根据 config.active_mode 决定活跃窗口生成策略：
            - contiguous_window：在 [0, T) 内随机选取一段连续窗口

        返回的 dict 后续传入 ComputeTask 构造函数，
        由其包装为 defaultdict(bool)（未列出的时隙自动返回 False）。

        Args:
            config: 配置对象，包含 active_mode、窗口大小、T 等参数。
            rng: 局部随机数生成器。

        Returns:
            以时隙索引为键、活跃标志为值的字典（仅包含 True 的条目）。
        """
        if config.active_mode != "contiguous_window":
            raise ValueError(
                f"Unsupported active_mode: {config.active_mode!r}"
            )

        window_len = int(rng.integers(config.active_window_min, config.active_window_max + 1))
        start = int(rng.integers(0, config.T - window_len + 1))

        return {slot: True for slot in range(start, start + window_len)}

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _build_meta(self, config: configPara) -> dict:
        """组装场景元信息字典。

        从 config 中提取场景级公共参数，写入 EdgeUavScenario.meta，
        确保场景文件自包含、可复现。

        包含字段：T, delta, x_max, y_max, H, depot_pos, active_mode。

        Args:
            config: Edge UAV 场景相关配置对象。

        Returns:
            记录场景全局参数的元信息字典。
        """
        return {
            "T": int(config.T),
            "delta": float(config.delta),
            "x_max": float(config.x_max),
            "y_max": float(config.y_max),
            "H": float(config.H),
            "depot_pos": (float(config.depot_x), float(config.depot_y)),
            "active_mode": config.active_mode,
        }

    @staticmethod
    def _is_within_map(pos: tuple, x_max: float, y_max: float) -> bool:
        """检查二维位置是否位于 [0, x_max] x [0, y_max] 内。"""
        x, y = pos
        return 0.0 <= float(x) <= x_max and 0.0 <= float(y) <= y_max

    @staticmethod
    def _is_contiguous(slots: list[int]) -> bool:
        """检查时隙集合是否构成单段连续窗口。"""
        if not slots:
            return False
        ordered = sorted(slots)
        return ordered == list(range(ordered[0], ordered[-1] + 1))

    def _estimate_offload_delay_lb(
        self,
        task: ComputeTask,
        uavs: dict[int, UAV],
        config: configPara,
    ) -> float:
        """乐观估计任务卸载到最优 UAV 的最小时延下界。

        对每个 UAV 计算：D_l/r_up + F/f_max + D_r/r_down，取最小值。
        若连该下界都超过 tau，则卸载基本不可行。
        """
        best = math.inf
        h_sq = float(config.H) ** 2

        for uav in uavs.values():
            dx = float(task.pos[0]) - float(uav.pos[0])
            dy = float(task.pos[1]) - float(uav.pos[1])
            dist_sq = max(dx * dx + dy * dy + h_sq, 1e-12)
            gain = float(config.rho_0) / dist_sq

            r_up = float(config.B_up) * math.log2(
                1.0 + float(config.P_i) * gain / float(config.N_0)
            )
            r_down = float(config.B_down) * math.log2(
                1.0 + float(config.P_j) * gain / float(config.N_0)
            )
            if r_up <= 0.0 or r_down <= 0.0 or float(uav.f_max) <= 0.0:
                continue

            delay = (
                float(task.D_l) / r_up
                + float(task.F) / float(uav.f_max)
                + float(task.D_r) / r_down
            )
            best = min(best, delay)

        return best

    # ------------------------------------------------------------------
    # 后置校验
    # ------------------------------------------------------------------

    def _validate_scenario(
        self, scenario: EdgeUavScenario, config: configPara
    ) -> None:
        """后置校验：验证生成的场景对象是否满足设计约束。

        检查内容包括：
            - 每个设备至少 1 个活跃时隙
            - 任务和 UAV 索引唯一
            - 所有位置在 [0, x_max] x [0, y_max] 内
            - tau 可行性粗估（>80% 不可卸载则告警）

        Args:
            scenario: 已组装完成的场景对象。
            config: 配置对象，用于辅助校验。

        Raises:
            ValueError: 硬约束不满足时抛出。
        """
        errors = []
        x_max = float(config.x_max)
        y_max = float(config.y_max)
        T = int(config.T)
        depot_pos = (float(config.depot_x), float(config.depot_y))

        # time_slots 一致性
        if list(scenario.time_slots) != list(range(T)):
            errors.append(f"time_slots must equal list(range({T})), got {scenario.time_slots}")

        # 数量一致性
        if len(scenario.tasks) != int(config.numTasks):
            errors.append(f"Expected {config.numTasks} tasks, got {len(scenario.tasks)}")
        if len(scenario.uavs) != int(config.numUAVs):
            errors.append(f"Expected {config.numUAVs} uavs, got {len(scenario.uavs)}")

        # ---- 任务校验 ----
        task_indices = []
        for tid, task in scenario.tasks.items():
            task_indices.append(task.index)

            # 索引匹配
            if task.index != tid:
                errors.append(f"Task outer key {tid} != inner index {task.index}")

            # 位置边界
            if not self._is_within_map(task.pos, x_max, y_max):
                errors.append(f"Task {tid} position out of bounds: {task.pos}")

            # 活跃时隙
            active_slots = sorted(
                slot for slot, enabled in dict(task.active).items() if enabled
            )
            if not active_slots:
                errors.append(f"Task {tid} has no active slots")
                continue
            if any(s < 0 or s >= T for s in active_slots):
                errors.append(f"Task {tid} has active slots outside [0, {T-1}]: {active_slots}")
            if config.active_mode == "contiguous_window":
                if not self._is_contiguous(active_slots):
                    errors.append(f"Task {tid} active slots are not contiguous: {active_slots}")
                if not (
                    int(config.active_window_min)
                    <= len(active_slots)
                    <= int(config.active_window_max)
                ):
                    errors.append(
                        f"Task {tid} active window length {len(active_slots)} "
                        f"not in [{config.active_window_min}, {config.active_window_max}]"
                    )

        if len(task_indices) != len(set(task_indices)):
            errors.append("Task indices are not unique")

        # ---- UAV 校验 ----
        uav_indices = []
        for uid, uav in scenario.uavs.items():
            uav_indices.append(uav.index)

            if uav.index != uid:
                errors.append(f"UAV outer key {uid} != inner index {uav.index}")
            if not self._is_within_map(uav.pos, x_max, y_max):
                errors.append(f"UAV {uid} start position out of bounds: {uav.pos}")
            if not self._is_within_map(uav.pos_final, x_max, y_max):
                errors.append(f"UAV {uid} final position out of bounds: {uav.pos_final}")
            if uav.pos != depot_pos:
                errors.append(f"UAV {uid} start position {uav.pos} != depot {depot_pos}")
            if uav.pos_final != depot_pos:
                errors.append(f"UAV {uid} final position {uav.pos_final} != depot {depot_pos}")

        if len(uav_indices) != len(set(uav_indices)):
            errors.append("UAV indices are not unique")

        # 硬约束汇总
        if errors:
            raise ValueError("Invalid Edge UAV scenario:\n- " + "\n- ".join(errors))

        # ---- 软约束：tau 可行性粗估 ----
        infeasible = 0
        for task in scenario.tasks.values():
            t_local = float(task.F) / float(task.f_local)
            t_offload = self._estimate_offload_delay_lb(task, scenario.uavs, config)
            if t_local > float(task.tau) and t_offload > float(task.tau):
                infeasible += 1

        if scenario.tasks:
            ratio = infeasible / len(scenario.tasks)
            if ratio > 0.8:
                warnings.warn(
                    f"High tau infeasibility: {infeasible}/{len(scenario.tasks)} "
                    f"({ratio:.0%}) tasks cannot meet deadline even under optimistic "
                    f"estimates. Consider relaxing tau or increasing capacity.",
                    RuntimeWarning,
                    stacklevel=2,
                )
