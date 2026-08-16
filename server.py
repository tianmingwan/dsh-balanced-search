"""balanced-search MCP server — 轮流调用 Keenable / Exa / Tavily 三个搜索 API。

用法:
    python server.py            # stdio 模式，供 MCP 客户端（如 ZCode）连接

环境变量（至少配置一个）:
    KEENABLE_API_KEY / EXA_API_KEY / TAVILY_API_KEY
也可在同目录 .env 文件中配置（本地测试用）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from providers import ProviderError, build_balancer

logging.getLogger("httpx").setLevel(logging.WARNING)  # 压掉每次请求的 HTTP 日志
load_dotenv(Path(__file__).resolve().parent / ".env")

mcp = MCPServer("balanced-search")

_TIME_RANGES = ("day", "week", "month", "year")

_balancer = None


def _get_balancer():
    global _balancer
    if _balancer is None:
        _balancer = build_balancer(os.environ)
    return _balancer


@mcp.tool()
def search(query: str, max_results: int = 8, time_range: Optional[str] = None) -> str:
    """搜索网页，返回标题、链接和内容摘要。

    三个搜索服务（Keenable / Exa / Tavily）轮流调用，某个服务失败时自动切换下一个。
    用于替代内置 WebSearch/WebFetch 的联网搜索场景。

    Args:
        query: 搜索关键词或自然语言问题。
        max_results: 返回结果条数，1-20，默认 8。
        time_range: 可选，只返回该时间范围内的结果：day / week / month / year。
    """
    query = (query or "").strip()
    if not query:
        return json.dumps({"error": "query 不能为空", "results": []}, ensure_ascii=False)
    try:
        max_results = max(1, min(20, int(max_results)))
    except (TypeError, ValueError):
        max_results = 8
    if time_range is not None and time_range not in _TIME_RANGES:
        return json.dumps(
            {"error": f"time_range 必须是 {_TIME_RANGES} 之一", "results": []},
            ensure_ascii=False,
        )

    try:
        provider, results = _get_balancer().search(query, max_results, time_range)
    except ProviderError as e:
        return json.dumps({"error": str(e), "results": []}, ensure_ascii=False)
    except Exception as e:  # 未预期错误也以 JSON 返回，避免 MCP 层崩溃
        return json.dumps({"error": f"内部错误: {e}", "results": []}, ensure_ascii=False)

    return json.dumps(
        {
            "provider": provider,
            "count": len(results),
            "results": [r.to_dict() for r in results],
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def fetch(url: str, max_chars: int = 30000, live: bool = False) -> str:
    """抓取指定 URL 的网页正文，返回 clean markdown 文本。

    三个服务（Keenable / Exa / Tavily）轮流调用，某个服务失败时自动切换下一个。
    Keenable 默认只支持其索引内的 URL，传 live=true 可直接从源站抓取（含未索引 URL）。

    Args:
        url: 要抓取的网页地址。
        max_chars: 返回内容的最大字符数，默认 30000。
        live: 是否实时从源站抓取（绕过索引/缓存），默认 false。
    """
    url = (url or "").strip()
    if not url:
        return json.dumps({"error": "url 不能为空"}, ensure_ascii=False)
    try:
        max_chars = max(1, min(50000, int(max_chars)))
    except (TypeError, ValueError):
        max_chars = 30000

    try:
        provider, result = _get_balancer().fetch(url, max_chars, bool(live))
    except ProviderError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except Exception as e:  # 未预期错误也以 JSON 返回，避免 MCP 层崩溃
        return json.dumps({"error": f"内部错误: {e}"}, ensure_ascii=False)

    return json.dumps(
        {"provider": provider, "result": result.to_dict()},
        ensure_ascii=False,
        indent=2,
    )


if __name__ == "__main__":
    asyncio.run(mcp.run_stdio_async())
