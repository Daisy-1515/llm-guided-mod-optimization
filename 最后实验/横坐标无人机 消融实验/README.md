# 无人机数量消融实验目录说明

本目录统一收拢 `numTasks = 20`、`seed = 42` 条件下的无人机数量消融结果。

## 当前覆盖口径

- `本地执行`：全任务强制本地执行的固定基线，当前口径为 `B_up = B_down = 1e7`
- `标准目标函数`：`D1`，当前口径为 `B_up = B_down = 1e7`、`use_bcd_loop = false`
- `LLM`：`B`，当前口径为 `B_up = B_down = 1e7`、`use_bcd_loop = true`
- `LLM+HS`：`A`，沿用当前目录内既有无人机 sweep 结果

## 目录约定

- 每个 `uX/` 子目录对应固定 `numUAVs = X`
- 子目录下保留原始时间戳目录，不改动内部已有实验结果文件
- 本轮补充后，每个最新时间戳目录都包含 `B/` 与 `LOCAL/` 汇总结果

## CSV 说明

同目录下的 `横坐标无人机数量 消融实验.csv` 已扩展为四条曲线：

- `本地执行`
- `标准目标函数`
- `LLM`
- `LLM+HS`

并保留各自的 `feasible_rate_mean` 汇总列。`最佳可行方案` 的选择规则是：

1. 先比较 `feasible_rate_mean`
2. 若可行率相同，再比较 `best_cost_mean`

## 备注

- 这批 `LLM(B)` 结果的 `run_seed_42.json` 中仍记录为 `llm_status = "api_error"`，与仓库中既有 `purellm_tasksweep_seed42_bw1e7_n20` 的历史口径一致
- 因此当前补表采用的是“仓库现有 pure LLM 口径的一致延续”，不是新增的另一套评估方式
