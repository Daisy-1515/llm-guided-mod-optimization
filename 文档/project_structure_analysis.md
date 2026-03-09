# Project Structure Analysis Report

## Project Overview

**Project Name:** LLM-Guided Mobility-on-Demand Optimization
**Repository:** llm-guided-mod-optimization
**Purpose:** Hierarchical optimization system that integrates Large Language Models (LLM) with mathematical optimization for mobility-on-demand platforms (ride-hailing services)

**Key Innovation:** Hybrid LLM-optimizer framework that uses:
- LLM as meta-objective designer (evolves strategic objectives)
- Mathematical optimizer as constraint enforcer (ensures feasibility)
- Harmony Search heuristics as prompt evolver (refines LLM prompts iteratively)

**Research Context:** Published at NeurIPS 2025

---

## Directory Structure

```
llm-guided-mod-optimization/
├── config/                    # Configuration management
│   ├── env/                   # Environment variables (API keys)
│   │   └── .env
│   ├── config.py              # Configuration parser
│   ├── firstLevelExample.py   # Example configuration
│   └── setting.cfg            # Main settings file
│
├── heuristics/                # Harmony Search algorithm implementation
│   ├── hsFrame.py             # Main evolutionary framework
│   ├── hsPopulation.py        # Population management
│   ├── hsIndividual.py        # Individual solution representation
│   ├── hsIndividualMultiCall.py  # Multi-call variant
│   ├── hsSorting.py           # Population sorting strategies
│   └── hsUtils.py             # Utility functions
│
├── llmAPI/                    # LLM interface layer
│   ├── llmInterface.py        # Factory pattern for LLM platforms
│   └── llmInterface_huggingface.py  # HuggingFace implementation
│
├── model/                     # Optimization models
│   ├── milpModel.py           # Base MILP model (Gurobi)
│   └── two_level/             # Two-level optimization
│       ├── AssignmentModel.py        # Vehicle-passenger assignment
│       ├── AssignmentModel_googleOR.py  # Google OR-Tools variant
│       └── SequencingModel.py        # Route sequencing
│
├── prompt/                    # Prompt engineering
│   ├── basicPrompt.py         # Base prompt templates
│   └── modPrompt.py           # MOD-specific prompts
│
├── simulator/                 # Simulation environment
│   └── SimClass.py            # Dynamic system simulator
│
├── inputs/                    # Input data
│   ├── Chicago_WNC/           # Chicago dataset
│   └── downtown/              # Downtown dataset
│
├── instances/                 # Problem instances
│   ├── chicago/
│   └── downtown/
│
├── resExample/                # Example results
│   └── 900s_150pass_100taxi/  # Sample scenario results
│       ├── run1/              # Multiple runs
│       ├── run2/
│       └── run3/
│
├── image/                     # Documentation images
├── dataCommon.py              # Common data structures
├── scenarioGenerator.py       # Scenario generation
├── testAll.py                 # Main entry point
└── dependencies.yml           # Conda environment specification
```

---

## Core Components Analysis


### 1. Configuration System (`config/`)

**Purpose:** Centralized configuration management for all system parameters

**Key Files:**
- `config.py` - Main configuration parser with type-safe value extraction
- `setting.cfg` - User-editable settings file (not in repo)
- `.env` - API credentials and endpoints (not in repo)

**Configuration Categories:**
1. **LLM Settings:** Platform (HuggingFace/OpenAI/DeepSeek/Nvidia), model name, API credentials
2. **Prompt Settings:** Map paths, model paths for context
3. **Harmony Search Settings:** Population size, iterations, HMCR, PAR parameters
4. **Simulation Settings:** Runtime, vehicle/passenger counts, city selection

**Design Pattern:** 
- Uses ConfigObj for .cfg parsing
- python-dotenv for environment variables
- Platform-specific API variable mapping
- Built-in validation with missing field detection

**Default Objective Function:**
The config includes a default multi-objective function combining:
- Cost1: Passenger waiting time penalty
- Cost2: Taxi-to-pickup distance
- Cost3: Taxi-to-destination distance  
- Cost4: Load balancing (quadratic penalty for multiple assignments)

---

### 2. Heuristics Module (`heuristics/`)

**Purpose:** Implements Harmony Search algorithm for prompt evolution

**Architecture:**
```
HarmonySearchSolver (hsFrame.py)
    ├── hsPopulation - Manages population of solutions
    │   └── hsIndividual - Individual prompt/objective representations
    ├── hsSorting - Fitness-based sorting
    └── hsUtils - Helper functions
```

