"""
文件: edge_uav/model/offloading.py

Edge UAV 计算卸载的 Level-1 二进制线性规划（BLP）。

本模块求解任务卸载决策子问题：
在 Level-2 给定的固定 UAV 轨迹与资源分配条件下，
决定哪些任务在本地执行，哪些卸载到哪架 UAV。

目标函数可通过 exec() 注入 LLM 生成的代码动态替换，
与原项目 AssignmentModel.py 的注入模式一致。
"""

import math
import os
import threading
import time

import gurobipy as gb


class OffloadingModel:
    """Level-1 任务卸载决策二进制线性规划。

    LLM 生成的 dynamic_obj_func(self) 可访问的属性：
        self.x_local[i, t]           - 二进制决策变量（1=本地执行）
        self.x_offload[i, j, t]      - 二进制决策变量（1=卸载到 UAV j）
        self.D_hat_local[i][t]       - 预计算本地执行时延（秒）
        self.D_hat_offload[i][j][t]  - 预计算卸载时延（秒）
        self.E_hat_comp[j][i][t]     - 预计算边缘计算能耗（焦耳）
        self.task[i].tau             - 任务截止期（秒）
        self.task[i].active[t]       - 任务活跃标志（bool）
        self.uav[j].E_max            - UAV 最大能量预算（焦耳）
        self.taskList                - 任务索引列表
        self.uavList                 - UAV 索引列表
        self.timeList                - 时隙索引列表
        self.alpha                   - 时延权重
        self.gamma_w                 - 能耗权重
        self.M                       - 大 M 常量（线性化用）
        self.model                   - Gurobi Model 实例
    """

    def __init__(self, tasks, uavs, time_list,
                 D_hat_local, D_hat_offload, E_hat_comp,
                 alpha=1.0, gamma_w=1.0,
                 dynamic_obj_func=None):
        """
        参数
        ----------
        tasks : dict
            {i: task_dataclass}，属性包括 .tau, .active[t], .D_l, .D_r, .F, .index
        uavs : dict
            {j: uav_dataclass}，属性包括 .E_max, .f_max, .pos, .index
        time_list : list
            时隙索引列表。
        D_hat_local : dict
            D_hat_local[i][t] — 预计算本地执行时延。
        D_hat_offload : dict
            D_hat_offload[i][j][t] — 预计算远程卸载时延。
        E_hat_comp : dict
            E_hat_comp[j][i][t] — 预计算边缘计算能耗。
        alpha : float
            归一化时延项权重。
        gamma_w : float
            归一化能耗项权重。
        dynamic_obj_func : str or None
            LLM 生成的目标函数代码（Python 字符串）。
        """
        # 数据存储（属性名与 LLM 生成代码中的访问名保持一致）
        self.task = tasks.copy()
        self.uav = uavs.copy()
        self.taskList = list(tasks.keys())
        self.uavList = list(uavs.keys())
        self.timeList = list(time_list)

        # 预计算常量
        self.D_hat_local = D_hat_local
        self.D_hat_offload = D_hat_offload
        self.E_hat_comp = E_hat_comp

        # 权重系数
        self.alpha = alpha
        self.gamma_w = gamma_w

        # 求解器参数
        self.M = 100000
        self.gap = 0.05

        # 模型与决策变量（由 setupVars 填充）
        self.model = None
        self.x_local = {}
        self.x_offload = {}

        # 动态目标函数处理
        self.error_message = None
        self.string_func = dynamic_obj_func
        self.dynamic_obj_func = dynamic_obj_func
        self.latest_correct_func = None

        if isinstance(self.dynamic_obj_func, str):
            try:
                namespace = {}
                exec(self.dynamic_obj_func, globals(), namespace)
                self.dynamic_obj_func = namespace.get("dynamic_obj_func", None)
            except Exception as e:
                self.error_message = (
                    f"{e}. ConversionError. Falling back to default obj."
                )
                print(f"Error during dynamic objective setup: {self.error_message}")
                self.dynamic_obj_func = None

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------
    def get_latest_func(self):
        """返回当前目标函数的字符串形式。"""
        return self.string_func

    def solveProblem(self):
        """执行完整求解流程：初始化 → 变量 → 约束 → 目标 → 优化。

        返回
        -------
        feasible : bool
        cost : float
            目标值（不可行时返回 -1）。
        """
        self.initModel()
        self.setupVars()
        self.setupCons()
        self.setupObj()

        print("*****************Start Optimize************")
        start = time.time()
        self.model.optimize()
        elapsed = time.time() - start
        print(f"*****************RUN TIME: {elapsed:.2f}s************")

        if self.model.status == gb.GRB.INFEASIBLE:
            self.model.computeIIS()
            ts = int(time.time() * 1000) % 1_000_000
            ilp_name = f"offloading_model_{os.getpid()}_{threading.get_ident()}_{ts}.ilp"
            self.model.write(ilp_name)
            return False, -1

        obj = self.model.objVal
        print(f"*****************OBJ COST: {obj:.4f}************")

        if self.model.status == gb.GRB.Status.OPTIMAL:
            return True, obj

        return False, obj

    def getOutputs(self):
        """从已求解模型中提取卸载决策结果。

        返回
        -------
        dict
            {t: {"local": [task_ids], "offload": {j: [task_ids]}}}
        """
        result = {}

        if self.model.status in (gb.GRB.INFEASIBLE, gb.GRB.UNBOUNDED):
            print("Model status infeasible/unbounded — no outputs.")
            return result

        X_local = self.model.getAttr("x", self.x_local)
        X_offload = self.model.getAttr("x", self.x_offload)

        for t in self.timeList:
            local_tasks = []
            offload_tasks = {j: [] for j in self.uavList}

            for i in self.taskList:
                if not self.task[i].active[t]:
                    continue

                if (i, t) in X_local and X_local[i, t] > 0.5:
                    local_tasks.append(i)
                else:
                    for j in self.uavList:
                        if (i, j, t) in X_offload and X_offload[i, j, t] > 0.5:
                            offload_tasks[j].append(i)
                            break

            result[t] = {"local": local_tasks, "offload": offload_tasks}

        return result

    # ------------------------------------------------------------------
    # 模型构建
    # ------------------------------------------------------------------
    def initModel(self):
        """初始化 Gurobi 模型并设置求解参数。"""
        self.model = gb.Model("Edge UAV Offloading BLP")
        self.model.Params.MIPGap = self.gap
        self.model.setParam("TimeLimit", 10)

    def _offload_feasible(self, i, j, t):
        """检查 L1-C2：卸载时延不超过截止期时才允许卸载。"""
        try:
            return self.D_hat_offload[i][j][t] <= self.task[i].tau
        except (KeyError, IndexError):
            return False

    def _local_feasible(self, i, t):
        """检查本地时延约束：本地执行时延不超过截止期。"""
        try:
            return self.D_hat_local[i][t] <= self.task[i].tau
        except (KeyError, IndexError):
            return False

    def setupVars(self):
        """创建二进制决策变量。

        为所有活跃任务无条件创建 x_local 和 x_offload 变量，
        让优化器自由选择所有分配选项（超时通过 D/τ > 1 自然反映在目标值中）。
        """
        print("Create Variables for Offloading Model!")
        self.x_local = {}
        self.x_offload = {}

        for i in self.taskList:
            for t in self.timeList:
                if not self.task[i].active[t]:
                    continue

                self.x_local[i, t] = self.model.addVar(
                    vtype=gb.GRB.BINARY, lb=0,
                    name=f"X_local_{i}_{t}",
                )

                for j in self.uavList:
                    self.x_offload[i, j, t] = self.model.addVar(
                        vtype=gb.GRB.BINARY, lb=0,
                        name=f"X_offload_{i}_{j}_{t}",
                    )

        self.model.update()

    def setupCons(self):
        """建立模型约束。

        L1-C1：每个活跃 (i,t) 在对应时隙中恰好分配到一个目标（本地或某架 UAV）。
        L1-C3：若 UAV 设置了最大承载量 N_max，则每时隙分配数不超过上限（可选）。
        """
        print("Create Constraints for Offloading Model!")

        # (L1-C1) 唯一分配：每个活跃 (i,t) → 本地或某一 UAV
        for i in self.taskList:
            for t in self.timeList:
                if not self.task[i].active[t]:
                    continue
                offload_sum = gb.quicksum(
                    self.x_offload[i, j, t]
                    for j in self.uavList
                    if (i, j, t) in self.x_offload
                )
                self.model.addConstr(
                    self.x_local[i, t] + offload_sum == 1,
                    name=f"C1_assign_{i}_{t}",
                )

        # (L1-C3) 可选 UAV 每时隙承载量上限
        for j in self.uavList:
            cap = getattr(self.uav[j], "N_max", None)
            if cap is None:
                continue
            for t in self.timeList:
                load = gb.quicksum(
                    self.x_offload[i, j, t]
                    for i in self.taskList
                    if self.task[i].active[t] and (i, j, t) in self.x_offload
                )
                self.model.addConstr(
                    load <= cap,
                    name=f"C3_cap_{j}_{t}",
                )

    # ------------------------------------------------------------------
    # 目标函数
    # ------------------------------------------------------------------
    def setupObj(self):
        """配置目标函数。

        三分支逻辑：
        1. 未提供目标函数代码 → 使用默认目标函数
        2. exec() 转换失败 → 回退到默认目标函数
        3. exec() 成功 → 调用 LLM 生成的动态目标函数
        """
        if self.dynamic_obj_func is None:
            if self.string_func is None:
                print("No dynamic_obj_func found.")
                self.default_dynamic_obj_func()
                self.error_message = "None Obj. Using default obj."
            else:
                # exec() 在 __init__ 阶段已失败，回退到默认
                self.default_dynamic_obj_func()
        else:
            try:
                self.dynamic_obj_func(self)
                self.error_message = (
                    "Your obj function is correct. Gurobi accepts your obj."
                )
                self.latest_correct_func = self.string_func
            except Exception as e:
                self.error_message = (
                    f"{e}. Falling back to default obj for this iteration."
                )
                print(f"Error in dynamic objective: {self.error_message}")
                self.default_dynamic_obj_func()

    def default_dynamic_obj_func(self):
        """标准 L1 目标函数（公式文档中的 L1-obj）。

        cost1：归一化时延（本地执行 + 卸载执行）
        cost2：归一化边缘计算能耗
        """
        # 成本项1：加权归一化时延
        cost1 = gb.quicksum(
            self.alpha * self.D_hat_local[i][t] / self.task[i].tau
            * self.x_local[i, t]
            for i in self.taskList
            for t in self.timeList
            if self.task[i].active[t] and (i, t) in self.x_local
        ) + gb.quicksum(
            self.alpha * self.D_hat_offload[i][j][t] / self.task[i].tau
            * self.x_offload[i, j, t]
            for i in self.taskList
            for j in self.uavList
            for t in self.timeList
            if self.task[i].active[t] and (i, j, t) in self.x_offload
        )

        # 成本项2：归一化边缘计算能耗
        cost2 = gb.quicksum(
            self.gamma_w * self.E_hat_comp[j][i][t] / self.uav[j].E_max
            * self.x_offload[i, j, t]
            for i in self.taskList
            for j in self.uavList
            for t in self.timeList
            if self.task[i].active[t] and (i, j, t) in self.x_offload
        )

        costs = [cost1, cost2]
        weights = [1, 1]
        self.model.setObjective(
            gb.quicksum(w * c for w, c in zip(costs, weights)),
            gb.GRB.MINIMIZE,
        )
