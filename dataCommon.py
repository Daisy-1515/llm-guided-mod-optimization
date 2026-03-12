"""
* File: dataCommon.py
* Author: Yi
*
* created on 2024/08/19
"""
"""
@package dataCommon.py
@brief This module provide basic dataclass template.
"""
class Taxi:
    def __init__(self, start_pos: int, arrival_time: int, index:int):
        self.start_pos = start_pos
        self.arrival_time = arrival_time 
        self.index = index
    def __eq__(self, other):
        if not isinstance(other, Taxi):
            return False
        return (
            self.start_pos == other.start_pos
            and self.arrival_time == other.arrival_time
            and self.index == other.index
        )
    def print(self):
        info = {"start_pos": self.start_pos, "arr": self.arrival_time, "taxi_id": self.index}
        print(info)


class Passenger:
    def __init__(self, start: int, end: int, ocurr:int, index:int):
        self.origin = start
        self.destination = end
        self.arrTime = ocurr
        self.index = index
    def __eq__(self, other):
        if not isinstance(other, Passenger):
            return False
        return (
            self.origin == other.origin
            and self.destination == other.destination
            and self.arrTime == other.arrTime
            and self.index == other.index
        )
    def print(self):
        info = {"o":self.origin, "d":self.destination, "arr":self.arrTime, "passenger_id":self.index}
        print(info)

class Task:
    def __init__(self, start: int, end: int, index:int, ocurr:int, vehArr:int, vehDep:int):
        self.origin = start
        self.destination = end
        self.pedArr = ocurr
        self.pedIndex = index
        self.vehArrOrigin = vehArr
        self.vehDepOrigin = vehDep
        self.archive_time = -1
        self.assign_time = -1
    def print(self):
        info = {"o":self.origin, "d":self.destination, "pedArr":self.pedArr, "pedIndex":self.pedIndex, "vArr":self.vehArrOrigin, "vDep":self.vehDepOrigin, "archive_time":self.archive_time, "assign_time":self.assign_time}
        print(info)


# ======================================================================
# Edge UAV 数据类（新增）
# ======================================================================

from collections import defaultdict


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