**Key Concepts:**
- **Harmony Memory (HM):** Population of candidate objective functions
- **HMCR (Harmony Memory Considering Rate):** Probability of selecting from existing solutions
- **PAR (Pitch Adjustment Rate):** Probability of local perturbation
- **Fitness Evaluation:** Each individual is evaluated via optimization solver + simulation

**Workflow:**
1. Initialize population with diverse objective functions
2. For each generation:
   - Generate new solutions via harmony memory operations
   - Combine old and new populations
   - Sort by fitness and select top performers
   - Save population state to JSON

---

### 3. LLM Interface (`llmAPI/`)

**Purpose:** Abstraction layer for multiple LLM platforms

**Design Pattern:** Factory pattern with platform-specific implementations

**Current Implementation:**
- `InterfaceAPI` - Factory class using `__new__` for dynamic instantiation
- `InterfaceAPI_huggingface` - HuggingFace API implementation

**Extensibility:**
The module is designed for easy extension. To add new platforms:
1. Create `llmInterface_<platform>.py`
2. Implement `getResponse(prompt)` method
3. Register in factory's `__new__` method

**Supported Platforms (via config):**
- HuggingFace (implemented)
- OpenAI (template provided in comments)
- DeepSeek (config support)
- Nvidia (config support)

---

### 4. Optimization Models (`model/`)

**Purpose:** Mathematical optimization solvers for vehicle routing and assignment

**Base Model (`milpModel.py`):**
- Uses Gurobi as MILP solver
- Implements general optimization template
- Key components: distance matrix, waypoints, taxi/passenger lists
- Configurable gap tolerance and big-M constraints

**Two-Level Optimization (`model/two_level/`):**

1. **AssignmentModel.py** - Vehicle-to-passenger assignment (Gurobi)
   - Decides which taxi serves which passenger
   - Considers arrival times, distances, capacity

2. **AssignmentModel_googleOR.py** - Alternative using Google OR-Tools
   - Same problem, different solver
   - Useful for comparison or licensing constraints

3. **SequencingModel.py** - Route sequencing optimization
   - Determines optimal order of pickups/dropoffs
   - Considers time windows and vehicle capacity

**Hierarchical Decomposition:**
- Upper level: Strategic objective design (LLM-guided)
- Lower level: Operational routing (mathematical optimization)

---

### 5. Simulation Environment (`simulator/`)

**Purpose:** Dynamic system simulator for evaluating solutions

**Key Class: SimEnvironment**
- Tracks system state over time
- Manages taxi positions, task assignments, and execution
- Computes performance metrics:
  - Total waiting time (passengers)
  - Total travel time (taxis)
  - Total idle time (taxis)

**Data Structures:**
- `task_archive`: Historical task assignments per taxi
- `command`: Current task queue per taxi
- `state_info`: Real-time taxi states
- `dist_mat`: Distance/time matrix between locations

**Workflow:**
1. Initialize with taxi fleet and distance matrix
2. Receive optimization decisions
3. Simulate task execution over time
4. Track key performance indicators
5. Return fitness metrics for heuristic evaluation

---

### 6. Prompt Engineering (`prompt/`)

**Purpose:** Manages prompt templates for LLM interactions

**Key Files:**
- `basicPrompt.py` - Base prompt templates and structures
- `modPrompt.py` - Mobility-on-Demand specific prompts

**Prompt Strategy:**
The system uses prompts to guide the LLM in generating objective functions that:
- Balance multiple competing goals (waiting time, distance, load balancing)
- Respect domain constraints (capacity, time windows)
- Adapt to scenario-specific characteristics
- Incorporate feedback from optimization solver

**Context Injection:**
Prompts likely include:
- Current system state (taxi positions, passenger requests)
- Historical performance metrics
- Distance/time matrices
- Previous objective functions and their fitness scores

---

### 7. Data Management

**Common Data Structures (`dataCommon.py`):**
- Taxi class: Vehicle state, position, capacity, availability
- Passenger class: Origin, destination, arrival time, service requirements
- Task class: Assignment details, timing information

**Input Data (`inputs/`):**
- Chicago_WNC: Chicago West North Central dataset
- downtown: Downtown area dataset
- Contains: Distance matrices, waypoint lists, demand patterns

**Problem Instances (`instances/`):**
- Pre-configured test scenarios
- chicago/ and downtown/ variants
- Different scales and characteristics for benchmarking

---

### 8. Scenario Generation (`scenarioGenerator.py`)

