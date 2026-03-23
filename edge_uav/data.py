"""Edge UAV 数据类模块。

包含 ComputeTask、UAV、EdgeUavScenario 三个核心数据类，
分别对应终端设备计算任务、无人机边缘服务器、仿真场景容器。

从 dataCommon.py 拆分而来，原 MoD 数据类（Taxi, Passenger, Task）保留在 dataCommon.py。
"""

from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path


class ComputeTask:
    """终端设备生成的计算任务，对应数学模型中的 U_i^t。

    属性与公式文档对齐：
        index   — 设备/任务索引 i
        pos     — 终端地面位置 (x_i, y_i)，单位 m
        D_l     — 上行数据量，单位 bits
        D_r     — 下行结果数据量，单位 bits
        F       — 所需 CPU 周期数，单位 cycles
        tau     — 最大允许时延（截止期），单位 s
        active  — 时隙活跃标志 {t: bool}，对应 zeta_i^t
        f_local — 终端本地 CPU 频率上限，单位 Hz
    """

    __hash__ = None

    def __init__(
        self,
        index: int,
        pos: tuple,
        D_l: float,
        D_r: float,
        F: float,
        tau: float,
        active: dict = None,
        f_local: float = 1e9,
    ):
        self.index = index
        self.pos = pos          # (x, y) 米
        self.D_l = D_l          # 上行数据量 bits
        self.D_r = D_r          # 下行数据量 bits
        self.F = F              # CPU 周期数 cycles
        self.tau = tau           # 截止期 s
        self.active = defaultdict(bool, active) if active is not None else defaultdict(bool)
        self.f_local = f_local  # 本地 CPU 频率 Hz

    def __eq__(self, other):
        if not isinstance(other, ComputeTask):
            return False
        return (
            self.index == other.index
            and self.pos == other.pos
            and self.D_l == other.D_l
            and self.D_r == other.D_r
            and self.F == other.F
            and self.tau == other.tau
        )

    def print(self):
        info = {
            "index": self.index,
            "pos": self.pos,
            "D_l": self.D_l,
            "D_r": self.D_r,
            "F": self.F,
            "tau": self.tau,
            "f_local": self.f_local,
            "active_slots": sum(self.active.values()),
        }
        print(info)


class UAV:
    """无人机边缘服务器，对应数学模型中的 UAV j。

    属性与公式文档对齐：
        index     — UAV 索引 j
        pos       — 初始 2D 水平位置 (x_j^I, y_j^I)，单位 m
        pos_final — 终止位置约束 (x_j^F, y_j^F)，单位 m
        E_max     — 总能量预算，单位 J
        f_max     — 最大 CPU 频率，单位 Hz
        N_max     — 每时隙最大承载任务数（可选，None 表示无上限）
    """

    __hash__ = None

    def __init__(
        self,
        index: int,
        pos: tuple,
        pos_final: tuple,
        E_max: float,
        f_max: float,
        N_max: int = None,
    ):
        self.index = index
        self.pos = pos              # 初始位置 (x, y) 米
        self.pos_final = pos_final  # 终止位置 (x, y) 米
        self.E_max = E_max          # 能量预算 J
        self.f_max = f_max          # 最大 CPU 频率 Hz
        self.N_max = N_max          # 承载上限（None = 无限制）

    def __eq__(self, other):
        if not isinstance(other, UAV):
            return False
        return (
            self.index == other.index
            and self.pos == other.pos
            and self.pos_final == other.pos_final
            and self.E_max == other.E_max
            and self.f_max == other.f_max
        )

    def print(self):
        info = {
            "index": self.index,
            "pos": self.pos,
            "pos_final": self.pos_final,
            "E_max": self.E_max,
            "f_max": self.f_max,
            "N_max": self.N_max,
        }
        print(info)


# ======================================================================
# Edge UAV 场景容器
# ======================================================================

