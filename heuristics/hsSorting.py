"""
* File: hsSorting.py
* Author: Yi
*
* created on 2025/01/27
"""
"""
@package hsSorting.py
@brief This module handles the sorting of individuals in each population.
"""

import numpy as np
import json
from collections import defaultdict

class hsSorting:
    def sort_population(self, population, popsize):
        """
        Sorts the population based on the 'evaluation_score' in ascending order.

        Args:
            population (list): List of individual solutions (dictionaries).
            popsize (int): Number of individuals to retain after sorting.

        Returns:
            list: Sorted population of length popsize.
        """
        # Sort population by 'evaluation_score'
        sorted_population = sorted(population, key=lambda ind: ind['evaluation_score'])

        # Return the top 'popsize' individuals
        return sorted_population[:popsize]
    
class hsDiversitySorting:
    def __init__(self, similarity_threshold=0.8):
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            raise RuntimeError(
                "hsDiversitySorting requires sentence-transformers and a working torch runtime."
            ) from exc
        self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        self.similarity_threshold = similarity_threshold
        
    def compute_similarity(self, emb_i, emb_j):
        return np.dot(emb_i, emb_j) / (np.linalg.norm(emb_i) * np.linalg.norm(emb_j))

    def sort_population(self, population, popsize):
        # Sort population by 'evaluation_score'
        sorted_population = sorted(population, key=lambda ind: ind['evaluation_score'])
        selected_population = []
        non_selected_population = []
        embeddings = {}
        
        # Group individuals by their evaluation score
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
                
                embedding = self.model.encode(obj_code, convert_to_numpy=True)
                embeddings[obj_code] = embedding
                
                # Check similarity within the same evaluation score layer
                if all(self.compute_similarity(embedding, embeddings[sel['obj_code']]) < self.similarity_threshold for sel in group_input):
                    group_input['obj_code'] = obj_code  # Store obj_code to reference later
                    layer_selected.append(ind)
                else:
                    non_selected_population.append(ind)
                
                if len(selected_population) + len(layer_selected) >= popsize:
                    selected_population.extend(layer_selected[:popsize - len(selected_population)])
                    return selected_population
            
            selected_population.extend(layer_selected)
        
        # Fill remaining slots from non-selected based on evaluation_score
        for ind in non_selected_population:
            if len(selected_population) < popsize:
                selected_population.append(ind)
            else:
                break
        
        return selected_population