**Purpose:** Creates test scenarios with taxis and passengers

**Key Class: TaskGenerator**
- Generates random or structured scenarios
- Configurable parameters: number of vehicles, passengers, time horizon
- Loads distance matrices and waypoint data
- Returns scenario information for optimization

**Integration:**
Called by `testAll.py` to create scenarios based on config parameters before running the harmony search solver.

---

### 9. Main Entry Point (`testAll.py`)

**Purpose:** Orchestrates the entire optimization pipeline

**Execution Flow:**
```python
1. Load configuration (config.cfg + .env)
2. Generate scenario (taxis, passengers, map data)
3. Initialize Harmony Search solver
4. Run evolutionary optimization
   - LLM generates objective functions
   - Optimizer solves with each objective
   - Simulator evaluates solutions
   - Heuristic evolves population
5. Save results to ./discussion/
```

**Simple Interface:**
```bash
python testAll.py
```
All configuration is externalized, making it easy to run different experiments.

---

## Dependencies Analysis

**Environment Management:** Conda-based (`dependencies.yml`)

**Core Dependencies:**

1. **Optimization Solvers:**
   - `gurobipy` - Commercial MILP solver (requires license)
   - `ortools` - Google's open-source optimization tools

2. **LLM Integration:**
   - `transformers` - HuggingFace model interface
   - `tiktoken` - Token counting for API usage
   - `sentence-transformers` - Embedding models

3. **Data Processing:**
   - `pandas` - Data manipulation
   - `numpy` - Numerical computations
   - `joblib` - Parallel processing and caching

4. **Configuration:**
   - `configobj` - Configuration file parsing
   - `python-dotenv` - Environment variable management

5. **API Communication:**
   - `requests` - HTTP requests for LLM APIs

**License Considerations:**
- Gurobi requires academic or commercial license
- Academic users can get free licenses
- OR-Tools provides open-source alternative for some models

---

## Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     testAll.py (Main)                       │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌────────┐    ┌──────────┐    ┌──────────┐
    │ Config │    │ Scenario │    │ Harmony  │
    │ Parser │    │Generator │    │  Search  │
    └────────┘    └──────────┘    └─────┬────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
                    ▼                   ▼                   ▼
              ┌──────────┐        ┌──────────┐       ┌──────────┐
              │   LLM    │        │Optimizer │       │Simulator │
              │Interface │        │  Model   │       │  Engine  │
              └──────────┘        └──────────┘       └──────────┘
                    │                   │                   │
                    └───────────────────┼───────────────────┘
                                        │
                                        ▼
                              ┌──────────────────┐
                              │ Fitness Metrics  │
                              │  & Population    │
                              │    Evolution     │
                              └──────────────────┘
