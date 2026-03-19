"""
* File: llmInterface_huggingface.py
* Author: Ni Yun
*
* created on 2025/02/15
"""
import http.client
import json
import time
import re
import textwrap
from transformers import AutoTokenizer
import tiktoken
import requests

"""
InterfaceAPI_huggingface provides a request handler for interacting with
OpenAI-compatible LLM APIs (HuggingFace, OpenAI, DeepSeek, CloseAI, etc.).
--------------------
响应解析支持三种格式（自动检测，优先级从高到低）：
  1. DeepSeek-R1 格式：content 中包含 <think>...</think>，提取 </think> 后的 JSON
  2. 通用格式：content 中无 <think> 标签，直接从 content 提取 JSON
  3. 兜底：无法提取 JSON 时，返回原始 content 文本
"""

class InterfaceAPI_huggingface:
    def __init__(self, configInfo):
        self.platform = configInfo.llmPlatform
        self.llmModel = configInfo.llmModel
        self.api_endpoint = self._normalize_endpoint(configInfo.api_endpoint)
        self.api_key = configInfo.api_key
        self.n_trial = configInfo.n_trial
        self.temperature = configInfo.temperature
        self.request_timeout = 60

    @staticmethod
    def _normalize_endpoint(endpoint):
        """确保 endpoint 以 /chat/completions 结尾。
        用户可填 https://xxx/v1 或 https://xxx/v1/chat/completions，均可正常工作。
        """
        if endpoint and not endpoint.rstrip("/").endswith("/chat/completions"):
            return endpoint.rstrip("/") + "/chat/completions"
        return endpoint

    def prepare_header(self):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        return headers


    def prepare_payload(self, prompt, max_length=None):
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    #"temperature": self.temperature
                }
            ],
            "model": self.llmModel
        }

        return payload


    def _extract_json(self, text):
        """从文本中提取最外层 JSON 对象（{...}），找不到则返回 None。"""
        match = re.search(r'\{.*\}', text, flags=re.DOTALL)
        return match.group().strip() if match else None

    def _parse_content(self, generated_text):
        """从 LLM 响应 content 中提取有效负载。

        解析优先级：
          1. 有 <think> 标签 → 取 </think> 之后的部分，再提取 JSON
          2. 无 <think> 标签 → 直接从整段 content 提取 JSON
          3. 都没有 JSON  → 返回原始文本
        """
        # 路径 1：DeepSeek-R1 格式（<think>...</think> + 正文）
        think_match = re.search(r'<think>(.*)', generated_text, flags=re.DOTALL)
        if think_match:
            after_think = re.split(r'</think>\s*', think_match.group(1))[-1].strip()
            json_str = self._extract_json(after_think)
            if json_str:
                return json_str
            # </think> 后无 JSON，回退到整段提取
            return self._extract_json(generated_text) or after_think

        # 路径 2：通用格式（无 <think> 标签）
        json_str = self._extract_json(generated_text)
        if json_str:
            return json_str

        # 路径 3：兜底，返回原始文本
        return generated_text

    def getResponse(self, prompt):
        payload = self.prepare_payload(prompt)
        headers = self.prepare_header()

        last_error = None
        trial_count = 0
        while trial_count < self.n_trial:
            trial_count += 1
            try:
                raw_resp = requests.post(
                    self.api_endpoint, headers=headers, json=payload,
                    timeout=self.request_timeout,
                )
                raw_resp.raise_for_status()
                json_data = raw_resp.json()

                generated_text = json_data["choices"][0]["message"]["content"]
                if generated_text:
                    response = self._parse_content(generated_text)
                    print(response)
                    return response
                else:
                    error_msg = json_data.get("error", "No generated_text or error field found")
                    raise RuntimeError(f"LLM returned empty content: {error_msg}")
            except Exception as e:
                last_error = e
                print(f"API Connection Fails! Error: {e}. Trial {trial_count}/{self.n_trial}")
                time.sleep(2)

        raise RuntimeError(
            f"LLM API failed after {self.n_trial} retries. Last error: {last_error}"
        )
