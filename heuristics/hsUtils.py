"""
* 文件: hsUtils.py
* 作者: Ni Yun
*
* 创建日期: 2025/02/20
"""

import json
import re

def json_load(parse_func):
    """
    JSON 加载装饰器，用于尝试从 LLM 回复中解析 JSON 对象。
    """
    def wrapper(json_response):
        try:
            # 尝试将整个响应解析为单个 JSON 对象
            response = json.loads(json_response)
            if parse_func(response):
                return parse_func(response)
        except json.JSONDecodeError:
            # 如果解析失败，尝试提取回复中的多个 JSON 对象（处理包含解释文本的情况）
            json_objects = re.findall(r'\{.*?\}', json_response, re.DOTALL)
            for obj in json_objects:
                try:
                    response = json.loads(obj)
                    if parse_func(response):
                        return parse_func(response)
                except json.JSONDecodeError:
                    continue

        # 如果未找到 obj_code，返回空字符串
        print("警告: 无法从 JSON 响应中提取内容。")
        return " "

    return wrapper


@json_load
def extract_code_hsPopulation(response):
    """
    从种群更新阶段的 LLM 响应中提取代码。
    """
    if isinstance(response, dict):
        if "obj_code" in response:
            return response["obj_code"]

        # 如果 obj_code 被嵌套，递归搜索
        for value in response.values():
            if isinstance(value, dict) and "obj_code" in value:
                return value["obj_code"]


@json_load
def extract_code_hsIndiv(response):
    """
    从单体运行阶段的 LLM 响应中提取代码。
    """
    if "obj_code" in response:
        return response["obj_code"]


@json_load
def extract_traj_code_hsIndiv(response):
    """
    从 L2b LLM 响应中提取轨迹目标函数代码（traj_obj_code）。
    """
    if "traj_obj_code" in response:
        return response["traj_obj_code"]
