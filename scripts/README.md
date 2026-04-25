# Scripts 启动说明

本说明面向 `scripts/` 目录下的可执行脚本，目标是让你快速跑通：
- 单次 Edge-UAV 求解
- 批量实验对比（A/B/C1/C2/D1/D2）
- 结果分析与可视化
- 常见诊断

## 1. 环境准备

在项目根目录执行：

```powershell
uv sync
```

可选：先检查 LLM 连接是否正常

```powershell
uv run python scripts/check_llm_api.py
```

如果失败，先检查：
- `config/setting.cfg` 的 `llmSettings`
- `config/env/.env` 中 API Key / endpoint

## 2. 快速开始

### 2.1 单次运行（Edge-UAV + HS）

```powershell
uv run python scripts/run_edge_uav.py
```

临时覆盖种群大小/迭代数（PowerShell）：

```powershell
$env:HS_POP_SIZE="1"; $env:HS_ITERATION="1"; uv run python scripts/run_edge_uav.py
```

### 2.2 批量实验（推荐入口）

```powershell
uv run python scripts/run_all_experiments.py --groups A D1 --seeds 42 43 44
```

仅查看计划，不执行：

```powershell
uv run python scripts/run_all_experiments.py --groups A D1 --seeds 42 --dry-run
```

关闭 BCD（默认是开启）：

```powershell
uv run python scripts/run_all_experiments.py --groups A D1 --seeds 42 --no-bcd-loop
```

## 3. 常用脚本索引

### 核心执行

- `run_edge_uav.py`
  - 用途：单次 Edge-UAV + HS 运行（最短路径）
  - 命令：`uv run python scripts/run_edge_uav.py`

- `run_all_experiments.py`
  - 用途：A/B/C1/C2/D1/D2 组批量实验
  - 常用参数：
    - `--groups A B C1 C2 D1 D2`
    - `--seeds 42 43 44`
    - `--hs-pop-size 5`
    - `--hs-iterations 10`
    - `--no-bcd-loop`
    - `--manual-alpha` + `--manual-gamma`（D2 必填）
    - `--output-root discussion/experiment_results`

### 分析与可视化

- `analyze_results.py`
  - 用途：分析 `discussion/` 中 `population_result_*.json` 或实验目录 `run_seed_*.json`
  - 命令：
    - `uv run python scripts/analyze_results.py --run-dir discussion/<run_dir>`
    - `uv run python scripts/analyze_results.py --experiment-dir discussion/experiment_results/<exp_dir>`

- `plot_optimization_curves.py`
  - 用途：画收敛曲线 + 分布图（PNG + HTML）
  - 命令：
    - `uv run python scripts/plot_optimization_curves.py`
    - `uv run python scripts/plot_optimization_curves.py --exp-dir discussion/experiment_results/<exp_dir>`
    - `uv run python scripts/plot_optimization_curves.py --output-dir discussion/plots_custom`

- `plot_trajectory.py`
  - 用途：从 `population_result_*.json` 画 UAV 轨迹/分配图（依赖 BCD 快照）
  - 命令：
    - `uv run python scripts/plot_trajectory.py --run-dir discussion/<run_dir> --gen 1`
    - `uv run python scripts/plot_trajectory.py --run-dir discussion/<run_dir> --gen 1 --mode both --save traj.png --no-show`

- `plot_d1_trajectory.py`
  - 用途：从 D1 实验结果（`run_seed_*.json`）画轨迹
  - 命令：
    - `uv run python scripts/plot_d1_trajectory.py --seed 42`
    - `uv run python scripts/plot_d1_trajectory.py --result-file discussion/experiment_results/<exp>/D1/run_seed_42.json --mode trajectory`

### 诊断与维护

- `check_llm_api.py`
  - 用途：检查 LLM 端到端连通性
  - 命令：`uv run python scripts/check_llm_api.py`

- `docx_to_md.py`
  - 用途：将 Word `.docx` 文档稳定转换为 Markdown（依赖本机 `pandoc`）
  - 命令：
    - `uv run python scripts/docx_to_md.py --input path/to/file.docx`
    - `uv run python scripts/docx_to_md.py --input path/to/file.docx --output path/to/file.md`

- `diagnose_edge_uav_bcd.py`
  - 用途：批量诊断场景可行性与 BCD 改善
  - 命令：`uv run python scripts/diagnose_edge_uav_bcd.py --seeds 42`

- `update_project_claude.py`
  - 用途：维护项目级 `CLAUDE.md`
  - 命令：
    - `uv run python scripts/update_project_claude.py`
    - `uv run python scripts/update_project_claude.py --dry-run`

## 4. 遗留/谨慎使用

- `run_all.py`
  - 旧版 MoD 入口（`legacy_mod` 路径），不是当前 Edge-UAV 主流程。

- `diagnose_offload_feasibility.py`
  - 历史诊断草稿脚本，包含过时导入路径（如 `edge_uav.model.scenario`），不建议作为当前主诊断入口。
  - 优先使用 `diagnose_edge_uav_bcd.py`。

## 5. 输出目录约定

- `run_edge_uav.py`：通常输出到 `discussion/<timestamp>/...`
- `run_all_experiments.py`：输出到 `discussion/experiment_results/<timestamp>/...`
- `plot_optimization_curves.py`：输出到 `discussion/plots/...`

## 6. 常见报错

- `D2 requires both --manual-alpha and --manual-gamma`
  - 说明：你选择了 D2 但没给手调参数。

- `LLM 配置缺失`
  - 先执行 `uv run python scripts/check_llm_api.py`，再补 `setting.cfg` / `.env`。

- `no optimal_snapshot.q found`
  - 轨迹图脚本需要 BCD 快照；请确认实验是 BCD 路径并且结果里有 `bcd_meta.optimal_snapshot`。
