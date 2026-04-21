# A 组 tau sweep 实验操作手册（seed=42）

更新时间：2026-04-21（最新核对）

## 1. 实验目标

本轮实验固定：

- 算法组：`A`
- 随机种子：`42`
- 横坐标：`numTasks = 5, 10, 15, ..., 50`
- 时延档位：`tau = 0.5 / 1.0 / 1.5 / 2.0`
- 输出目录：`discussion/tau_sweep_a_seed42/numTasks_XX/tau_X/...`

目标是补齐下面 40 个点位的完整结果，每个点位最终都要有：

- `manifest.json`
- `A/run_seed_42.json`
- `A/summary.json`

---

## 2. 运行前准备

在每台机器上都先执行：

```bash
uv sync
```

进入仓库根目录后，统一使用：

```bash
uv run python scripts/run_all_experiments.py
```

不要用裸 `python`。

---

## 3. 当前进度快照

### 3.1 已完成点位

这些点位**不要重复跑**：

- `numTasks=5, tau=0.5`
- `numTasks=5, tau=1.0`
- `numTasks=5, tau=1.5`
- `numTasks=5, tau=2.0`
- `numTasks=10, tau=1.5`
- `numTasks=15, tau=1.5`
- `numTasks=20, tau=1.5`
- `numTasks=25, tau=1.5`
- `numTasks=30, tau=1.5`
- `numTasks=35, tau=1.5`

### 3.2 当前无活跃进程

刚刚已检查过：`discussion/tau_sweep_a_seed42` 下当前**没有正在运行**的 `run_all_experiments.py` 进程。

因此下面列出的点位都可以重新分发到其他机器执行。

### 3.3 半成品、需要补跑的点位

这些点位目录里目前只有 `manifest.json`，还**没有** `A/run_seed_42.json`，属于半成品：

- `numTasks=10, tau=0.5`
- `numTasks=10, tau=1.0`
- `numTasks=10, tau=2.0`

### 3.4 完全没跑的点位

这些点位目前可以直接分发到其他机器执行：

- `numTasks=15, tau=0.5`
- `numTasks=15, tau=1.0`
- `numTasks=15, tau=2.0`
- `numTasks=20, tau=0.5`
- `numTasks=20, tau=1.0`
- `numTasks=20, tau=2.0`
- `numTasks=25, tau=0.5`
- `numTasks=25, tau=1.0`
- `numTasks=25, tau=2.0`
- `numTasks=30, tau=0.5`
- `numTasks=30, tau=1.0`
- `numTasks=30, tau=2.0`
- `numTasks=35, tau=0.5`
- `numTasks=35, tau=1.0`
- `numTasks=35, tau=2.0`
- `numTasks=40, tau=0.5`
- `numTasks=40, tau=1.0`
- `numTasks=40, tau=1.5`
- `numTasks=40, tau=2.0`
- `numTasks=45, tau=0.5`
- `numTasks=45, tau=1.0`
- `numTasks=45, tau=1.5`
- `numTasks=45, tau=2.0`
- `numTasks=50, tau=0.5`
- `numTasks=50, tau=1.0`
- `numTasks=50, tau=1.5`
- `numTasks=50, tau=2.0`

### 3.5 仍需补齐总数

- 半成品补跑：3 个点位
- 完全没跑：27 个点位
- 合计待完成：30 个点位

---

## 4. 推荐分机方案

考虑电脑性能不足，建议按机器拆分，而不是一台机器同时开太多任务。

### 机器 A：先补小中规模

- `numTasks=10` 的 3 个补跑点
- `numTasks=15` 的 3 个点
- `numTasks=20` 的 3 个点

共 9 个点。

### 机器 B：补中规模

- `numTasks=25` 的 3 个点
- `numTasks=30` 的 3 个点
- `numTasks=35` 的 3 个点

共 9 个点。

### 机器 C：补大规模

- `numTasks=40` 的 4 个点
- `numTasks=45` 的 4 个点
- `numTasks=50` 的 4 个点

共 12 个点。

如果机器更少，也可以按 `numTasks` 区间拆：

- 一台做 `10~20`
- 一台做 `25~35`
- 一台做 `40~50`

---

## 5. 通用命令模板

```bash
uv run python scripts/run_all_experiments.py \
  --groups A \
  --seeds 42 \
  --num-tasks <NUM_TASKS> \
  --tau <TAU> \
  --output-root "discussion/tau_sweep_a_seed42/numTasks_<NN>/tau_<TAU_LABEL>"
```

其中：

- `<NUM_TASKS>` 例如 `25`
- `<NN>` 是两位数目录名，例如 `25`、`40`
- `<TAU>` 例如 `1.5`
- `<TAU_LABEL>` 目录名写法为：
  - `0.5 -> 0p5`
  - `1.0 -> 1p0`
  - `1.5 -> 1p5`
  - `2.0 -> 2p0`

---

## 6. 可直接复制的实验命令

### 6.1 `numTasks=10`

```bash
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 10 --tau 0.5 --output-root "discussion/tau_sweep_a_seed42/numTasks_10/tau_0p5"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 10 --tau 1.0 --output-root "discussion/tau_sweep_a_seed42/numTasks_10/tau_1p0"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 10 --tau 2.0 --output-root "discussion/tau_sweep_a_seed42/numTasks_10/tau_2p0"
```

### 6.2 `numTasks=15`

```bash
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 15 --tau 0.5 --output-root "discussion/tau_sweep_a_seed42/numTasks_15/tau_0p5"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 15 --tau 1.0 --output-root "discussion/tau_sweep_a_seed42/numTasks_15/tau_1p0"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 15 --tau 2.0 --output-root "discussion/tau_sweep_a_seed42/numTasks_15/tau_2p0"
```

