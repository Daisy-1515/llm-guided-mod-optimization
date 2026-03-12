"""
File: OffloadingModel.py

Level-1 BLP for Edge UAV computation offloading.

This module solves the task offloading decision subproblem:
given fixed UAV trajectories and resource allocation (from Level 2),
decide which tasks execute locally and which offload to which UAV.

The objective function can be dynamically replaced by LLM-generated
code via exec(), following the same injection pattern as the original
AssignmentModel.py.
"""

import time

import gurobipy as gb


class OffloadingModel:
    """Level-1 Binary Linear Program for task offloading decisions.

    Attributes exposed to LLM-generated dynamic_obj_func(self):
        self.x_local[i, t]           - binary decision variable
        self.x_offload[i, j, t]      - binary decision variable
        self.D_hat_local[i][t]       - precomputed local delay (s)
        self.D_hat_offload[i][j][t]  - precomputed offload delay (s)
        self.E_hat_comp[j][i][t]     - precomputed edge energy (J)
        self.task[i].tau             - deadline (s)
        self.task[i].active[t]       - activity flag (bool)
        self.uav[j].E_max           - energy budget (J)
        self.taskList                - list of task indices
        self.uavList                 - list of UAV indices
        self.timeList                - list of time slot indices
        self.alpha                   - delay weight
        self.gamma_w                 - energy weight
        self.M                       - big-M constant
        self.model                   - Gurobi Model instance
    """

    def __init__(self, tasks, uavs, time_list,
                 D_hat_local, D_hat_offload, E_hat_comp,
                 alpha=1.0, gamma_w=1.0,
                 dynamic_obj_func=None):
        """
        Parameters
        ----------
        tasks : dict
            {i: task_dataclass} with .tau, .active[t], .D_l, .D_r, .F, .index
        uavs : dict
            {j: uav_dataclass} with .E_max, .f_max, .pos, .index
        time_list : list
            Time slot indices.
        D_hat_local : dict
            D_hat_local[i][t] - precomputed local execution delay.
        D_hat_offload : dict
            D_hat_offload[i][j][t] - precomputed remote offloading delay.
        E_hat_comp : dict
            E_hat_comp[j][i][t] - precomputed edge computing energy.
        alpha : float
            Weight for normalized delay term.
        gamma_w : float
            Weight for normalized energy term.
        dynamic_obj_func : str or None
            LLM-generated objective function code (Python string).
        """
        # Data storage (use same names that LLM code will access)
        self.task = tasks.copy()
        self.uav = uavs.copy()
        self.taskList = list(tasks.keys())
        self.uavList = list(uavs.keys())
        self.timeList = list(time_list)

        # Precomputed constants
        self.D_hat_local = D_hat_local
        self.D_hat_offload = D_hat_offload
        self.E_hat_comp = E_hat_comp

        # Weights
        self.alpha = alpha
        self.gamma_w = gamma_w

        # Solver parameters
        self.M = 100000
        self.gap = 0.05

        # Model and variables (populated in setupVars)
        self.model = None
        self.x_local = {}
        self.x_offload = {}

        # Dynamic objective function handling
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
    # Public interface
    # ------------------------------------------------------------------
    def get_latest_func(self):
        """Return the string form of the current objective function."""
        return self.string_func

    def solveProblem(self):
        """Run the full solve pipeline: init -> vars -> cons -> obj -> optimize.

        Returns
        -------
        feasible : bool
        cost : float
            Objective value (-1 if infeasible).
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
            self.model.write("offloading_model.ilp")
            return False, -1

        obj = self.model.objVal
        print(f"*****************OBJ COST: {obj:.4f}************")

        if self.model.status == gb.GRB.Status.OPTIMAL:
            return True, obj

        return False, obj

    def getOutputs(self):
        """Extract offloading decisions from the solved model.

        Returns
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
    # Model building
    # ------------------------------------------------------------------
    def initModel(self):
        self.model = gb.Model("Edge UAV Offloading BLP")
        self.model.Params.MIPGap = self.gap
        self.model.setParam("TimeLimit", 10)

    def _offload_feasible(self, i, j, t):
        """Check L1-C2: offloading is feasible only if delay <= deadline."""
        try:
            return self.D_hat_offload[i][j][t] <= self.task[i].tau
        except (KeyError, IndexError):
            return False

    def setupVars(self):
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
                    if self._offload_feasible(i, j, t):
                        self.x_offload[i, j, t] = self.model.addVar(
                            vtype=gb.GRB.BINARY, lb=0,
                            name=f"X_offload_{i}_{j}_{t}",
                        )

        self.model.update()

    def setupCons(self):
        print("Create Constraints for Offloading Model!")

        # (L1-C1) Unique assignment: each active task -> local OR one UAV
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

        # (L1-C3) Optional UAV capacity per time slot
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
    # Objective function
    # ------------------------------------------------------------------
    def setupObj(self):
        if self.dynamic_obj_func is None:
            if self.string_func is None:
                print("No dynamic_obj_func found.")
                self.default_dynamic_obj_func()
                self.error_message = "None Obj. Using default obj."
            else:
                # exec() failed during __init__
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
        """Standard L1 objective (L1-obj from formula docs).

        cost1: normalized delay (local + offload)
        cost2: normalized edge computing energy
        """
        # Cost 1: weighted normalized delay
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

        # Cost 2: normalized edge computing energy
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
