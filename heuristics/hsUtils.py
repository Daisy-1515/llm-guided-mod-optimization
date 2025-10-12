"""
* File: hsUtils.py
* Author: Ni Yun
*
* created on 2025/02/20
"""

import json
import re

def json_load(parse_func):
    def wrapper(json_response):
        try:
            # Try parsing the response as a single JSON object
            response = json.loads(json_response)
            if parse_func(response):
                return parse_func(response)
        except json.JSONDecodeError:
            # If JSON parsing fails, attempt to extract multiple JSON objects
            json_objects = re.findall(r'\{.*?\}', json_response, re.DOTALL)
            for obj in json_objects:
                try:
                    response = json.loads(obj)
                    if parse_func(response):
                        return parse_func(response)
                except json.JSONDecodeError:
                    continue

        # If obj_code is not found, return an empty string
        print("Warning: Could not extract from json response.")
        return " "

    return wrapper


@json_load
def extract_code_hsPopulation(response):
    if isinstance(response, dict):
        if "obj_code" in response:
            return response["obj_code"]

        # If obj_code is nested, search for it recursively
        for value in response.values():
            if isinstance(value, dict) and "obj_code" in value:
                return value["obj_code"]


@json_load
def extract_code_hsIndiv(response):
    if "obj_code" in response:
        return response["obj_code"]




