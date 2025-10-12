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
InterfaceAPI_huggingface provides a request handler for interacting with Hugging Face-hosted LLM APIs.
--------------------
This implementation is specifically designed and tested for the **DeepSeek-R1-Distill-Qwen-32B** model.
The `getResponse()` function assumes the model output format includes a `<think>...</think>` reasoning
block followed by the actual response content.

If you plan to use **other models**, please be aware that:
    - The response format may differ (e.g., absence of <think> tags or different JSON structures).
    - You must **implement your own parse function** inside `getResponse()` (or a new subclass)
    to correctly extract the intended output content from the model's response.

This design ensures flexibility while maintaining model-specific parsing integrity.
"""

class InterfaceAPI_huggingface:
    def __init__(self, configInfo):
        self.platform = configInfo.llmPlatform
        self.llmModel = configInfo.llmModel
        self.api_endpoint = configInfo.api_endpoint
        self.api_key = configInfo.api_key
        self.n_trial = configInfo.n_trial
        self.temperature = configInfo.temperature

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


    def getResponse(self, prompt):
        def extract_after_last_think(self, generated_text):
            parts = re.split(r'</think>\s*', generated_text)
            return parts[-1] if len(parts) > 1 else ""


        payload = self.prepare_payload(prompt)
        #payload_explanation = json.dumps(payload)
        payload_explanation = payload

        headers = self.prepare_header()

        response = None
        trial_count = 0
        while trial_count < self.n_trial:
            trial_count += 1
            try:
                response = requests.post(self.api_endpoint, headers=headers, json=payload_explanation)
                json_data = response.json()

                # Parse response and return raw text as 'generated_text' field
                generated_text = json_data["choices"][0]["message"]["content"]
                if generated_text:
                    match = re.search(r'<think>(.*)', generated_text, flags=re.DOTALL)

                    if match:
                        # Look for content after </think> symbol
                        extracted_text = match.group(1).strip()  # Extract content after </think>
                        json_match = re.search(r'\{.*\}', extracted_text, flags=re.DOTALL)
                        if json_match:
                            response = json_match.group().strip()  # Extract JSON content
                            print(response)
                        else:
                            response = extracted_text  # If no JSON found, return the extracted text
                else:
                    response = json_data.get("error", "No generated_text or error field found")
                break  # If successful, break out of the loop
            except Exception as e:
                print(f"API Connection Fails! Error: {e}. Will try to reconnect!")
                time.sleep(2)  # Optionally wait for 2 seconds before retrying

        return response
