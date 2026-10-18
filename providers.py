"""balanced-search providers: Keenable / Exa / Tavily / Firecrawl
统一客户端与轮换调度。

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
# Firecrawl 用 Google 的 tbs 相对时间窗口码表达"最近多久"
FIRECRAWL_TBS = {"day": "qdr:d", "week": "qdr:w", "month": "qdr:m", "year": "qdr:y"}

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
    # 只有真正知道原始页面状态码的 provider（目前仅 Firecrawl）才填；其余留 None，
    # to_dict 里也要省略，免得上游把"没测到"当成"页面返回了 200"。
    status_code: Optional[int] = None

    def to_dict(self) -> dict:
        d = {"url": self.url, "title": self.title, "content": self.content}
        if self.status_code is not None:
            d["status_code"] = self.status_code
        return d


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


class FirecrawlProvider(SearchProvider):
    """Firecrawl — POST https://api.firecrawl.dev/v2/{search,scrape}，Bearer 鉴权。

    与 Keenable/Exa/Tavily 不同，它把抓到的原始页面状态码带回来（metadata.statusCode），
    是唯一能如实回答"页面本身返回了什么状态"的 provider。

    两个成本约束决定了请求参数：
      - search 按 10 条结果 2 credits 计费（向上取整），所以 limit 直接用调用方要的条数，
        不要固定要一大把；
      - 在 /search 上挂 scrapeOptions 会把每条结果都变成一次抓取（各 1 credit），而这里只
        需要卡片摘要，所以只用默认的 description，不请求正文。
    """
    name = "firecrawl"
    ENDPOINT_SEARCH = "https://api.firecrawl.dev/v2/search"
    ENDPOINT_SCRAPE = "https://api.firecrawl.dev/v2/scrape"
    # description 有时是抽取出的整页文字而非摘要，卡片放不下，按 Exa 的正文预算截断。
    SNIPPET_LIMIT = 2000

    def __init__(self, api_key: str):
        self._http = httpx.Client(
            timeout=HTTP_TIMEOUT, headers={"Authorization": f"Bearer {api_key}"}
        )

    def search(self, query: str, max_results: int, time_range: Optional[str]) -> list[SearchResult]:
        # sources 固定 web：不限定的话响应里还可能带 news/images，归一化结果放不下。
        body: dict = {"query": query, "limit": max_results, "sources": ["web"]}
        if time_range:
            body["tbs"] = FIRECRAWL_TBS[time_range]
        data = _post_json(self._http, self.ENDPOINT_SEARCH, body, "firecrawl")
        results = []
        for item in (data.get("data") or {}).get("web") or []:
            results.append(
                SearchResult(
                    title=item.get("title") or "",
                    url=item.get("url") or "",
                    content=str(item.get("description") or "").strip()[: self.SNIPPET_LIMIT],
                    provider=self.name,
                )
            )
        return results

    def fetch(self, url: str, max_chars: Optional[int] = None, live: bool = False) -> FetchResult:
        body: dict = {
            "url": url,
            "formats": ["markdown"],
            # 导航栏、页脚、cookie 横幅对工具调用都是噪音，只留正文。
            "onlyMainContent": True,
        }
        # Firecrawl 默认最多返回 2 天内的缓存副本。本插件里 live 的语义是"绕过索引/缓存"，
        # 对应的就是 maxAge: 0 —— 代价是更慢，也更可能触发完整抓取失败。
        if live:
            body["maxAge"] = 0
        data = _post_json(self._http, self.ENDPOINT_SCRAPE, body, "firecrawl")
        doc = data.get("data")
        if not doc:
            raise ProviderError("firecrawl 抓取无结果")
        raw = str(doc.get("markdown") or "").strip()
        if raw == "":
            raise ProviderError("firecrawl 抓取返回空正文")
        metadata = doc.get("metadata") or {}
        status_code = metadata.get("statusCode")
        return FetchResult(
            url=metadata.get("sourceURL") or doc.get("url") or url,
            title=metadata.get("title") or metadata.get("ogTitle") or "",
            content=raw[:max_chars] if max_chars else raw,
            # REST 几家 provider 里只有 Firecrawl 真的把源站状态码交回来，其余置 None。
            status_code=status_code if isinstance(status_code, int) else None,
            provider=self.name,
        )
class Balancer:
    """round-robin 轮换；某 provider 失败时自动尝试下一个，全部失败才抛错。"""

    def __init__(self, providers: list[SearchProvider]):
        if not providers:
            raise ValueError("至少需要一个 provider")
        self._providers = providers
        # 两个能力各用独立游标，刻意不共享：搜索和抓取的调用频率不同，共用一个游标会让
        # 轮换失效 —— 只有两个 provider 且请求搜索/抓取交替出现时，会把每次搜索都钉在
        # A 家、每次抓取都钉在 B 家。（JS 版早已拆分，这是 Python 侧的历史 bug。）
        self._next_search = 0
        self._next_fetch = 0
        self._lock = threading.Lock()

    def _take(self, capability: str) -> int:
        """领取该能力的起始下标并推进它自己的游标。"""
        with self._lock:
            current = getattr(self, f"_next_{capability}")
            setattr(self, f"_next_{capability}", (current + 1) % len(self._providers))
            return current

    def search(self, query: str, max_results: int, time_range: Optional[str]) -> tuple[str, list[SearchResult]]:
        start = self._take("search")
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
        start = self._take("fetch")
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
    if env.get("FIRECRAWL_API_KEY"):
        providers.append(FirecrawlProvider(env["FIRECRAWL_API_KEY"]))
    if not providers:
        raise RuntimeError(
            "未配置任何搜索 API key（请设置 KEENABLE_API_KEY / EXA_API_KEY / TAVILY_API_KEY "
            "/ FIRECRAWL_API_KEY）"
        )
    return Balancer(providers)
