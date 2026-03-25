"""
* File: llmInterface.py
* Author: Yi
*
* created on 2025/01/23
"""
"""
@package llmInterface.py
@brief This module handles the api call with LLM.
"""
from llmAPI.llmInterface_huggingface import InterfaceAPI_huggingface

class InterfaceAPI:
    """
        @class InterfaceAPI
        @brief Base factory for managing API calls with different LLM platforms.

        Usage:
            api = InterfaceAPI(configInfo)
            # This automatically creates an instance of the subclass
            # matching configInfo.llmPlatform (e.g., HuggingFace, OpenAI, etc.)

        To extend:
            If you are using a different platform other than HuggingFace, 
            please create a new child class following this template:

        Example:
        -----------------------------------------
        from llmAPI.llmInterface_base import InterfaceAPI

        class InterfaceAPI_OpenAI(InterfaceAPI):
            def __init__(self, configInfo):
                self.platform = configInfo.llmPlatform
                self.llmModel = configInfo.llmModel
                self.api_endpoint = configInfo.api_endpoint
                self.api_key = configInfo.api_key

            def getResponse(self, prompt):
                headers = {"Authorization": f"Bearer {self.api_key}"}
                payload = {"model": self.llmModel, "messages": [{"role": "user", "content": prompt}]}
                response = requests.post(self.api_endpoint, headers=headers, json=payload)
                return response.json()["choices"][0]["message"]["content"]
        -----------------------------------------
    """            
    def __new__(cls, configInfo):
            if configInfo.llmPlatform == "HuggingFace":
                return InterfaceAPI_huggingface(configInfo)
            else:
                raise NotImplementedError(
                    "For non-huggingface platform %s, please complete the logic to interact with the end server. A template has been provided" % configInfo.llmPlatform)