### 6.3 `numTasks=20`

```bash
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 20 --tau 0.5 --output-root "discussion/tau_sweep_a_seed42/numTasks_20/tau_0p5"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 20 --tau 1.0 --output-root "discussion/tau_sweep_a_seed42/numTasks_20/tau_1p0"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 20 --tau 2.0 --output-root "discussion/tau_sweep_a_seed42/numTasks_20/tau_2p0"
```

### 6.4 `numTasks=25`

```bash
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 25 --tau 0.5 --output-root "discussion/tau_sweep_a_seed42/numTasks_25/tau_0p5"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 25 --tau 1.0 --output-root "discussion/tau_sweep_a_seed42/numTasks_25/tau_1p0"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 25 --tau 2.0 --output-root "discussion/tau_sweep_a_seed42/numTasks_25/tau_2p0"
```

### 6.5 `numTasks=30`

```bash
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 30 --tau 0.5 --output-root "discussion/tau_sweep_a_seed42/numTasks_30/tau_0p5"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 30 --tau 1.0 --output-root "discussion/tau_sweep_a_seed42/numTasks_30/tau_1p0"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 30 --tau 2.0 --output-root "discussion/tau_sweep_a_seed42/numTasks_30/tau_2p0"
```

### 6.6 `numTasks=35`

```bash
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 35 --tau 0.5 --output-root "discussion/tau_sweep_a_seed42/numTasks_35/tau_0p5"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 35 --tau 1.0 --output-root "discussion/tau_sweep_a_seed42/numTasks_35/tau_1p0"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 35 --tau 2.0 --output-root "discussion/tau_sweep_a_seed42/numTasks_35/tau_2p0"
```

### 6.7 `numTasks=40`

```bash
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 40 --tau 0.5 --output-root "discussion/tau_sweep_a_seed42/numTasks_40/tau_0p5"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 40 --tau 1.0 --output-root "discussion/tau_sweep_a_seed42/numTasks_40/tau_1p0"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 40 --tau 1.5 --output-root "discussion/tau_sweep_a_seed42/numTasks_40/tau_1p5"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 40 --tau 2.0 --output-root "discussion/tau_sweep_a_seed42/numTasks_40/tau_2p0"
```

### 6.8 `numTasks=45`

```bash
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 45 --tau 0.5 --output-root "discussion/tau_sweep_a_seed42/numTasks_45/tau_0p5"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 45 --tau 1.0 --output-root "discussion/tau_sweep_a_seed42/numTasks_45/tau_1p0"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 45 --tau 1.5 --output-root "discussion/tau_sweep_a_seed42/numTasks_45/tau_1p5"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 45 --tau 2.0 --output-root "discussion/tau_sweep_a_seed42/numTasks_45/tau_2p0"
```

### 6.9 `numTasks=50`

```bash
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 50 --tau 0.5 --output-root "discussion/tau_sweep_a_seed42/numTasks_50/tau_0p5"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 50 --tau 1.0 --output-root "discussion/tau_sweep_a_seed42/numTasks_50/tau_1p0"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 50 --tau 1.5 --output-root "discussion/tau_sweep_a_seed42/numTasks_50/tau_1p5"
uv run python scripts/run_all_experiments.py --groups A --seeds 42 --num-tasks 50 --tau 2.0 --output-root "discussion/tau_sweep_a_seed42/numTasks_50/tau_2p0"
```

---

## 7. 每个实验做完后怎么验收

单个点位跑完后，至少检查：

```bash
ls "discussion/tau_sweep_a_seed42/numTasks_25/tau_0p5"
ls "discussion/tau_sweep_a_seed42/numTasks_25/tau_0p5"/*/A
```

验收标准：

1. 对应 `tau_*` 目录下出现一个新的时间戳目录
2. 该目录下有 `manifest.json`
3. 该目录下有 `A/run_seed_42.json`
4. 该目录下有 `A/summary.json`

如果只有 `manifest.json`，说明是半成品，需要后续重跑。

---

## 8. 多机执行注意事项

### 8.1 不要重复跑同一个点位

同一个 `(numTasks, tau)` 只分给一台机器。

### 8.2 输出目录必须保持一致

所有机器都按下面格式写：

```text
discussion/tau_sweep_a_seed42/numTasks_XX/tau_X/
```

不要改目录命名，不要改成 tau-first。

### 8.3 如果在其他机器单独跑

建议最终只把该点位生成的整个时间戳目录拷回主仓库，例如：

```text
discussion/tau_sweep_a_seed42/numTasks_40/tau_2p0/20260421_xxxxxx/
```

### 8.4 建议不要一台机器一次开太多

经验上建议每台机器同时跑 `2~4` 个点，避免 API、求解器和内存一起卡住。

---

## 9. 建议执行顺序

如果要优先补最有价值的点，建议顺序：

1. `numTasks=10, tau=0.5/1.0/2.0`
2. `numTasks=15, tau=0.5/1.0/2.0`
3. `numTasks=20, tau=0.5/1.0/2.0`
4. `numTasks=40~50` 全部点位

原因：

- `10/15/20` 能先把低中规模横轴补齐
- `40/45/50` 是当前完全空白的高规模区间

---

## 10. 本手册适用范围

本手册只对应这一次实验：

- `group=A`
- `seed=42`
- `tau sweep`
- 输出根目录：`discussion/tau_sweep_a_seed42`

如果以后要跑别的组、别的 seed、别的 sweep，不要直接照抄输出目录。
