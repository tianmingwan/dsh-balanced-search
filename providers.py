"""balanced-search providers: Keenable / Exa / Tavily 统一客户端与轮换调度。

- 每个 provider 一个类，search() 返回归一化的 SearchResult 列表
- Balancer 负责 round-robin 轮换 + 某个 provider 失败时自动切换下一个
- build_balancer() 按环境变量里配置的 key 构建 provider 列表
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

HTTP_TIMEOUT = httpx.Timeout(30.0)

# time_range (day/week/month/year) 映射
DAYS_BY_RANGE = {"day": 1, "week": 7, "month": 30, "year": 365}
# Keenable 支持相对时间: min / h / d / mo / y
KEENABLE_REL = {"day": "1d", "week": "7d", "month": "1mo", "year": "1y"}


class ProviderError(RuntimeError):
    """provider 调用失败（网络、认证、限流、响应异常等）。"""


@dataclass
class SearchResult:
    title: str = ""
    url: str = ""
    content: str = ""
    published_at: str = ""
    score: Optional[float] = None
    provider: str = ""

    def to_dict(self) -> dict:
        d = {"title": self.title, "url": self.url, "content": self.content}
        if self.published_at:
            d["published_at"] = self.published_at
        if self.score is not None:
            d["score"] = self.score
        return d


@dataclass
class FetchResult:
    url: str = ""
    title: str = ""
    content: str = ""
    provider: str = ""

    def to_dict(self) -> dict:
        return {"url": self.url, "title": self.title, "content": self.content}


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )


def _post_json(http: httpx.Client, endpoint: str, body: dict, ctx: str) -> dict:
    """POST JSON 并统一把网络/HTTP/解析错误包装成 ProviderError。"""
    try:
        resp = http.post(endpoint, json=body)
    except httpx.HTTPError as e:
        raise ProviderError(f"{ctx} 网络错误: {e}") from e
    if resp.status_code != 200:
        raise ProviderError(f"{ctx} HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        return resp.json()
    except ValueError as e:
        raise ProviderError(f"{ctx} 响应不是合法 JSON: {e}") from e


def _get_json(http: httpx.Client, endpoint: str, params: dict, ctx: str) -> dict:
    """GET 并统一把网络/HTTP/解析错误包装成 ProviderError。"""
    try:
        resp = http.get(endpoint, params=params)
    except httpx.HTTPError as e:
        raise ProviderError(f"{ctx} 网络错误: {e}") from e
    if resp.status_code != 200:
        raise ProviderError(f"{ctx} HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        return resp.json()
    except ValueError as e:
        raise ProviderError(f"{ctx} 响应不是合法 JSON: {e}") from e


class SearchProvider:
    name = ""

    def search(self, query: str, max_results: int, time_range: Optional[str]) -> list[SearchResult]:
        raise NotImplementedError

    def fetch(self, url: str, max_chars: Optional[int] = None, live: bool = False) -> FetchResult:
        raise NotImplementedError


class KeenableProvider(SearchProvider):
    """Keen Search by Keenable — POST https://api.keenable.ai/v1/search，X-API-Key 请求头。

    无结果数量参数（默认返回约 10 条）；time_range 映射为 published_after 相对时间。
    """
    name = "keenable"
    ENDPOINT = "https://api.keenable.ai/v1/search"
    ENDPOINT_FETCH = "https://api.keenable.ai/v1/fetch"

    def __init__(self, api_key: str):
        self._http = httpx.Client(
            timeout=HTTP_TIMEOUT, headers={"X-API-Key": api_key}
        )

    def search(self, query: str, max_results: int, time_range: Optional[str]) -> list[SearchResult]:
        body = {"query": query, "mode": "realtime"}
        if time_range:
            body["published_after"] = KEENABLE_REL[time_range]
        data = _post_json(self._http, self.ENDPOINT, body, "keenable")
        results = []
        for item in data.get("results", []):
            content = item.get("snippet") or item.get("description") or ""
            results.append(
                SearchResult(
                    title=item.get("title") or "",
                    url=item.get("url") or "",
                    content=content.strip(),
                    published_at=item.get("published_at") or "",
                    provider=self.name,
                )
            )
        return results

    def fetch(self, url: str, max_chars: Optional[int] = None, live: bool = False) -> FetchResult:
        params: dict = {"url": url}
        if max_chars:
            params["max_chars"] = str(max_chars)
        if live:
            params["live"] = "true"
        data = _get_json(self._http, self.ENDPOINT_FETCH, params, "keenable")
        return FetchResult(
            url=data.get("url") or url,
            title=data.get("title") or "",
            content=(data.get("content") or "").strip(),
            provider=self.name,
        )


class ExaProvider(SearchProvider):
    """Exa — POST https://api.exa.ai/search，x-api-key 请求头。"""
    name = "exa"
    ENDPOINT = "https://api.exa.ai/search"
    ENDPOINT_CONTENTS = "https://api.exa.ai/contents"

    def __init__(self, api_key: str):
        self._http = httpx.Client(
            timeout=HTTP_TIMEOUT, headers={"x-api-key": api_key}
        )

    def search(self, query: str, max_results: int, time_range: Optional[str]) -> list[SearchResult]:
        body = {
            "query": query,
            "type": "auto",
            "numResults": max_results,
            "contents": {"text": {"maxCharacters": 3000}, "title": True},
        }
        if time_range:
            body["startPublishedDate"] = _iso_days_ago(DAYS_BY_RANGE[time_range])
        data = _post_json(self._http, self.ENDPOINT, body, "exa")
        results = []
        for item in data.get("results", []):
            results.append(
                SearchResult(
                    title=item.get("title") or "",
                    url=item.get("url") or "",
                    content=(item.get("text") or "").strip(),
                    published_at=item.get("publishedDate") or "",
                    provider=self.name,
                )
            )
        return results

    def fetch(self, url: str, max_chars: Optional[int] = None, live: bool = False) -> FetchResult:
        body = {
            "urls": [url],
            "text": {"maxCharacters": max_chars or 30000},
        }
        if live:
            body["maxAgeHours"] = 0
        data = _post_json(self._http, self.ENDPOINT_CONTENTS, body, "exa")
        for item in data.get("results", []):
            if item.get("url") == url or item.get("id") == url:
                return FetchResult(
                    url=item.get("url") or url,
                    title=item.get("title") or "",
                    content=(item.get("text") or "").strip(),
                    provider=self.name,
                )
        if data.get("results"):
            item = data["results"][0]
            return FetchResult(
                url=item.get("url") or url,
                title=item.get("title") or "",
                content=(item.get("text") or "").strip(),
                provider=self.name,
            )
        raise ProviderError("exa 抓取无结果")


