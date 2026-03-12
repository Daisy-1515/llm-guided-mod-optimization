"""
File: edgeUavPrompt.py

Prompt templates for Edge UAV computation offloading optimization.

This module is an independent base class — it does NOT inherit from
the original project's basicPrompts. All five prompt components are
built from scratch for the Edge Computing + UAV scenario.
"""

from pathlib import Path


class EdgeUavPrompts:
    """Base prompt template for Edge UAV task offloading (Level 1 BLP).

    Five prompt components:
        1. prompt_scenario       — system overview and LLM task description
        2. prompt_static_info    — runtime statistics summary (populated via set_scenario_info)
        3. prompt_init_level1model — OffloadingModel source code + structured explanation
        4. prompt_obj_format     — required JSON output format for LLM response
        5. prompt_cons_restriction — Gurobi coding rules and variable constraints
    """

    def __init__(self, model_path):
        """
        Parameters
        ----------
        model_path : str
            Path to the OffloadingModel source file. Its contents are
            embedded in the prompt so the LLM can see the model structure.
        """
        self.model_path = model_path

        # ---- build five core prompt components ----
        self.prompt_scenario = self._build_scenario()
        self.prompt_static_info = self._build_static_info_placeholder()
        self.prompt_init_level1model = self._build_init_level1model()
        self.prompt_obj_format = self._build_obj_format()
        self.prompt_cons_restriction = self._build_cons_restriction()

    # ------------------------------------------------------------------
    # 1. Scenario
    # ------------------------------------------------------------------
    def _build_scenario(self):
        return (
            "Act as an expert in Edge Computing and UAV trajectory optimization. "
            "You are designing the primary objective function for a two-level "
            "real-time computation offloading system.\n\n"

            "1. **System Overview**:\n"
            "   - Multiple UAVs fly over a service area, each carrying an edge computing server.\n"
            "   - Ground terminal devices (TDs) generate computation tasks every time slot.\n"
            "   - Each task can be executed locally on the TD, or offloaded to a nearby UAV for remote execution.\n"
            "   - The system operates in discrete time slots indexed by t.\n\n"

            "2. **Optimization Structure (Two-Level Decomposition)**:\n"
            "   - **Level 1 (Your Task)**: Task offloading assignment — decide which tasks execute locally "
            "and which offload to which UAV. This is a Binary Linear Program (BLP) solved by Gurobi.\n"
            "   - **Level 2 (Already Solved)**: Given fixed offloading decisions, jointly optimize "
            "UAV trajectories and CPU frequency allocation via BCD + SCA.\n"
            "   - The two levels alternate iteratively (Block Coordinate Descent) until convergence.\n\n"

            "3. **Your Task**:\n"
            "   Design a novel Level-1 objective function that guides Gurobi to make "
            "good offloading decisions. Your objective is a *proxy* — it replaces the "
            "standard cost function to explore creative optimization strategies. "
            "The proxy objective should:\n"
            "   - Minimize a weighted combination of task completion delay and energy consumption.\n"
            "   - Account for task urgency (deadline), UAV proximity, and load distribution.\n"
            "   - Be compatible with Gurobi's BLP formulation (linear in binary variables).\n\n"

            "4. **Key Requirements**:\n"
            "   - All tasks must be assigned (local or one UAV) each time slot.\n"
            "   - Only active tasks (task[i].active[t] == True) should be included in summations.\n"
            "   - The objective must be expressible using Gurobi linear expressions.\n"
            "   - Precomputed constants (delays, energies) are available — no need to recompute them."
        )

    # ------------------------------------------------------------------
    # 2. Static Info (populated at runtime via set_scenario_info)
    # ------------------------------------------------------------------
    def _build_static_info_placeholder(self):
        return (
            "=== System Scale ===\n"
            "Data not yet initialized. Call set_scenario_info() after scenario generation."
        )

    def set_scenario_info(self, tasks, uavs, time_slots):
        """Populate static info with actual scenario statistics.

        Called once after scenario generation, before the optimization loop.

        Parameters
        ----------
        tasks : dict
            {task_id: task_dataclass} with attributes: D_l, D_r, F, tau, active.
        uavs : dict
            {uav_id: uav_dataclass} with attributes: E_max, f_max, pos.
        time_slots : list
            List of time slot indices.
        """
        num_tasks = len(tasks)
        num_uavs = len(uavs)
        num_time = len(time_slots)

        def _stats(values):
            """Return (min, max, mean) with empty-list safety."""
            if not values:
                return "N/A", "N/A", "N/A"
            return min(values), max(values), sum(values) / len(values)

        tau_min, tau_max, tau_mean = _stats([t.tau for t in tasks.values()])
        data_min, data_max, data_mean = _stats([t.D_l + t.D_r for t in tasks.values()])
        e_min, e_max_val, e_mean = _stats([u.E_max for u in uavs.values()])
        f_min, f_max_val, f_mean = _stats([u.f_max for u in uavs.values()])

        def _fmt(val, spec):
            return val if val == "N/A" else format(val, spec)

        self.prompt_static_info = (
            "=== System Scale ===\n"
            f"- Terminal devices (tasks): {num_tasks}\n"
            f"- UAVs (edge servers):     {num_uavs}\n"
            f"- Time slots:              {num_time}\n\n"

            "=== Task Statistics ===\n"
            f"- Deadline (tau): min={_fmt(tau_min, '.3f')}s, "
            f"max={_fmt(tau_max, '.3f')}s, mean={_fmt(tau_mean, '.3f')}s\n"
            f"- Total data size (D_l + D_r): min={_fmt(data_min, '.0f')} bits, "
            f"max={_fmt(data_max, '.0f')} bits, mean={_fmt(data_mean, '.0f')} bits\n\n"

            "=== UAV Statistics ===\n"
            f"- Max energy (E_max): min={_fmt(e_min, '.1f')}J, "
            f"max={_fmt(e_max_val, '.1f')}J, mean={_fmt(e_mean, '.1f')}J\n"
            f"- Max CPU freq (f_max): min={_fmt(f_min, '.2e')} Hz, "
            f"max={_fmt(f_max_val, '.2e')} Hz, mean={_fmt(f_mean, '.2e')} Hz\n\n"

            "Note: Full matrices are NOT shown to save tokens. "
            "Use the precomputed constants (D_hat_*, E_hat_*) directly in your objective."
        )

    # ------------------------------------------------------------------
    # 3. Level 1 Model Definition
    # ------------------------------------------------------------------
    def _build_init_level1model(self):
        model_src = self._read_model_source()

        return (
            "=== OffloadingModel Source ===\n"
            f"{model_src}\n\n"
            "=== Model Structure ===\n"
            "- ComputeTask: dataclass with D_l (local data), D_r (remote data), "
            "F (CPU cycles), tau (deadline), active[t] (per-slot activity flag).\n"
            "- UAV: dataclass with E_max (energy budget), f_max (max CPU freq), "
            "pos (current position).\n"
            "- OffloadingModel: Gurobi-based Level-1 BLP. "
            "Your goal is to replace its objective function.\n\n"
            "=== Key Methods ===\n"
            "- setupVars: Creates binary variables x_local[i,t] and x_offload[i,j,t].\n"
            "- setupCons: Ensures each active task is assigned to exactly one target "
            "(local or one UAV).\n"
            "- setupObj: Configurable objective - you design a new one via dynamic_obj_func.\n\n"
            "=== Precomputed Constants (available in self) ===\n"
            "- self.D_hat_local[i][t]:      local execution delay (seconds), scalar.\n"
            "- self.D_hat_offload[i][j][t]: remote offloading delay "
            "(upload + compute + download), scalar.\n"
            "- self.E_hat_comp[j][i][t]:    edge computing energy consumption (Joules), scalar.\n"
        )

    def _read_model_source(self):
        """Read the OffloadingModel source file for prompt embedding."""
        try:
            return Path(self.model_path).read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return (
                "[OffloadingModel source not yet available]\n"
                "The model file will be created at: " + str(self.model_path) + "\n"
                "For now, refer to the structured explanation below."
            )
        except Exception as exc:
            return f"[Error reading model source: {exc}]"

    # ------------------------------------------------------------------
    # 4. Output Format
    # ------------------------------------------------------------------
    def _build_obj_format(self):
        # NOTE: braces are escaped via .replace() at the end so that
        # downstream .format() calls won't break on JSON braces.
        raw = (
            "Generate response **EXACTLY AND MUST** in this JSON format:\n"
            '{"obj_description": "[Brief description of your objective strategy]",'
            '"obj_code": "def dynamic_obj_func(self):\n'
            '    print(\\"Creating dynamic objectives for Offloading Model\\")\n'
            '    # Define cost components (1-5 components)\n'
            '    cost1 = gb.quicksum(\n'
            '        self.D_hat_local[i][t] / self.task[i].tau\n'
            '        * self.x_local[i, t]\n'
            '        for i in self.taskList for t in self.timeList\n'
            '        if self.task[i].active[t]\n'
            '    )\n'
            '    cost2 = [Your Gurobi expression]\n'
            '    costs = [cost1, cost2]\n'
            '    weights = [w1, w2]  # Must match length of costs\n'
            '    objective = gb.quicksum(w*c for w, c in zip(costs, weights))\n'
            '    self.model.setObjective(objective, gb.GRB.MINIMIZE)"}\n'
            "\n"
            "Requirements:\n"
            "1. **NO EXPLANATIONS**: Only provide the JSON object — no markdown, no analysis.\n"
            "2. **Indentation**: Every line after `def` MUST start with exactly 4 spaces.\n"
            "3. **Validation**: Test your code mentally for valid Python before responding.\n"
            "4. JSON must contain exactly two keys: obj_description (string) and obj_code (code block)."
        )
        return raw.replace("{", "{{").replace("}", "}}")

    # ------------------------------------------------------------------
    # 5. Constraint Restrictions (Gurobi Coding Rules)
    # ------------------------------------------------------------------
    def _build_cons_restriction(self):
        raw = (
            "5. Code implementation requirements:\n"
            "   - Number of cost components: 1 <= n <= 5.\n"
            "   - Weights list must match the length of costs list.\n"
            "   - Final objective must use: gb.quicksum(w*c for w, c in zip(costs, weights)).\n"

            "6. Variable naming (MUST use exactly):\n"
            "   - self.x_local[i, t]          (binary: 1 = execute locally)\n"
            "   - self.x_offload[i, j, t]     (binary: 1 = offload task i to UAV j at time t)\n"
            "     Index order: i=task, j=UAV, t=time slot. DO NOT swap.\n"
            "   - self.D_hat_local[i][t]       (precomputed local delay, scalar constant)\n"
            "   - self.D_hat_offload[i][j][t]  (precomputed remote delay, scalar constant)\n"
            "   - self.E_hat_comp[j][i][t]     (precomputed edge energy, scalar constant)\n"
            "   - self.task[i].tau             (deadline, scalar constant)\n"
            "   - self.task[i].active[t]       (Python bool — use in `if` guards)\n"
            "   - self.uav[j].E_max           (max energy budget, scalar constant)\n"
            "   - self.alpha                   (delay weight, scalar constant)\n"
            "   - self.gamma_w                 (energy weight, scalar constant)\n"
            "   - self.M                       (big-M constant for linearization)\n"

            "7. Active-task gating (CRITICAL):\n"
            "   - Every summation over tasks MUST filter by self.task[i].active[t].\n"
            "   - Use Python `if` inside generator: "
            "`gb.quicksum(... for i in self.taskList for t in self.timeList if self.task[i].active[t])`.\n"
            "   - NEVER sum over inactive tasks — they have no valid precomputed constants.\n"

            "8. Full time-slot summation:\n"
            "   - When computing per-task or per-UAV aggregates, always sum across ALL t in self.timeList.\n"
            "   - Combine with the active-task filter: "
            "`for i in self.taskList for t in self.timeList if self.task[i].active[t]`.\n"
            "   - Do NOT optimize for a single time slot unless explicitly instructed.\n"

            "9. Scale awareness:\n"
            "   - Delays are in seconds (typically 0.001 ~ 1.0 s).\n"
            "   - Energy is in Joules (typically 0.1 ~ 100 J).\n"
            "   - Use self.alpha and self.gamma_w to balance them, or normalize by "
            "self.task[i].tau and self.uav[j].E_max respectively.\n"

            "10. Deadline awareness:\n"
            "   - Consider adding a soft penalty for tasks close to their deadline.\n"
            "   - Example: penalty = max(D_hat_offload[i][j][t] - task[i].tau, 0) "
            "(use Python max() since operands are constants).\n"

            "11. gb.quicksum rules:\n"
            "   a) NEVER nest gb.quicksum() inside another gb.quicksum().\n"
            "   b) Flatten multi-dimensional sums into a single gb.quicksum with multiple `for` clauses.\n"
            "      - Valid:   gb.quicksum(expr for i in ... for j in ... for t in ...)\n"
            "      - Invalid: gb.quicksum(gb.quicksum(...) for i in ...)\n"
            "   c) Do NOT use gb.quicksum for a single term — just use the expression directly.\n"

            "12. Expression function rules:\n"
            "   - Use gb.quicksum()/gb.max_()/gb.abs_() ONLY when the expression contains Gurobi variables.\n"
            "   - Use Python sum()/max()/abs() when working with pure constants (parameters).\n"

            "13. Quadratic term rules:\n"
            "   - For squared terms, use variable * variable directly.\n"
            "   - NEVER use Python list.append() with Gurobi expressions.\n"

            "14. Conditional logic handling:\n"
            "   - NEVER use Python if/else on Gurobi variables/expressions.\n"
            "   - For conditional cost components that depend on binary variables, "
            "multiply by the binary variable directly (big-M linearization).\n"

            "15. Nonlinear handling:\n"
            "   - For products of two binary variables: create auxiliary variable + big-M constraints.\n"
            "   - All precomputed constants (D_hat_*, E_hat_*) are scalars — multiplying them "
            "by a binary variable is always linear.\n"
        )
        return raw.replace("{", "{{").replace("}", "}}")

    # ------------------------------------------------------------------
    # Getter methods
    # ------------------------------------------------------------------
    def get_scenario(self):
        return self.prompt_scenario

    def get_static_info(self):
        return self.prompt_static_info

    def get_level1model(self):
        return self.prompt_init_level1model

    def get_obj_format(self):
        return self.prompt_obj_format

    def get_cons_restriction(self):
        return self.prompt_cons_restriction
