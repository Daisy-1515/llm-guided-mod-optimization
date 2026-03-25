# Phase⑤ 首跑 LLM 调用问题诊断报告

> **日期**：2026-03-20
> **阶段**：Phase⑤ 完整 pipeline 首次试跑 (C→F)
> **运行参数**：popSize=3, iteration=3, model=glm-5, 代理服务=CloseAI (api.openai-proxy.org)
> **环境**：Windows 11 Pro, Python 3.x, Gurobi 13.0.1, Intel i5-14600K

---

## 1. 概述

Phase⑤ 首次试跑于 2026-03-20 执行完成。3×3 正式首跑（run_id: `20260320_132706`）进程正常退出（exit 0），Gurobi 求解器全部可行，但 LLM 调用全部失败（9/9 个体均 `llm_status=api_error`），所有个体回退至默认目标函数。

**S1-S4 成功判据结果**：

| 判据 | 内容 | 结果 |
|------|------|------|
| S1 | JSON 文件数 = 预期代数 (3) | **PASS** |
| S2 | 末代 ≥1 个体使用 LLM 自定义目标函数 | **FAIL** (custom_obj=0) |
| S3 | 末代 ≥1 个体 feasible=true | **PASS** (feasible=3) |
| S4 | 记录基线 evaluation_score | **PASS** (baseline=31.7735) |

**结论**：代码路径完整正确，瓶颈在 LLM 外部调用链路。

---

## 2. 现象描述

### 2.1 短 prompt 正常

`check_llm_api.py` 发送极短 prompt "Say OK"，三次测试均成功：

```
# D1 初次测试
platform=HuggingFace  model=glm-5  endpoint=api.openai-proxy.org  n_trial=3
elapsed_sec=6.78  response_preview=OK  status=SUCCESS

# D2 验证（timeout 调整后）
elapsed_sec=8.61  response_preview=OK  status=SUCCESS

# 诊断阶段对比测试
WITH system proxy:    Status=200, elapsed=11.49s
WITHOUT proxy:        Status=200, elapsed=9.84s
```

**观察**：短 prompt 响应时间 6-11 秒，均正常返回。

### 2.2 长 prompt 持续失败

Edge UAV 完整 prompt 规模：**21,018 chars / ~5,254 tokens**。

```
=== Test: Edge UAV prompt WITH system proxy ===
  FAILED after 120.31s: Read timed out. (read timeout=120)

=== Test: Edge UAV prompt WITHOUT proxy ===
  FAILED after 123.34s: ProxyError('Unable to connect to proxy',
    RemoteDisconnected('Remote end closed connection without response'))
```

### 2.3 两种错误交替出现

在正式首跑和各次预飞中，以下两类错误交替出现：

**错误类型 A — ProxyError**：
```
HTTPSConnectionPool(host='api.openai-proxy.org', port=443): Max retries exceeded
with url: /v1/chat/completions
(Caused by ProxyError('Unable to connect to proxy',
  RemoteDisconnected('Remote end closed connection without response')))
```

**错误类型 B — Read timeout**（timeout=60s 时）：
```
HTTPSConnectionPool(host='api.openai-proxy.org', port=443):
Read timed out. (read timeout=60)
```

**错误类型 B — Read timeout**（timeout=120s 时）：
```
HTTPSConnectionPool(host='api.openai-proxy.org', port=443):
Read timed out. (read timeout=120)
```

在同一次运行中，两种错误可混合出现：
```
Trial 1/3: ProxyError('Unable to connect to proxy', ...)
Trial 2/3: Read timed out. (read timeout=120)
Trial 3/3: ProxyError('Unable to connect to proxy', ...)
```

### 2.4 D3 验证中有 1 次 LLM 成功返回

在 D3 验证运行（`20260320_130919`，2×2 配置）的 Gen 1 中，有 1 个个体成功获得 LLM 返回的自定义目标函数。该函数被 Gurobi 成功执行，产生了不同于默认目标的求解结果（OBJ COST=34.2830 vs 默认 31.7735）。详见第 5 节。

---

## 3. 调用链路分析

### 3.1 完整链路图

```
Python requests.post()
    │
    ▼
本地代理 127.0.0.1:7897 (Clash)      ← Windows 注册表自动拾取
    │
    ▼
CloseAI (api.openai-proxy.org)        ← 代理转发服务
    │
    ▼
glm-5 (智谱 GLM-5 推理模型)           ← 最终推理层
```

### 3.2 Windows 代理自动拾取机制

Python `requests` 库在 Windows 上自动读取注册表代理设置：

