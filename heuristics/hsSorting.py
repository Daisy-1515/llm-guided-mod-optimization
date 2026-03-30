"""
* 文件: hsSorting.py
* 作者: Yi
*
* 创建日期: 2025/01/27
"""
"""
@package hsSorting.py
@brief 此模块处理每个种群中个体的排序。
"""

import numpy as np
import json
from collections import defaultdict

class hsSorting:
    def sort_population(self, population, popsize):
        """
        基于 'evaluation_score' 对种群进行升序排序。

        参数:
            population (list): 个体解的列表（字典形式）。
            popsize (int): 排序后保留的个体数量。

        返回:
            list: 长度为 popsize 的已排序种群。
        """
        # 按 'evaluation_score' 排序种群
        sorted_population = sorted(population, key=lambda ind: ind['evaluation_score'])

        # 返回前 'popsize' 个个体
        return sorted_population[:popsize]
    
class hsDiversitySorting:
    """
    带有多样性考虑的种群排序。
    """
    def __init__(self, similarity_threshold=0.8):
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            raise RuntimeError(
                "hsDiversitySorting 需要 sentence-transformers 和运行正常的 torch 环境。"
            ) from exc
        self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        self.similarity_threshold = similarity_threshold
        
    def compute_similarity(self, emb_i, emb_j):
        """计算余弦相似度。"""
        return np.dot(emb_i, emb_j) / (np.linalg.norm(emb_i) * np.linalg.norm(emb_j))

    def sort_population(self, population, popsize):
        # 首先按 'evaluation_score' 排序
        sorted_population = sorted(population, key=lambda ind: ind['evaluation_score'])
        selected_population = []
        non_selected_population = []
        embeddings = {}
        
        # 按评估得分对个体进行分组
        grouped_population = defaultdict(list)
        for ind in sorted_population:
            grouped_population[ind['evaluation_score']].append(ind)
        
        for score in sorted(grouped_population.keys()):
            layer_selected = []
            group_input = {}
            for ind in grouped_population[score]:
                obj_code = ""
                for key in ind['simulation_steps'].keys():
                    if ind['simulation_steps'][key]['response_format'] != "Response format does not meet the requirements":
                        print('B')
                        llm_response_dict = json.loads(ind['simulation_steps'][key]['llm_response'])
                        obj_code += llm_response_dict['obj_code']
                
                # 为目标函数代码计算嵌入 (embedding)
                embedding = self.model.encode(obj_code, convert_to_numpy=True)
                embeddings[obj_code] = embedding
                
                # 检查同一评估得分层内的相似度
                if all(self.compute_similarity(embedding, embeddings[sel['obj_code']]) < self.similarity_threshold for sel in group_input):
                    group_input['obj_code'] = obj_code  # 记录 obj_code 以供后续参考
                    layer_selected.append(ind)
                else:
                    non_selected_population.append(ind)
                
                # 如果已选个体达到 popsize，则直接返回
                if len(selected_population) + len(layer_selected) >= popsize:
                    selected_population.extend(layer_selected[:popsize - len(selected_population)])
                    return selected_population
            
            selected_population.extend(layer_selected)
        
        # 如果插槽未满，从非优选集中按 evaluation_score 填充
        for ind in non_selected_population:
            if len(selected_population) < popsize:
                selected_population.append(ind)
            else:
                break
        
        return selected_population
