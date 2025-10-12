<div align=center>
<h1 align="center">
LLM-Guided-MoD-Optimization
</h1>
<h3 align="center">
Hierarchical Optimization via LLM-Guided Objective Evolution for Mobility-on-Demand Systems
</h3>

### [Paper](https://neurips.cc/virtual/2025/poster/117702) | [Project Page](https://github.com/yizhangele/llm-guided-mod-optimization) 

![Unbalanced World](./image/unbalancedWorld.png)

## Introduction

<img src="./image/workFlow.png" alt="framework" width="500" height="auto" div align=center>

## Installation

### 1. Clone the Repo
```bash
git clone https://github.com/yizhangele/llm-guided-mod-optimization.git
cd llm-guided-mod-optimization
```

### 2. Create a Conda Virtual Environment with Required Dependencies
```bash
conda env create -f dependencies.yml
conda activate llm-guided-mod-optimization
```
Or manually install the dependencies.

**Note:** This code depends on Gurobi (`gurobipy`), which requires a license.  
- Academic users can obtain a **free academic license** from Gurobi: [Gurobi Academic License](https://www.gurobi.com/academia/academic-program-and-licenses/)  
- Commercial use requires a paid license.

### 3. Configuration
1. Update `config/env/.env` with the key for your LLM API provider.
2. Update `config/setting.cfg` as needed.
3. If using a non-HuggingFace provider, implement the logic to interact with that provider.

## Usage

### Running Tests
```bash
python testAll.py
```

## License

This project is licensed under the terms of the MIT license. See LICENSE.txt for details. 

**Note:** Some dependencies, such as Gurobi, require separate licenses. Academic users can obtain a free license for research purposes; commercial use requires a paid license.

## Citation

If you use this code in your research, please cite:

```
@inproceedings{llm-guided-mod-optimization,
    title={Hierarchical Optimization via LLM-Guided Objective Evolution for Mobility-on-Demand Systems},
    author={Yi Zhang, Yushen Long, Yun Ni, Liping Huang, Xiaohong Wang, Jun Liu},
    booktitle={Conference on Neural Information Processing Systems (NeurIPS)},
    year={2025}
}
```