```
=== Python requests proxy detection ===
Session proxies: {}
Env HTTPS_PROXY: <not set>
Env HTTP_PROXY: <not set>
Env https_proxy: <not set>
Env http_proxy: <not set>
Env ALL_PROXY: <not set>
Env NO_PROXY: <not set>
Windows ProxyEnable: 1
Windows ProxyServer: 127.0.0.1:7897
```

**关键发现**：虽然所有环境变量代理均未设置，且 `Session proxies` 为空字典，但 Windows 注册表中 `ProxyEnable=1`、`ProxyServer=127.0.0.1:7897`。Python `requests` 底层通过 `urllib3` → `trustenv=True` 路径自动拾取此代理。

即便显式设置 `proxies={}`，请求仍可能经过本地代理，因为 `proxies={}` 在 Windows 上不等价于 "不使用代理"。

### 3.3 对比实验

| 组合 | 短 prompt ("Say OK") | 长 prompt (~5K tokens) |
|------|---------------------|----------------------|
| WITH 系统代理 | 200 OK, 11.49s | FAIL, 120.31s Read timeout |
| WITHOUT 代理 (`proxies={}`) | 200 OK, 9.84s | FAIL, 123.34s ProxyError |

**结论**：
- 短 prompt 无论有无代理均可通过
- 长 prompt 无论有无代理均失败
- `proxies={}` 并未真正绕开 Windows 注册表代理（仍出现 ProxyError）

---

## 4. 三层根因

### 根因 A：glm-5 推理模型对长 prompt 响应慢

glm-5 是智谱的推理模型，处理请求时先执行 `reasoning_content`（思维链推理），再生成最终响应。对于 ~5K token 的复杂数学优化 prompt，模型需要：
1. 解析完整的 Edge UAV 计算卸载场景描述
2. 执行长链推理（reasoning_content 可能数千 tokens）
3. 生成符合格式要求的目标函数代码

短 prompt "Say OK" 推理极短（~10s 可返回），但 Edge UAV prompt 的推理+生成可能需要 2-5 分钟，远超 120s timeout。

**佐证**：D3 中唯一成功的 LLM 返回发生在 Gen 1（非 Gen 0），推测是因为该请求恰好在代理稳定窗口内完成了推理。

### 根因 B：本地代理 (Clash 7897) 对长连接不稳定

Clash 代理在短连接场景下表现稳定，但对长时间保持的 HTTPS 连接（>60s）存在断开风险：
- 代理可能对 idle connection 执行超时清理
- SSL/TLS 长连接在代理层面可能被中间设备重置

**佐证**：ProxyError 的具体消息 `RemoteDisconnected('Remote end closed connection without response')` 指向代理层面的连接中断，而非目标服务器拒绝。

### 根因 C：`requests proxies={}` 在 Windows 上未完全绕开代理

在 Linux 上，`requests.post(..., proxies={})` 可有效绕开系统代理。但在 Windows 上，由于注册表代理拾取机制的优先级问题，空字典不一定能覆盖 `ProxyEnable=1` 的设定。

**佐证**：诊断测试中 `proxies={}` 的长 prompt 请求仍产生 ProxyError。

---

## 5. 代码路径验证

### 5.1 D3 成功返回的 obj_code

在 D3 运行（`20260320_130919`）Gen 1 中，glm-5 成功返回了一个包含 4 个 cost 项的自定义目标函数：

```python
def dynamic_obj_func(self):
    print("Creating dynamic objectives for Offloading Model")
    # Cost 1: Normalized local execution delay
    cost1 = gb.quicksum(
        self.alpha * self.D_hat_local[i][t] / self.task[i].tau
        * self.x_local[i, t]
        for i in self.taskList for t in self.timeList
        if self.task[i].active[t] and (i, t) in self.x_local
    )
    # Cost 2: Normalized offloading delay
    cost2 = gb.quicksum(
        self.alpha * self.D_hat_offload[i][j][t] / self.task[i].tau
        * self.x_offload[i, j, t]
        for i in self.taskList for j in self.uavList
        for t in self.timeList
        if self.task[i].active[t] and (i, j, t) in self.x_offload
    )
    # Cost 3: Normalized edge computing energy
    cost3 = gb.quicksum(
        self.gamma_w * self.E_hat_comp[j][i][t] / self.uav[j].E_max
        * self.x_offload[i, j, t]
        for i in self.taskList for j in self.uavList
        for t in self.timeList
        if self.task[i].active[t] and (i, j, t) in self.x_offload
    )
    # Cost 4: Urgency penalty - higher weight for tasks closer to deadline
    cost4 = gb.quicksum(
        (self.D_hat_offload[i][j][t] / self.task[i].tau) ** 2
        * self.x_offload[i, j, t]
        for i in self.taskList for j in self.uavList
        for t in self.timeList
        if self.task[i].active[t] and (i, j, t) in self.x_offload
    )
    costs = [cost1 + cost2, cost3, cost4]
    weights = [1.0, 1.2, 0.15]
    objective = gb.quicksum(w * c for w, c in zip(costs, weights))
    self.model.setObjective(objective, gb.GRB.MINIMIZE)
```

