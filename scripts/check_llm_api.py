"""LLM API 连通性检查 — Phase⑤ D1 在线预飞。

走真实生产路径（configPara → InterfaceAPI → getResponse），
发一条极短 prompt 验证端到端连通。

用法:
    .venv/Scripts/python scripts/check_llm_api.py
退出码: 0 成功, 1 失败
"""

import sys
import time
from urllib.parse import urlparse

from script_common import load_config
from llmAPI.llmInterface import InterfaceAPI


def _mask_endpoint(endpoint):
    """只保留域名，隐藏路径和凭证。"""
    if not endpoint:
        return "<missing>"
    parsed = urlparse(endpoint)
    return parsed.netloc or endpoint.split("/")[0]


def main():
    config = load_config()

    # ---- 诊断信息 ----
    print(
        f"platform={config.llmPlatform}  "
        f"model={config.llmModel}  "
        f"endpoint={_mask_endpoint(config.api_endpoint)}  "
        f"n_trial={config.n_trial}"
    )

    if not config.api_key or not config.api_endpoint:
        print("error=LLM config missing. Check config/setting.cfg + config/env/.env",
              file=sys.stderr)
        print("status=FAIL")
        return 1

    try:
        api = InterfaceAPI(config)
    except Exception as exc:
        print(f"error=InterfaceAPI init failed: {exc}", file=sys.stderr)
        print("status=FAIL")
        return 1

    # ---- 发送测试 prompt ----
    try:
        start = time.perf_counter()
        response = str(api.getResponse("Say OK"))
        elapsed = time.perf_counter() - start

        preview = response.replace("\r", " ").replace("\n", " ")[:200]
        print(f"elapsed_sec={elapsed:.2f}")
        print(f"response_preview={preview}")
        print("status=SUCCESS")
        return 0
    except Exception as exc:
        elapsed = time.perf_counter() - start
        print(f"elapsed_sec={elapsed:.2f}")
        print(f"error={exc}", file=sys.stderr)
        print("status=FAIL")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
