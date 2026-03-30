# Edge-UAV Joint Optimization

This repository is currently maintained as an Edge-UAV joint optimization workspace.
The active workflow combines:

1. `LLM` for objective proposal or prompt evolution
2. `Harmony Search` for population-based search
3. `Mathematical optimization` for feasible offloading, resource allocation, and trajectory decisions

The main path in daily use is the Edge-UAV pipeline under `scripts/`, `edge_uav/`,
`heuristics/`, and `tests/`.

Current project status is tracked in [CLAUDE.md](./CLAUDE.md).
Detailed design and audit material is indexed in [文档/INDEX.md](./文档/INDEX.md).

## Quick Start

### Requirements

- Python 3.11-3.12
- `uv`
- `gurobipy` with a valid Gurobi license
- An LLM API endpoint if you want to run the LLM-guided path

### Environment

```bash
uv sync
```

Create `config/env/.env`:

```env
HUGGINGFACE_ENDPOINT="https://your-endpoint/v1"
HUGGINGFACEHUB_API_TOKEN="sk-your-api-key"
```

Update `config/setting.cfg` if needed:

```ini
[llmSettings]
platform = HuggingFace
model = qwen3.5-plus
```

### Common Commands

```bash
uv run python scripts/run_edge_uav.py
HS_POP_SIZE=3 HS_ITERATION=5 uv run python scripts/run_edge_uav.py
uv run pytest tests -v
uv run python scripts/run_all_experiments.py --help
uv run python scripts/check_llm_api.py
```

- `scripts/run_edge_uav.py`: main Edge-UAV entrypoint
- `scripts/run_all_experiments.py`: batch experiment runner
- `scripts/check_llm_api.py`: connectivity check for the configured LLM endpoint
- `pytest tests -v`: unit and integration tests

## Repository Map

- `scripts/`: runnable entrypoints and experiment helpers
- `edge_uav/`: scenario data, prompts, and optimization blocks
- `heuristics/`: Harmony Search framework and individual execution bridge
- `config/`: runtime configuration and parameter loading
- `tests/`: unit and integration tests for the active Edge-UAV workflow
- `llmAPI/`: model interface layer

## Runtime Flow

1. `scripts/run_edge_uav.py` loads configuration and builds an `EdgeUavScenario`.
2. `HarmonySearchSolver` manages the outer search loop.
3. `hsIndividualEdgeUav` bridges the LLM or default objective into the solver stack.
4. `offloading.py`, `resource_alloc.py`, `trajectory_opt.py`, and `bcd_loop.py` solve the main optimization blocks.
5. `evaluator.py` computes the fixed `evaluation_score` used to compare solutions.

## More Context

- [CLAUDE.md](./CLAUDE.md): current project status, recent experiment conclusions, and next-step notes
- [文档/INDEX.md](./文档/INDEX.md): full documentation index
- `discussion/`: single-run and batch experiment outputs
- `scripts/diagnose_edge_uav_bcd.py`: narrow diagnostic runner for offloading feasibility and BCD impact

## Legacy Note

Historical MoD code is still present under `legacy_mod/`, `model/`, `prompt/`,
`simulator/`, and `scripts/run_all.py`, but it is not the default development path.

## License

This repository does not currently include a checked-in `LICENSE` file.
Do not treat the repository as having an explicit license grant until that file exists.