**LLM 的设计理由**（obj_description）：
> Enhanced objective with urgency-aware penalty: combines normalized delay (alpha-weighted), normalized energy (gamma_w-weighted), and a deadline-proximity urgency term that penalizes tasks with delay ratios closer to their deadline, encouraging better distribution of urgent tasks to faster execution modes.

### 5.2 Gurobi 成功执行

该自定义目标函数被 Gurobi 成功接受并求解：

```
Creating dynamic objectives for Offloading Model
*****************OBJ COST: 34.2830************
```

vs 默认目标函数：

```
*****************OBJ COST: 31.7735************
```

cost 差异说明自定义目标函数引入了额外的 urgency penalty 项（cost4），导致总 cost 略高，符合预期。

### 5.3 验证结论

这一成功案例完整证明了：
1. **Prompt 生成**：Edge UAV prompt 可被 glm-5 正确理解
2. **JSON 解析**：LLM 返回的 obj_code 可被正确提取
3. **动态注入**：`dynamic_obj_func` 可被正确注入到 OffloadingModel
4. **Gurobi 求解**：自定义目标函数语法正确，Gurobi 可正常求解
5. **评分记录**：evaluation_score 正确记录

**瓶颈仅在 LLM 外部调用链路的稳定性/速度，代码路径本身完整正确。**

---

## 6. 可用模型清单

CloseAI 代理服务支持的模型列表（`/v1/models` 接口返回，按类型分组）：

### 智谱
- `glm-5`（当前使用，推理模型）

### OpenAI GPT 系列
- `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`
- `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`
- `gpt-5`, `gpt-5-mini`, `gpt-5-nano`, `gpt-5-pro`
- `gpt-5.1` ~ `gpt-5.4` 各变体

### Anthropic Claude 系列
- `claude-opus-4-5`, `claude-opus-4-6`
- `claude-sonnet-4-5`, `claude-sonnet-4-6`
- `claude-haiku-4-5`

### DeepSeek
- `deepseek-chat`, `deepseek-reasoner`, `deepseek-v3.2`

### 阿里通义
- `qwen3.5-flash`, `qwen3.5-plus`

### 推荐替代模型

| 模型 | 推理类型 | 推荐理由 |
|------|---------|---------|
| `gpt-4o` | 非推理 | 快速、稳定，适合代码生成 |
| `gpt-4o-mini` | 非推理 | 更快更便宜，适合测试 |
| `deepseek-chat` | 非推理 | 快速，代码能力强 |
| `gpt-4.1` | 非推理 | 最新 GPT 系列，能力强 |
| `qwen3.5-plus` | 非推理 | 通义系列，中文能力好 |

---

## 7. 修复方案

### 方案 A：换快速非推理模型（推荐）

将 `config/setting.cfg` 中的 `model` 从 `glm-5` 改为非推理模型（如 `gpt-4o`、`deepseek-chat`）。

**优点**：响应速度快（预计 10-30s），无 reasoning_content 开销，可立即验证
**缺点**：可能影响目标函数设计质量（但可通过 prompt 工程弥补）

### 方案 B：增大 timeout

将 `llmInterface_huggingface.py` 的 `request_timeout` 从 120s 增大至 300-600s，同步调整 `hsPopulation.timeout`。

**优点**：不换模型，保持推理质量
**缺点**：每个个体等待时间极长（3×300s = 15min/个体），3×3 运行可能需要数小时；代理长连接不稳定问题仍存在

### 方案 C：绕开本地代理

在调用 `requests.post` 前显式设置 `os.environ["NO_PROXY"] = "*"` 或 `os.environ["HTTPS_PROXY"] = ""`，确保不经过 Clash 代理。

**优点**：消除代理层面的连接中断
**缺点**：仅解决根因 B，不解决根因 A（glm-5 本身慢）

### 方案 D：组合方案（推荐最终方案）

1. 换非推理模型（方案 A）— 解决根因 A
2. 绕开本地代理（方案 C）— 解决根因 B 和 C
3. 保持 timeout=120s — 足够非推理模型使用

**预期效果**：每次 LLM 调用 10-30s，3×3 运行总时间从"不可能完成"降至 ~10-15 分钟。

---

