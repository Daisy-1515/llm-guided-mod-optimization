<div align=center>
<h1 align="center">
Hierarchical Optimization via LLM-Guided Objective Evolution for Mobility-on-Demand Systems
</h1>
<h3 align="center">
LLM + Mathematical Optimization
</h3>
</div>

### [Paper Link](https://arxiv.org/pdf/2510.10644) 
<!---
| [Project Page](https://github.com/yizhangele/llm-guided-mod-optimization) 
-->
<!---
![Unbalanced World](./image/unbalancedWorld.png)
-->
<!---
## Introduction
-->
## Method Overview
<p align="center">
    <img src="./image/unbalancedWorld.png" alt="Alt Text" style="width:80%; height:auto;">
</p>

<p align="justify">
Mobility-on-demand platforms, such as ride-hailing services, have become critical urban transportation infrastructures. They address unbalanced demand and supply by continuously executing decision-making processes.
</p>

<p align="center">
    <img src="./image/workFlow.png" alt="Alt Text" style="width:80%; height:auto;">
</p>

<p align="justify">
Our proposed method <strong>integrates large language model (LLM) with mathematical optimization</strong> in a dynamic hierarchical system to optimize mobility operations. The hybrid LLM-optimizer framework decomposes the problem hierarchically, strategically embedding LLM only where human expertise bottlenecks exist:
</p>

- <strong>LLM as Meta-Objective Designer</strong>: Dynamically evolves strategic objectives via prompt-based harmony search, guided by feasibility feedback from the optimization solver.
- <strong>Optimizer as Constraint Enforcer</strong>: Solves operational routing layer with mathematical rigor, ensuring real-time feasibility.
- <strong>Heuristics as Prompt Evolver</strong>: Leverages harmony search algorithm to iteratively refine LLM prompts, guided by optimizer feedback to adaptively explore and
converge toward effective meta-objectives


<p align="justify">
This hybrid approach <strong>combines the semantic richness of LLM with the structural robustness of traditional optimization</strong>, delivering solutions that outperform state-of-the-art baselines.
</p>

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
You can also manually install the dependencies.

**Note:** This code depends on Gurobi (`gurobipy`), which requires a license.
- Academic users can request **free academic licenses** from Gurobi: [Gurobi Academic License](https://www.gurobi.com/academia/academic-program-and-licenses/)
- Commercial users need paid licenses.

### 3. Update Configuration Files
1. Update `config/env/.env` with the API access token for your chosen LLM hosting provider.
2. Depending on your chosen LLM model and hosting provider, you may need to implement your own code to formulate API requests and parse heuristics from API responses.
3. Update all other configurations in `config/setting.cfg`.

## Usage

### Running A Test
```bash
python testAll.py
```

## License

This project is licensed under the terms of the MIT license. See LICENSE.txt for details. 

**Note:** Some dependencies, such as Gurobi, require separate licenses. Academic users can request free licenses for research purposes. Commercial users need paid licenses.

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