```

**Iterative Loop:**
1. LLM generates objective function code
2. Optimizer solves MILP with that objective
3. Simulator evaluates solution quality
4. Fitness guides next generation of objectives
5. Repeat until convergence or max iterations

---

## Key Design Patterns

### 1. Factory Pattern (LLM Interface)
- `InterfaceAPI` uses `__new__` to instantiate platform-specific implementations
- Easy to extend for new LLM providers
- Centralizes API differences

### 2. Strategy Pattern (Optimization Models)
- Multiple solver implementations (Gurobi, OR-Tools)
- Interchangeable without changing client code
- Allows benchmarking different approaches

### 3. Template Method (MILP Model)
- `generalModel` defines optimization skeleton
- Subclasses implement specific `setupVars()`, `setupCons()`, `setupObj()`
- Ensures consistent solver workflow

### 4. Evolutionary Algorithm (Harmony Search)
- Population-based metaheuristic
- Combines exploration (random) and exploitation (memory-based)
- Fitness-driven selection

---

## Configuration Requirements

**Before Running:**

1. **Create `config/setting.cfg`** with:
   ```ini
   [llmSettings]
   platform = HuggingFace
   model = meta-llama/Llama-3.1-70B-Instruct
   
   [promptSettings]
   mapPath = ./inputs/downtown/
   modelPath = ./model/
   
   [hsSettings]
   popSize = 3
   iteration = 5
   HMCR = 0.9
   PAR = 0.5
   
   [simSettings]
   simulationTime = 600
   totalVehicleNum = 60
   totalPassNum = 70
   city = NYC
   ```

2. **Create `config/env/.env`** with:
   ```bash
   HUGGINGFACEHUB_API_TOKEN=your_token_here
   HUGGINGFACE_ENDPOINT=https://api-inference.huggingface.co/models/meta-llama/Llama-3.1-70B-Instruct
   ```

3. **Install Gurobi License:**
   - Academic: https://www.gurobi.com/academia/
   - Commercial: Requires paid license

---

## Output and Results

**Results Directory:** `./discussion/` (created at runtime)

**Output Format:** JSON files per iteration
- `population_result_0.json` - Initial population
- `population_result_1.json` - After 1st generation
- `population_result_N.json` - After Nth generation

**Result Structure (per individual):**
```json
{
  "objective_function": "def dynamic_obj_func(self): ...",
  "fitness_score": 1234.56,
  "waiting_time": 567.89,
  "travel_time": 890.12,
  "idle_time": 345.67,
  "generation": 3
}
```

**Example Results:** `resExample/900s_150pass_100taxi/`
- Contains 3 runs with 10 iterations each
- Demonstrates convergence behavior
- Useful for validation and benchmarking

---

## Extensibility Points

### Adding New LLM Platforms
1. Create `llmAPI/llmInterface_<platform>.py`
2. Implement `getResponse(prompt)` method
3. Add platform to factory in `llmInterface.py`
4. Add API variables to `config.py` platform_envs dict

### Adding New Optimization Models
1. Inherit from `generalModel` in `milpModel.py`
2. Implement `setupVars()`, `setupCons()`, `setupObj()`
3. Use in harmony search evaluation

### Customizing Objective Functions
1. Modify default in `config.py`
2. Adjust prompt templates in `prompt/modPrompt.py`
3. Update LLM instructions for domain-specific goals

### Adding New Heuristics
1. Create new sorting strategy in `heuristics/hsSorting.py`
2. Implement diversity metrics or multi-objective sorting
3. Plug into `HarmonySearchSolver`

---

## Code Quality Observations

**Strengths:**
- Clear separation of concerns (config, optimization, simulation, LLM)
- Extensible architecture with factory and template patterns
- Comprehensive documentation in docstrings
- Type hints in newer modules (SimClass.py)
- Configurable parameters externalized

**Areas for Enhancement:**
- Missing `setting.cfg` template in repository
- Limited error handling in API calls
- No unit tests visible
- Hard-coded paths in some modules
- Could benefit from logging framework instead of print statements

**Security Considerations:**
- API keys properly externalized to .env
- .env file correctly excluded from git (assumed)
- No hardcoded credentials visible

---

## Technical Workflow Summary

**Complete Execution Pipeline:**

1. **Initialization Phase:**
   - Load configuration from `setting.cfg` and `.env`
   - Generate scenario (taxi fleet, passenger requests, distance matrix)
   - Initialize harmony search with population size N

2. **Population Initialization:**
   - LLM generates N diverse objective functions
   - Each objective is a Python function combining multiple cost terms
   - Initial population evaluated and sorted by fitness

3. **Evolutionary Loop (per generation):**
   - **Selection:** Choose from harmony memory (HMCR probability)
   - **Mutation:** Apply pitch adjustment (PAR probability)
   - **Generation:** LLM creates new objective functions
   - **Evaluation:** 
     - Parse objective function code
     - Inject into MILP model
     - Solve optimization problem
     - Simulate solution in dynamic environment
     - Compute fitness metrics
   - **Selection:** Combine old and new populations, keep top N
   - **Archive:** Save population state to JSON

4. **Termination:**
   - After max iterations or convergence
   - Best objective function represents learned strategy

---

## Research Contributions

**Novel Aspects:**

1. **LLM as Meta-Optimizer:** Uses language models to design optimization objectives rather than solve problems directly

2. **Hybrid Intelligence:** Combines semantic reasoning (LLM) with mathematical rigor (MILP solver)

3. **Prompt Evolution:** Applies evolutionary algorithms to prompt engineering, creating a meta-learning system

4. **Hierarchical Decomposition:** Strategic layer (LLM) guides operational layer (optimizer)

5. **Feedback Loop:** Optimization feasibility and simulation results guide LLM's next generation

**Advantages over Traditional Approaches:**
- Adapts objectives to scenario characteristics
- Discovers non-obvious objective combinations
- Reduces need for manual objective tuning
- Leverages domain knowledge encoded in LLM

---

## Usage Guide

**Quick Start:**

```bash
# 1. Clone and setup environment
git clone https://github.com/yizhangele/llm-guided-mod-optimization.git
cd llm-guided-mod-optimization
conda env create -f dependencies.yml
conda activate llm-guided-mod-optimization

# 2. Configure settings
# Create config/setting.cfg with your parameters
# Create config/env/.env with API credentials