## 8. 首跑数据存档

### 8.1 全部运行记录

| # | Run ID | 配置 | 阶段 | 结果 |
|---|--------|------|------|------|
| 1 | `20260320_124738` | 1×1 | D2 首次 | Exit 0. LLM 3× Read timeout (60s), 回退默认 obj. OBJ=31.7735 |
| 2 | `20260320_125415` | 1×1 | D2 二次 | Exit 1. 混合 ProxyError + Read timeout (120s). **Executor TimeoutError**：120s×3 retries + 2s×2 sleep = ~366s > executor timeout 300s |
| 3 | `20260320_130134` | 1×1 | D2 三次 | Exit 0. LLM 3× 失败 (ProxyError + Read timeout). 回退默认 obj. OBJ=31.7735 |
| 4 | `20260320_130919` | 2×2 | D3 验证 | Exit 0. Gen 0: 0/2 ok. Gen 1: **1 个体 LLM 成功**（OBJ=34.2830）, 1 个体失败. |
| 5 | `20260320_132706` | 3×3 | E 正式首跑 | Exit 0. 9/9 LLM 失败 (全部 ProxyError). 全部回退默认 obj. OBJ=31.7735 |

### 8.2 3×3 正式首跑 analyze_results.py 输出

```
run_dir=discussion\20260320_132706  json_files=3
========================================================================
Gen  0: n=3/3  ok=0  custom_obj=0  feasible=3  best=31.7735
Gen  1: n=3/3  ok=0  custom_obj=0  feasible=3  best=31.7735
Gen  2: n=3/3  ok=0  custom_obj=0  feasible=3  best=31.7735
========================================================================
S1 PASS: json_files=3 expected=3
S2 FAIL: final gen 2 custom_obj_ok=0
S3 PASS: final gen 2 feasible=3
S4 PASS: baseline best_evaluation_score=31.7735
```

### 8.3 关键超时参数

| 参数 | 值 | 位置 |
|------|-----|------|
| `request_timeout` | 120s（原 60s） | `llmAPI/llmInterface_huggingface.py:34` |
| `n_trial` (LLM 重试次数) | 3 | `config/config.py` |
| 重试间隔 | 2s | `llmAPI/llmInterface_huggingface.py` (`time.sleep(2)`) |
| `hsPopulation.timeout` | 600s（运行时设置） | `testEdgeUav.py:44` |
| Gurobi `TimeLimit` | 10s | `config/config.py` |
| Gurobi `MIPGap` | 0.05 | `config/config.py` |

**超时链路计算**：单个个体最坏 LLM 等待时间 = 120s × 3 + 2s × 2 = **364s**。
Run #2 崩溃原因：executor timeout (300s) < 单个体最坏等待时间 (364s)。修复后设为 600s。

---

## 9. 代码变更记录

Phase⑤ C→F 涉及的文件改动：

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `testEdgeUav.py` | 修改 | +环境变量覆盖 (`HS_POP_SIZE`, `HS_ITERATION`), +executor timeout 600s, +启动前诊断日志, +tau/f_local 放宽 |
| `llmAPI/llmInterface_huggingface.py` | 修改 | `request_timeout` 从 60 改为 120 |
| `check_llm_api.py` | 新增 | API 连通性检查脚本 (~64 行), 走真实生产路径验证端到端连通 |
| `analyze_results.py` | 新增 | 结果分析 + S1-S4 判据检测脚本 (~173 行) |

**Phase⑤-B 已提交的改动**（commit `c1a52bb`）：

| 文件 | 变更说明 |
|------|---------|
| `heuristics/hsFrame.py` | run_id 归档至 `discussion/{YYYYMMDD_HHMMSS}/` + 运行结束摘要 |
| `heuristics/hsPopulation.py` | 删除星号噪声日志 |
| `tests/test_edge_uav_hs_integration.py` | 测试路径断言同步更新 |

---

## 附录：数据文件索引

| 路径 | 内容 |
|------|------|
| `discussion/20260320_132706/` | 3×3 正式首跑结果 (3 JSON) |
| `discussion/20260320_130919/` | D3 2×2 验证结果 (2 JSON, 含 1 次 LLM 成功) |
| `discussion/20260320_130134/` | D2 第三次 1×1 预飞 |
| `discussion/20260320_125415/` | D2 第二次 1×1 预飞 (executor crash) |
| `discussion/20260320_124738/` | D2 第一次 1×1 预飞 |
| `logs/run_3x3_20260320_132702.log` | 3×3 正式首跑完整日志 (398 行) |
| `check_llm_api.py` | API 连通性检查脚本 |
| `analyze_results.py` | 结果分析脚本 |
