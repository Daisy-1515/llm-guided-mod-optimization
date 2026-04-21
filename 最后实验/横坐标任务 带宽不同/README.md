# 任务数-带宽实验目录说明

本目录统一收拢“任务数横坐标、带宽口径不同”的实验结果。

## 当前覆盖点

- `bup_1e7/`：A 组任务数 sweep，固定 `B_up = 1e7`、`B_down = 5e7`
- `bup_5e7/`：A 组任务数 sweep，固定 `B_up = 5e7`、`B_down = 5e7`

两组目录都按 `tasks_X/时间戳/` 保存原始结果，不改动内部 `manifest.json`、`comparison_summary.json`、`A/summary.json` 等文件。

## 当前覆盖情况

- `bup_1e7`：已有 `tasks=5/10/15/20/25/30/35/40/45/50` 的完整结果
- `bup_5e7`：已有 `tasks=5/10/15/20/25/30/35/40/45/50` 的完整结果

## 目录约定

- 每个 `bup_xxx/tasks_X/` 子目录对应固定任务数与带宽口径
- 子目录下保留原始时间戳目录，不改动内部结果文件
- 只有 `manifest.json`、缺 `A/summary.json` / `A/run_seed_42.json` 的目录视为无效残留，不能用于汇总

## 汇总口径

- 同目录下的 `横坐标任务-带宽对比实验.csv` 汇总了 all-local、D1、pure LLM(B) 与两组 A 组结果
- `最佳可行方案` 的选择规则是：先比较 `feasible_rate_mean`，再比较 `best_cost_mean`
- 如果只想看 A 组不同带宽口径的对比，可重点关注 `A(bup=1e7,bdown=5e7)`、`A(bup=5e7,bdown=5e7)` 及对应 feasible 列

## 当前备注

- `bup_1e7/tasks_25/20260421_232820/` 已补齐完整结果，可用于后续汇总
- `bup_1e+07/` 旧无效残留目录已清理