# 3. Setup Gurobi license
# Follow: https://www.gurobi.com/academia/

# 4. Run optimization
python testAll.py
```

**Expected Runtime:**
- Depends on: population size, iterations, problem size, LLM response time
- Example: 3 population × 5 iterations × ~30s per evaluation = ~7.5 minutes
- Results saved incrementally to `./discussion/`

---

## File Dependencies Map

**Critical Path:**
```
testAll.py
  ├── config/config.py
  │     └── config/env/.env
  ├── scenarioGenerator.py
  │     ├── dataCommon.py
  │     └── inputs/{city}/
  └── heuristics/hsFrame.py
        ├── heuristics/hsPopulation.py
        │     ├── heuristics/hsIndividual.py
        │     │     ├── llmAPI/llmInterface.py
        │     │     │     └── llmAPI/llmInterface_huggingface.py
        │     │     ├── model/milpModel.py
        │     │     │     └── model/two_level/*.py
        │     │     ├── simulator/SimClass.py
        │     │     └── prompt/modPrompt.py
        │     └── heuristics/hsUtils.py
        └── heuristics/hsSorting.py
```

---

## Potential Improvements

**Short-term Enhancements:**
1. Add `setting.cfg` template to repository
2. Implement retry logic for LLM API calls
3. Add logging framework (replace print statements)
4. Create validation for LLM-generated code before execution
5. Add progress bars for long-running operations

**Medium-term Enhancements:**
1. Implement multi-objective optimization (Pareto fronts)
2. Add visualization tools for convergence analysis
3. Create benchmark suite with standard test cases
4. Implement checkpointing for long runs
5. Add support for distributed computing

**Long-term Research Directions:**
1. Transfer learning across different cities/scenarios
2. Online learning during operation
3. Multi-agent LLM collaboration
4. Integration with real-time traffic data
5. Explainability tools for LLM-generated objectives

---

## Troubleshooting Guide

**Common Issues:**

1. **Gurobi License Error:**
   - Ensure license is installed: `grbgetkey YOUR-LICENSE-KEY`
   - Check license file location: `~/gurobi.lic`

2. **API Authentication Failed:**
   - Verify `.env` file exists in `config/env/`
   - Check API token is valid and not expired
   - Ensure endpoint URL is correct

3. **Module Import Errors:**
   - Activate conda environment: `conda activate llm-guided-mod-optimization`
   - Reinstall dependencies: `conda env update -f dependencies.yml`

4. **Empty Results:**
   - Check `./discussion/` directory is created
   - Verify write permissions
   - Check console for error messages

5. **LLM Timeout:**
   - Increase timeout in API interface
   - Try smaller model or different platform
   - Check network connectivity

---

## Summary Statistics

**Project Metrics:**
- **Total Python Files:** 20+
- **Core Modules:** 9 (config, heuristics, llmAPI, model, prompt, simulator, etc.)
- **Lines of Code:** ~2000-3000 (estimated)
- **Configuration Files:** 2 (setting.cfg, .env)
- **Data Directories:** 3 (inputs, instances, resExample)
- **Dependencies:** 11 packages

**Module Complexity:**
- **High:** heuristics (evolutionary algorithm), model (MILP formulations)
- **Medium:** simulator (dynamic system), llmAPI (multi-platform support)
- **Low:** config (parsing), prompt (templates), dataCommon (structures)

---

## Key Takeaways

1. **Innovative Approach:** Combines LLM reasoning with mathematical optimization in a novel hierarchical framework

2. **Well-Structured:** Clear separation between configuration, optimization, simulation, and LLM components

3. **Extensible Design:** Factory patterns and template methods enable easy addition of new platforms and models

4. **Research-Grade:** Published at NeurIPS 2025, includes example results and reproducibility support

5. **Practical Application:** Addresses real-world mobility-on-demand optimization with hybrid AI approach

6. **Configuration-Driven:** All parameters externalized for easy experimentation

7. **Multi-Solver Support:** Both commercial (Gurobi) and open-source (OR-Tools) options

---

## References

- **Paper:** [Hierarchical Optimization via LLM-Guided Objective Evolution for Mobility-on-Demand Systems](https://arxiv.org/pdf/2510.10644)
- **Conference:** NeurIPS 2025
- **Repository:** https://github.com/yizhangele/llm-guided-mod-optimization
- **License:** MIT (with Gurobi requiring separate license)

---

**Report Generated:** 2026-03-08
**Analysis Scope:** Complete project structure, architecture, and implementation details