class TavilyProvider(SearchProvider):
    """Tavily — POST https://api.tavily.com/search，Authorization: Bearer 请求头。"""
    name = "tavily"
    ENDPOINT = "https://api.tavily.com/search"
    ENDPOINT_EXTRACT = "https://api.tavily.com/extract"

    def __init__(self, api_key: str):
        self._http = httpx.Client(
            timeout=HTTP_TIMEOUT, headers={"Authorization": f"Bearer {api_key}"}
        )

    def search(self, query: str, max_results: int, time_range: Optional[str]) -> list[SearchResult]:
        body = {
            "query": query,
            "search_depth": "advanced",
            "max_results": max_results,
        }
        if time_range:
            body["time_range"] = time_range  # day / week / month / year（Tavily 原生值）
        data = _post_json(self._http, self.ENDPOINT, body, "tavily")
        results = []
        for item in data.get("results", []):
            results.append(
                SearchResult(
                    title=item.get("title") or "",
                    url=item.get("url") or "",
                    content=(item.get("content") or "").strip(),
                    score=item.get("score"),
                    provider=self.name,
                )
            )
        return results

    def fetch(self, url: str, max_chars: Optional[int] = None, live: bool = False) -> FetchResult:
        body = {
            "urls": [url],
            "extract_depth": "advanced",
            "format": "markdown",
        }
        data = _post_json(self._http, self.ENDPOINT_EXTRACT, body, "tavily")
        results = data.get("results") or []
        if not results:
            failed = data.get("failed_results") or []
            err = failed[0].get("error") if failed else "无结果"
            raise ProviderError(f"tavily 抓取失败: {err}")
        item = results[0]
        return FetchResult(
            url=item.get("url") or url,
            title=item.get("title") or "",
            content=(item.get("raw_content") or "").strip(),
            provider=self.name,
        )


class Balancer:
    """round-robin 轮换；某 provider 失败时自动尝试下一个，全部失败才抛错。"""

    def __init__(self, providers: list[SearchProvider]):
        if not providers:
            raise ValueError("至少需要一个 provider")
        self._providers = providers
        self._next = 0
        self._lock = threading.Lock()

    def search(self, query: str, max_results: int, time_range: Optional[str]) -> tuple[str, list[SearchResult]]:
        with self._lock:
            start = self._next
            self._next = (self._next + 1) % len(self._providers)
        errors = []
        for offset in range(len(self._providers)):
            provider = self._providers[(start + offset) % len(self._providers)]
            try:
                results = provider.search(query, max_results, time_range)
                return provider.name, results[:max_results]
            except Exception as e:  # 任何异常都切换下一个 provider
                errors.append(f"{provider.name}: {e}")
        raise ProviderError("全部搜索 provider 均失败 → " + " | ".join(errors))

    def fetch(self, url: str, max_chars: Optional[int] = None, live: bool = False) -> tuple[str, FetchResult]:
        with self._lock:
            start = self._next
            self._next = (self._next + 1) % len(self._providers)
        errors = []
        for offset in range(len(self._providers)):
            provider = self._providers[(start + offset) % len(self._providers)]
            try:
                result = provider.fetch(url, max_chars, live)
                return provider.name, result
            except Exception as e:  # 任何异常都切换下一个 provider
                errors.append(f"{provider.name}: {e}")
        raise ProviderError("全部抓取 provider 均失败 → " + " | ".join(errors))


def build_balancer(env: Optional[dict] = None) -> Balancer:
    """按环境变量里配置的 key 构建 provider 列表（配置了哪些就用哪些）。"""
    env = env if env is not None else os.environ
    providers = []
    if env.get("KEENABLE_API_KEY"):
        providers.append(KeenableProvider(env["KEENABLE_API_KEY"]))
    if env.get("EXA_API_KEY"):
        providers.append(ExaProvider(env["EXA_API_KEY"]))
    if env.get("TAVILY_API_KEY"):
        providers.append(TavilyProvider(env["TAVILY_API_KEY"]))
    if not providers:
        raise RuntimeError(
            "未配置任何搜索 API key（请设置 KEENABLE_API_KEY / EXA_API_KEY / TAVILY_API_KEY）"
        )
    return Balancer(providers)