# @dataclass 装饰器自动生成 __init__、__repr__、__eq__ 等方法，
# 字段声明即构造函数参数，无需手写样板代码。
@dataclass
class EdgeUavScenario:
    """Edge UAV 仿真场景容器，支持 JSON 序列化与反序列化。

    本类是场景生成器（scenario_generator）的输出、预计算模块（③）的输入。
    它只存储"出题"数据，不包含任何优化计算结果（如 D_hat_local 等预计算量）。

    序列化设计要点：
        - JSON 字典键必须为 str → to_dict 中 int 键自动转 str，from_dict 中转回 int
        - tuple（坐标）在 JSON 中存为 list → 反序列化时还原为 tuple
        - defaultdict(bool)（active）序列化时仅保留值为 True 的时隙 → JSON 更紧凑
        - meta 中的 tuple 值（如 depot_pos）也做 list↔tuple 双向转换

    字段说明：
        tasks      — 终端设备集合 {task_id: ComputeTask}
        uavs       — 无人机集合 {uav_id: UAV}
        time_slots — 仿真时隙列表 [0, 1, ..., T-1]
        seed       — 随机种子，用于复现场景
        meta       — 元参数：T, delta, x_max, y_max, H, depot_pos 等
    """

    tasks: dict[int, ComputeTask]       # 键为设备索引 i，值为 ComputeTask 实例
    uavs: dict[int, UAV]               # 键为 UAV 索引 j，值为 UAV 实例
    time_slots: list[int]              # 时隙序列，如 [0, 1, ..., 19]
    seed: int                          # 场景随机种子，相同 seed 保证可复现
    meta: dict                         # 自由字典，存储全局仿真参数

    # ------ 序列化：Python 对象 → JSON 兼容字典 ------

    # @staticmethod：不访问实例(self)也不访问类(cls)，作为纯工具函数挂在类命名空间下。
    @staticmethod
    def _task_to_dict(task: 'ComputeTask') -> dict:
        """ComputeTask → JSON 兼容字典。

        转换规则：
            pos   : tuple → list    （JSON 不支持 tuple）
            active: defaultdict → dict，且仅保留值为 True 的时隙
                    键转为 str（JSON 要求字典键为字符串）
        """
        return {
            "index": task.index,
            "pos": list(task.pos),              # tuple (x, y) → list [x, y]
            "D_l": task.D_l,
            "D_r": task.D_r,
            "F": task.F,
            "tau": task.tau,
            "active": {
                # dict comprehension：遍历 active 字典，
                # 仅当 enabled 为 True 时才写入，实现紧凑存储
                str(slot): True
                for slot, enabled in dict(task.active).items()
                if enabled                      # 过滤掉 False 的时隙
            },
            "f_local": task.f_local,
        }

    @staticmethod
    def _uav_to_dict(uav: 'UAV') -> dict:
        """UAV → JSON 兼容字典。

        转换规则：
            pos / pos_final: tuple → list
            N_max: None 在 JSON 中自动映射为 null
        """
        return {
            "index": uav.index,
            "pos": list(uav.pos),               # tuple → list
            "pos_final": list(uav.pos_final),   # tuple → list
            "E_max": uav.E_max,
            "f_max": uav.f_max,
            "N_max": uav.N_max,                 # None → JSON null
        }

    def to_dict(self) -> dict:
        """整个场景 → JSON 兼容的嵌套字典。

        顶层结构：
            {
                "tasks":      {"0": {...}, "1": {...}, ...},  # str 键
                "uavs":       {"0": {...}, "1": {...}, ...},  # str 键
                "time_slots": [0, 1, ..., T-1],
                "seed":       42,
                "meta":       {"T": 20, "depot_pos": [500, 500], ...}
            }
        """
        # 遍历 meta，将其中的 tuple 值（如 depot_pos）转为 list
        meta_out = {}
        for k, v in (self.meta or {}).items():
            meta_out[k] = list(v) if isinstance(v, tuple) else v
        return {
            "tasks": {
                # str(tid)：将 int 键转为 str 以符合 JSON 规范
                str(tid): self._task_to_dict(task)
                for tid, task in self.tasks.items()
            },
            "uavs": {
                str(uid): self._uav_to_dict(uav)
                for uid, uav in self.uavs.items()
            },
            "time_slots": list(self.time_slots),
            "seed": self.seed,
            "meta": meta_out,
        }

    # ------ 反序列化：JSON 兼容字典 → Python 对象 ------

    @staticmethod
    def _task_from_dict(data: dict) -> 'ComputeTask':
        """JSON 字典 → ComputeTask 实例。

        反向转换规则（与 _task_to_dict 对称）：
            pos   : list → tuple
            active: str 键 → int 键，且只保留值为 True 的条目
                    ComputeTask.__init__ 会将 active 包装为 defaultdict(bool)，
                    因此未列出的时隙查询时自动返回 False
        """
        active_raw = data.get("active", {})
        # 带条件的 dict comprehension：遍历 active 字典项，
        # 将 str 键转回 int，并过滤掉 enabled 为 False 的条目
        active = {
            int(slot): True
            for slot, enabled in active_raw.items()
            if enabled                          # 防御外部 JSON 含 {"3": false} 的情况
        } if active_raw else {}
        return ComputeTask(
            index=int(data["index"]),           # JSON 数值可能为 float，强转 int
            pos=tuple(data["pos"]),             # list [x, y] → tuple (x, y)
            D_l=data["D_l"],
            D_r=data["D_r"],
            F=data["F"],
            tau=data["tau"],
            active=active,                      # 传入 ComputeTask 后自动包装为 defaultdict(bool)
            f_local=data.get("f_local", 1e9),   # 兼容早期 JSON 中缺少此字段的情况
        )

    @staticmethod
    def _uav_from_dict(data: dict) -> 'UAV':
        """JSON 字典 → UAV 实例。

        反向转换规则：
            pos / pos_final: list → tuple
            N_max: JSON null → Python None；JSON 数值 → int
        """
        n_max = data.get("N_max")               # JSON null → Python None
        return UAV(
            index=int(data["index"]),
            pos=tuple(data["pos"]),             # list → tuple
            pos_final=tuple(data["pos_final"]), # list → tuple
            E_max=data["E_max"],
            f_max=data["f_max"],
            # 三元表达式：N_max 非 None 时转 int，否则保持 None
            N_max=int(n_max) if n_max is not None else None,
        )

    # @classmethod：第一个参数 cls 指向类本身（而非实例），
    # 好处是子类调用时 cls 自动指向子类，支持继承扩展。
    @classmethod
    def from_dict(cls, data: dict) -> 'EdgeUavScenario':
        """从 JSON 兼容字典重建场景实例。

        处理流程：
            1. 遍历 data["tasks"]，将每项通过 _task_from_dict 还原为 ComputeTask
            2. 遍历 data["uavs"]，将每项通过 _uav_from_dict 还原为 UAV
            3. 校验 outer key（字典键）与 inner index（对象属性）的一致性
            4. 还原 meta 中的结构化字段（如 depot_pos: list → tuple）
        """
        # 重建 tasks 字典：str 键 → int 键 + ComputeTask 实例
        tasks = {
            int(tid): cls._task_from_dict(tdata)
            for tid, tdata in data["tasks"].items()
        }
        # 重建 uavs 字典：str 键 → int 键 + UAV 实例
        uavs = {
            int(uid): cls._uav_from_dict(udata)
            for uid, udata in data["uavs"].items()
        }
        # 一致性校验：防止手工编辑 JSON 导致外层键与内层 index 不匹配
        # 例如 {"7": {"index": 0, ...}} 会触发断言失败
        for tid, task in tasks.items():
            assert task.index == tid, (
                f"Task outer key {tid} != inner index {task.index}"
            )
        for uid, uav in uavs.items():
            assert uav.index == uid, (
                f"UAV outer key {uid} != inner index {uav.index}"
            )
        # 还原 meta 中已知的结构化字段
        # depot_pos 在 to_dict 中被转为 list，这里转回 tuple 以保持类型一致
        meta = data.get("meta", {})
        if "depot_pos" in meta and isinstance(meta["depot_pos"], list):
            meta["depot_pos"] = tuple(meta["depot_pos"])
        return cls(
            tasks=tasks,
            uavs=uavs,
            time_slots=data["time_slots"],
            seed=data["seed"],
            meta=meta,
        )

    # ------ 文件 I/O：JSON 持久化 ------

    def save_json(self, file_path: str) -> None:
        """保存到 JSON 文件。

        - 自动创建不存在的父目录（parents=True, exist_ok=True）
        - indent=2 保证可读性
        - ensure_ascii=False 允许中文等 Unicode 字符直接写入
        """
        path = Path(file_path)                              # str → Path 对象
        path.parent.mkdir(parents=True, exist_ok=True)      # 递归创建父目录
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load_json(cls, file_path: str) -> 'EdgeUavScenario':
        """从 JSON 文件加载场景实例。

        流程：读文件 → json.load 解析为 dict → cls.from_dict 重建对象。
        使用 @classmethod 而非 @staticmethod，使子类调用时能正确实例化子类。
        """
        with open(file_path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
