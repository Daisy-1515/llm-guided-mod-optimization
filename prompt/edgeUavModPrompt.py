"""
File: edgeUavModPrompt.py

Evolution strategies for Edge UAV offloading prompt templates.

Inherits EdgeUavPrompts and adds four mutation/generation strategies
used by the Harmony Search population manager:

    way1 — Fresh generation (complete new objective)
    way2 — Improvement on best individual (TODO: depends on OffloadingModel)
    way3 — Structural refactoring of best individual (TODO: depends on OffloadingModel)
    way4 — Resource-aware generation (energy + load balancing focus)
"""

from prompt.edgeUavPrompt import EdgeUavPrompts


class EdgeUavModPrompts(EdgeUavPrompts):
    """Prompt evolution strategies for Harmony Search.

    Usage
    -----
    >>> prompts = EdgeUavModPrompts(model_path="model/two_level/OffloadingModel.py")
    >>> prompts.set_scenario_info(tasks, uavs, time_slots)   # after scenario generation
    >>> text = prompts.get_prompt_way1(iter=3, task_info="...", uav_info="...")
    """

    def __init__(self, model_path):
        super().__init__(model_path)
        self._setup_template_components()

    # ------------------------------------------------------------------
    # Template assembly
    # ------------------------------------------------------------------
    def _setup_template_components(self):
        """Pre-assemble reusable prompt blocks from the five base components."""

        self._scenario_block = (
            f"{self.prompt_scenario}\n\n"
            "Below is the system scale summary:\n"
            f"{self.prompt_static_info}\n\n"
            "Below is the Level-1 model information. "
            "Your goal is to replace the function [dynamic_obj_func(self)]:\n"
            f"{self.prompt_init_level1model}\n\n"
        )

        self._iteration_block = (
            "--- Iteration Context ---\n"
            "This is the {iter}th optimization iteration.\n"
            "{task_info}\n"
            "{uav_info}\n\n"
        )

        self._base_instruction = (
            "Given the above information:\n"
            "1. {objective_instruction}\n"
            "2. Implement it as a Python function following Gurobi format.\n"
            f"{self.prompt_obj_format}\n"
            f"{self.prompt_cons_restriction}"
        )

    def refresh_scenario_block(self):
        """Rebuild _scenario_block after set_scenario_info() updates static info.

        Must be called if set_scenario_info() is invoked after __init__.
        """
        self._setup_template_components()

    # ------------------------------------------------------------------
    # Prompt builders (internal)
    # ------------------------------------------------------------------
    def _build_core_prompt(self, context_block, instruction):
        """Assemble a complete prompt from context + iteration + instruction.

        Parameters
        ----------
        context_block : str
            The scenario context (typically self._scenario_block).
        instruction : dict
            Must contain:
              - "iteration": {"iter": int}
              - "task_info": str
              - "uav_info": str
              - "objective_instruction": str
        """
        iter_text = self._iteration_block.format(
            iter=instruction["iteration"]["iter"],
            task_info=instruction.get("task_info", ""),
            uav_info=instruction.get("uav_info", ""),
        )
        instr_text = self._base_instruction.format(
            objective_instruction=instruction["objective_instruction"],
        )
        return f"{context_block}{iter_text}{instr_text}"

    def _build_inspirational_prompt(self, best_ind, instruction):
        """Assemble a prompt that references a previous best individual.

        Parameters
        ----------
        best_ind : str or dict
            The best individual's description, code, and fitness from a prior run.
        instruction : dict
            Same structure as _build_core_prompt, plus "objective_instruction".
        """
        iter_text = self._iteration_block.format(
            iter=instruction["iteration"]["iter"],
            task_info=instruction.get("task_info", ""),
            uav_info=instruction.get("uav_info", ""),
        )
        instr_text = self._base_instruction.format(
            objective_instruction=instruction["objective_instruction"],
        )
        return (
            f"{self._scenario_block}"
            "--- Previous Best Run ---\n"
            "Below is one of your previous runs that achieved a good cost score. "
            "Its description, objective code, and evaluated system cost are provided:\n"
            f"{best_ind}\n\n"
            f"{iter_text}"
            f"{instr_text}"
        )

    # ------------------------------------------------------------------
    # Way 1: Fresh generation
    # ------------------------------------------------------------------
    def get_prompt_way1(self, iter, task_info, uav_info):
        """Generate a prompt for creating a completely new objective function.

        Parameters
        ----------
        iter : int
            Current Harmony Search iteration index.
        task_info : str
            String summary of current task states (active tasks, urgency, etc.).
        uav_info : str
            String summary of current UAV states (positions, energy levels, etc.).
        """
        instruction = {
            "iteration": {"iter": iter},
            "task_info": task_info,
            "uav_info": uav_info,
            "objective_instruction": (
                "Please generate a **new objective function** for the Level-1 "
                "offloading assignment problem. Your objective should creatively "
                "balance task completion delay, edge computing energy, and assignment "
                "quality. Consider proximity, urgency, and load distribution."
            ),
        }
        return self._build_core_prompt(self._scenario_block, instruction)

    # ------------------------------------------------------------------
    # Way 2: Improvement on best individual (TODO)
    # ------------------------------------------------------------------
    def get_prompt_way2(self, iter, task_info, uav_info, best_ind):
        """Generate a prompt for improving the best-performing objective.

        TODO: The best_ind structure depends on OffloadingModel, which is
        not yet implemented. This method is a placeholder — it will be
        completed after OffloadingModel is available and the individual
        evaluation pipeline (hsIndividualMultiCall) is adapted.

        Parameters
        ----------
        best_ind : str or dict
            Best individual from previous generation. Structure TBD
            (will include obj_description, obj_code, fitness score).
        """
        instruction = {
            "iteration": {"iter": iter},
            "task_info": task_info,
            "uav_info": uav_info,
            "objective_instruction": (
                "Develop an **improved objective function** based on the previous best run:\n"
                "a) Preserve approximately 50% of the original structure.\n"
                "b) Refine the weighting strategy - consider adjusting alpha/gamma_w balance.\n"
                "c) Add or improve penalty terms for deadline violations or load imbalance.\n"
                "d) Ensure all active-task gating rules are maintained."
            ),
        }
        return self._build_inspirational_prompt(best_ind, instruction)

    # ------------------------------------------------------------------
    # Way 3: Structural refactoring (TODO)
    # ------------------------------------------------------------------
    def get_prompt_way3(self, iter, task_info, uav_info, best_ind):
        """Generate a prompt for fundamentally refactoring the objective.

        TODO: Same dependency on OffloadingModel as way2.
        This method is a placeholder.

        Parameters
        ----------
        best_ind : str or dict
            Best individual from previous generation. Structure TBD.
        """
        instruction = {
            "iteration": {"iter": iter},
            "task_info": task_info,
            "uav_info": uav_info,
            "objective_instruction": (
                "**Reinvent the objective function** from scratch, inspired by "
                "the previous best run but with a fundamentally different approach:\n"
                "a) The overall goal is to minimize weighted system cost "
                "(delay + energy) as evaluated by the simulator.\n"
                "b) Try a completely different cost decomposition or weighting scheme.\n"
                "c) Consider creative strategies: QoS tiers, proximity clustering, "
                "energy-proportional assignment, or fairness-aware allocation.\n"
                "d) Maintain all variable naming and gating rules."
            ),
        }
        return self._build_inspirational_prompt(best_ind, instruction)

    # ------------------------------------------------------------------
    # Way 4: Resource-aware generation
    # ------------------------------------------------------------------
    def get_prompt_way4(self, iter, task_info, uav_info):
        """Generate a prompt with explicit resource-awareness guidance.

        This strategy directs the LLM to focus on UAV energy budgets,
        compute capacity limits, and load balancing — aspects that
        way1's generic instruction might overlook.

        Parameters
        ----------
        iter : int
            Current Harmony Search iteration index.
        task_info : str
            String summary of current task states.
        uav_info : str
            String summary of current UAV states (must include energy levels).
        """
        resource_guidance = (
            "--- Resource-Aware Guidance ---\n"
            "Pay special attention to the following resource constraints:\n\n"
            "1. **Energy Budget Sensitivity**:\n"
            "   - Each UAV has a finite energy budget (self.uav[j].E_max).\n"
            "   - Penalize assigning tasks to UAVs whose cumulative energy cost "
            "(sum of E_hat_comp[j][i][t] over assigned tasks) approaches E_max.\n"
            "   - Consider a per-UAV energy utilization ratio as a penalty factor.\n\n"
            "2. **Load Balancing**:\n"
            "   - Avoid concentrating all tasks on a single UAV.\n"
            "   - Add a linear load-balancing penalty to encourage even distribution.\n"
            "   - Example (linear per-UAV load): gb.quicksum(self.x_offload[i, j, t] "
            "for i in self.taskList for j in self.uavList for t in self.timeList "
            "if self.task[i].active[t])\n"
            "   - For per-UAV quadratic penalties, define auxiliary variables in constraints; "
            "do NOT nest gb.quicksum.\n\n"
            "3. **Deadline-Energy Tradeoff**:\n"
            "   - Urgent tasks (small tau) should prefer the nearest UAV even if "
            "it costs more energy.\n"
            "   - Non-urgent tasks should prefer the UAV with the most remaining energy.\n\n"
            "4. **Future-Slot Reservation**:\n"
            "   - If a UAV is heavily loaded in early time slots, reserve capacity "
            "for later slots by discouraging further assignment.\n"
        )

        instruction = {
            "iteration": {"iter": iter},
            "task_info": task_info,
            "uav_info": uav_info,
            "objective_instruction": (
                "Generate a **resource-aware objective function** that explicitly "
                "accounts for UAV energy budgets, compute capacity, and load balance. "
                "Follow the Resource-Aware Guidance provided above."
            ),
        }

        iter_text = self._iteration_block.format(
            iter=instruction["iteration"]["iter"],
            task_info=task_info,
            uav_info=uav_info,
        )
        instr_text = self._base_instruction.format(
            objective_instruction=instruction["objective_instruction"],
        )
        return (
            f"{self._scenario_block}"
            f"{resource_guidance}\n"
            f"{iter_text}"
            f"{instr_text}"
        )
