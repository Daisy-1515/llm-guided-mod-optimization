"""
* File: basicPrompt.py
* Author: Yi
*
* created on 2025/02/01
"""
"""
@package basicPrompt.py
@brief This module handles basic prompts template.
"""
import pandas as pd
class basicPrompts():
    """
    @class basicPrompts
    @brief Manages basic prompts template.
    """
    def __init__(self, mapPath, modelPath, enableMemory=False, enableFuture=False):
        self.level2Obj = "the passenger waiting time (before pickup)"
        self.prompt_scenario = (
                "Act as an AI transportation optimization expert designing the primary objective function for a two-level real-time mobility system:\n"
                "1. **System Overview**:\n"
                "- Simulator (executes commands) ↔ Dispatcher (calculates strategies) closed loop\n"
                "- Periodic updates: Taxi states (idle/busy locations), passenger requests/dropoffs\n"
                "- Deterministic environment with full driver compliance\n\n"
                
                "2. **Optimization Structure**:\n"
                "First Level: Passenger-taxi assignment problem\n"
                "Second Level: Fixed TSP sequencing (minimizes {self.level2Obj}) - SOLVED\n\n"
                
                "3. **Your Task**:\n"
                "Design novel first-level objective function using:\n"
                "- Static map data\n"
                "- Taxi locations (current for idle, future ETA for busy)\n"
                "- Passenger request details\n\n"
                
                "4. **Key Requirements**:\n"
                "- Enable timely service for all passengers\n"
                "- Compatible with Gurobi-based MILP formulation\n"
                "- Account for dynamic re-assignment (previous unfinished tasks discarded)\n"
                "- Balance assignment efficiency with second-level sequencing feasibility"
            )
        od_matrix = pd.read_csv(mapPath, index_col=0)
        od_matrix = od_matrix.astype(int)
        self.prompt_static_map_info = (
                #f"{od_matrix.to_string()}\n"
                f"{od_matrix.index}\n"
                "=== OD Matrix Explanation === \n"
                "The above info is the zone index, denoting origins/destinations.\n"
                f"1. Matrix Dimensions: {od_matrix.shape[0]} origins × {od_matrix.shape[1]} destinations\n"
                f"2. Index Values (Origins): {od_matrix.index.tolist()[:5]}... (total {len(od_matrix.index)} locations)\n"
                f"3. Column Values (Destinations): {od_matrix.columns.tolist()[:5]}... (total {len(od_matrix.columns)} locations)\n"
                "4. Cell Values: Travel time in seconds between origin (row) and destination (column)\n"
                "Example Interpretation:\n"
                f"- From location 4 to 261: {od_matrix.loc[4, '261']:.1f} seconds\n"
                f"- From location 261 to 4: {od_matrix.loc[261, '4']:.1f} seconds\n"
                f"- Diagonal values (e.g., 4→4) show {od_matrix.loc[4, '4']:.1f} seconds, indicating same location\n"
                "Key Observations:\n"
                "- This is a square matrix (n×n) representing pairwise travel times\n"
                "- Contains 0 values on diagonal (self-to-self travel)\n"
                "- This is passed to assignmentModel class as argument \"distMatrix\"\n"
            )
        
        self.prompt_data_format = {
            "Argument_explanation": {
                "core_DataClass": [
                    "Taxi: data class, include start_pos (same index in OD Matrix above), arrival_time, and index (taxi index).",
                    "Passenger: data class, include origin (same index in OD Matrix above), destination (same index in OD Matrix above), arrTime, and index (passenger index)."
                ], 
                "core_FunctionArguments": [
                    "self.distMatrix: dictionary of dictionary, key1 is origin id, key2 is destination id, value is travel time.",
                    "self.taxi: dictionary: key is taxi index, value is the instance of dataclass Taxi",
                    "self.passenger: dictionary: key is passenger index, value is the instance of dataclass Passenger."
                ]
                }
        }
                
        with open(modelPath, 'r') as f:
            class_code = f.read()

        self.prompt_init_level1model = {
            "level1model_definition": class_code,
            "structured_explanation": {
                "core_components": [
                    "Taxi: data class, include start_pos (same index in OD Matrix above), arrival_time, and index (taxi index).",
                    "Passenger: data class, include origin (same index in OD Matrix above), destination (same index in OD Matrix above), arrTime, and index (passenger index).",
                    "AssignmentModel: Gurobi-based optimization engine - first-level model."
                ], 
                "key_methods": {
                    "setupVars": "Creates binary assignment variables y[v, p].",
                    "setupCons": "Ensures each passenger is assigned to exactly one taxi.",
                    "setupObj": "Configurable objective function (your should design a new one)."
                }
            }
        }
        
        self.llmHasMemory = enableMemory
        self.llmHasFuture = enableFuture
        
        self.prompt_obj_format = (
        "Generate response **EXACTLY AND MUST** in this JSON format:\n"
        r'{"obj_description": "[Your custom objective *brief* description]",'
        r'"obj_code": "def dynamic_obj_func(self):\n'
        r'    print(\"Creating dynamic objectives for Assignment Model\")\n'
        r'    # Custom cost components (define as needed)'
        r'    cost1 = [Proper Gurobi expression]\n'
        r'    cost2 = [Proper Gurobi expression]\n'
        r'    # Add more components as needed\n'
        r'    # Custom weights (match costs length)'
        r'    weights = ['
        r'        [Your custom weight 1],'
        r'        [Your custom weight 2],'
        r'        # Add matching weights'
        r'    ]'
        r'    # Build objective expression'
        r'    objective = sum(w*c for w,c in zip(weights, costs))\n'
        r'    self.model.setObjective(objective, gb.GRB.MINIMIZE)"}'
        "\nRequirements:\n"
        "1. **NO EXPLANATIONS**: Only provide the JSON object - no additional text/markdown/analysis\n"
        "2. **Indentation**: Every line after `def` MUST start with 4 spaces\n"
        "3. **Validation**: Test your code for valid Python indentation before responding\n"
        "4. JSON structure must strictly contain these keys:\n"
        "   - obj_description (string)\n"
        "   - obj_code (code block)\n"
        ).replace("{", "{{").replace("}", "}}")
            
        self.prompt_cons_restriction = (
        "5. Code implementation requirements:\n"
        "   - Store cost components and weights in lists\n"
        "   - Number of cost components: 1 ≤ n ≤ 5\n"
        "   - Weights list must have same length as costs list\n"
        "   - Ensure full utilization of taxis\n"
        "   - Maintain Gurobi expression validity\n"
        "6. Variables and parameters can only use the following items:\n"
        "   - self.y[v,p]   (variables)\n"
        "   - self.distMatrix   (parameters)\n"
        "   - self.taxi dictionaries (containing dataclass instances with PARAMETER values: start_pos, arrival_time, index)\n"
        "   - self.passenger dictionaries (containing dataclass instances with PARAMETER values: origin, destination, arrTime, index)\n"
        "   - self.M    (parameter)\n"
        "7. When calculating waiting time (taxi arrival vs passenger request time):\n"
        "   - If using parameter values (self.taxi[v].arrival_time & self.passenger[p].arrTime), use Python max()\n"
        "   - Example: max(taxi_arrival - passenger_time, 0)\n"
        "   - Only use gb.max_() if operands contain Gurobi variables\n"
        "8. Final objective expression must use sum(zip()) structure\n"
        "9. NEVER multiply Gurobi variables with Gurobi expressions:\n"
        "   - Invalid: y[v,p] * gb.max_(expression_with_vars, 0)\n"
        "   - Valid: y[v,p] * max(param1 - param2, 0) (when using Python max with parameters)\n"
        "10. Expression function rules:\n"
        "   - Use **gb.quicksum()/gb.max_()/gb.abs_()** ONLY when containing **variables**\n"
        "   - Use **sum()/max()/abs()** when working with pure **parameters**\n"
        "11. Expression construction rules:\n"
        "   a) NEVER nest Gurobi functions like gb.quicksum() inside other Gurobi functions\n"
        "   b) Use gb.quicksum() ONLY for summing multiple terms in one dimension\n"
        "      - Valid: gb.quicksum(self.y[v,p] * param for p in...)\n"
        "      - Invalid: gb.quicksum(gb.quicksum(...)) or quicksum(single_term)\n"
        "   c) When creating multi-dimensional sums:\n"
        "      - Use nested Python list comprehensions inside a SINGLE gb.quicksum()\n"
        "      - Example: gb.quicksum(self.y[v,p] * param for v in... for p in...)\n"
        "12. Quadratic term rules:\n"
        "   - For squared terms, use variable * variable directly\n"
        "   - Example: (sum(self.y[v,p] for p...)) * (sum(...)) is valid quadratic\n"
        "   - NEVER use Python list.append() with Gurobi expressions\n"
        "13. Conditional logic handling:\n"
        "   - NEVER use Python if/else with Gurobi variables/expressions\n"
        "   - Use gb.max_()/gb.min_()/gb.abs_() instead of conditional multipliers\n"
        "14. Nonlinear Handling:\n"
        "   - For multiplication of two variables:\n"
        "     * Create auxiliary variables 'binary_var'\n"
        "     * Implement Big-M constraints using self.M\n"
        "     * Example: wait_var >= expr - self.M*(1 - binary_var),  wait_var >= -expr - self.M*(1 - binary_var)\n"
        ).replace("{", "{{").replace("}", "}}")
        
        self.prompt_future_impacts = ("3. With these technical requirements:\n"
            "   a) Incorporate temporal awareness through:\n"
            "      - Implicit state transition modeling\n" 
            "      - Dynamic weight adaptation patterns\n"
            "      - Time horizon prediction heuristics\n"
            "   b) Use these predictive techniques:\n"
            "      - Anticipatory cost components (e.g. expected future demand)\n"
            "      - Discounted future cost estimation (γ=0.95)\n"
            "      - Resource utilization trajectory modeling\n"
            "3. Optimization strategy requirements:\n"
            "   - Current-step cost: Direct observable metrics\n"
            "   - Future-impact cost: Estimated through:\n"
            "      * Taxi repositioning probability matrices\n"
            "      * Passenger demand forecasting\n"
            "      * Resource depletion projections\n"
            "   - Balance weights: α*current_cost + (1-α)*future_impact (0.6≤α≤0.8)\n").strip()

    def get_scenario(self):
        return self.prompt_scenario
    
    def get_static_map_info(self):
        return self.prompt_static_map_info
    
    def get_level1model(self):
        return self.prompt_init_level1model
    
    def get_obj_format(self):
        return self.prompt_obj_format
    
    
    
        