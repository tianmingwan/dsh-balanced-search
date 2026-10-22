"""balanced-search providers: Keenable / Exa / Tavily / Firecrawl / AnySearch /
TinyFish 统一客户端与轮换调度。

- 每个 provider 一个类，search() 返回归一化的 SearchResult 列表
- Balancer 负责 round-robin 轮换 + 某个 provider 失败时自动切换下一个，
  并把 auth / quota / rate 三类失败短暂"停放"（cooldown），避免每次轮换都先撞一个
  已知不可用的厂商
- build_balancer() 按环境变量里配置的 key 构建 provider 列表
"""
from __future__ import annotations

import os
import re
import threading
import time
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
# TinyFish 用"最近多少分钟"表达回溯窗口
TINYFISH_RECENCY_MINUTES = {
    "day": 1440,
    "week": 10080,
    "month": 43200,
    "year": 525600,
}

# 各类失败后该 vendor 被跳过多久（秒）。额度/认证失败要停久一点：池子里的免费额度多是
# 按天/按月计，对着已经干掉的 key 每次轮换都重试一遍只会白等延迟；限流则只需要歇一会儿。
# 都刻意远小于额度周期——用户可能中途充值，为了发现它而重启进程更糟。
COOLDOWN_SECONDS = {"auth": 30 * 60, "quota": 20 * 60, "rate": 30}

# 429 的响应体在池子里含义不统一：有的厂商是限流，有的其实是余额/额度用完。
_RATE_LIMIT_RE = re.compile(r"rate[ _-]?limit", re.IGNORECASE)
_QUOTA_RE = re.compile(r"insufficient|quota|credit|balance|allowance|payment", re.IGNORECASE)


class ProviderError(RuntimeError):
    """provider 调用失败（网络、认证、限流、响应异常等）。

    kind 说明失败类别，Balancer 据此决定要不要把该 provider 停放一段时间：
    auth / quota / rate 会停放，generic（普通 4xx/5xx、超时、解析失败等）只在本次调用
    里切换下一家。
    """

    def __init__(self, message: str, kind: str = "generic"):
        super().__init__(message)
        self.kind = kind


def _classify_failure(status: int, body: str) -> str:
    """把 HTTP 状态码 + 响应体映射到 ProviderError.kind（对应 JS 版 classifyFailure）。

    429 必须靠响应体区分：限流文案里会出现 rate/limit，额度文案里是 funds/credits；
    有些额度文案也带 "exceeded"，所以限流措辞要先判。
    """
    if status in (401, 403):
        return "auth"
    if status == 402:
        return "quota"
    if status == 429:
        if _RATE_LIMIT_RE.search(body):
            return "rate"
        return "quota" if _QUOTA_RE.search(body) else "rate"
    return "generic"


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


def _raise_for_status(resp: httpx.Response, ctx: str) -> None:
    """非 200 统一包成 ProviderError，并按状态码/响应体分类（供 cooldown 使用）。"""
    if resp.status_code != 200:
        raise ProviderError(
            f"{ctx} HTTP {resp.status_code}: {resp.text[:200]}",
            _classify_failure(resp.status_code, resp.text),
        )


def _post_json(http: httpx.Client, endpoint: str, body: dict, ctx: str) -> dict:
    """POST JSON 并统一把网络/HTTP/解析错误包装成 ProviderError。"""
    try:
        resp = http.post(endpoint, json=body)
    except httpx.TimeoutException as e:
        raise ProviderError(f"{ctx} 请求超时") from e
    except httpx.HTTPError as e:
        raise ProviderError(f"{ctx} 网络错误: {e}") from e
    _raise_for_status(resp, ctx)
    try:
        return resp.json()
    except ValueError as e:
        raise ProviderError(f"{ctx} 响应不是合法 JSON: {e}") from e


def _get_json(http: httpx.Client, endpoint: str, params: dict, ctx: str) -> dict:
    """GET 并统一把网络/HTTP/解析错误包装成 ProviderError。"""
    try:
        resp = http.get(endpoint, params=params)
    except httpx.TimeoutException as e:
        raise ProviderError(f"{ctx} 请求超时") from e
    except httpx.HTTPError as e:
        raise ProviderError(f"{ctx} 网络错误: {e}") from e
    _raise_for_status(resp, ctx)
    try:
        return resp.json()
    except ValueError as e:
        raise ProviderError(f"{ctx} 响应不是合法 JSON: {e}") from e


class SearchProvider:
    name = ""
    # 该厂商是否真的能按"最近 N 天"过滤。False 的 provider 不会被分配带 time_range 的
    # 搜索（除非池子里没有一家支持），免得用未过滤的结果冒充过滤过的结果。
    supports_time_range = True

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


class AnySearchProvider(SearchProvider):
    """AnySearch — POST https://api.anysearch.com/v1/search，Authorization: Bearer as_sk_…

    免费档是纯"每天 1,000 次请求"的预算（search 与 extract 共用，每 key 20 QPS），参数怎么
    传都不改变单次成本。适配层被两个厂商限制决定：
      - max_results 服务端硬上限 10，超过会被静默截断；本地先 clamp，否则调用方要 20 条
        却只拿到 10 条时，会以为结果本来就少；
      - 完全没有 recency 参数（time_range/freshness 传了也被忽略、不报错），所以
        supports_time_range=False，由 Balancer 把带时间过滤的搜索只发给能回溯的厂商。

    extract 是抓取能力，请求体是严格 schema：只能有 url 一个字段，多一个（哪怕 maxChars）
    就 400，且报错文案是误导性的 "URL is invalid."（真实原因在 error_code 里）。
    """
    name = "anysearch"
    supports_time_range = False
    ENDPOINT = "https://api.anysearch.com/v1/search"
    ENDPOINT_EXTRACT = "https://api.anysearch.com/v1/extract"
    # 服务端硬上限，超过会被静默截断。
    MAX_RESULTS = 10

    def __init__(self, api_key: str):
        self._http = httpx.Client(
            timeout=HTTP_TIMEOUT, headers={"Authorization": f"Bearer {api_key}"}
        )

    def search(self, query: str, max_results: int, time_range: Optional[str]) -> list[SearchResult]:
        # time_range 刻意不发送：端点没有这个字段，发了也只是被忽略，等于对调用方撒谎。
        body = {"query": query, "max_results": min(max_results, self.MAX_RESULTS)}
        data = _post_json(self._http, self.ENDPOINT, body, "anysearch")
        # 统一信封用 code 表示成功（0）；2xx 但非 0 时不能当成"没有结果"。
        if data.get("code") not in (None, 0):
            raise ProviderError(f"anysearch: {data.get('message') or '搜索失败'}")
        results = []
        for item in (data.get("data") or {}).get("results") or []:
            # snippet 与 content 都是可选字段（缺失而非 null），普通网页搜索里两者长度接近；
            # 优先 snippet 让卡片载荷更小。
            snippet = item.get("snippet")
            content = item.get("content") if snippet is None else snippet
            results.append(
                SearchResult(
                    title=item.get("title") or "",
                    url=item.get("url") or "",
                    content=str(content or "").strip(),
                    # 响应里完全没有发布日期（只有英文短语形式的日期文本），不猜。
                    provider=self.name,
                )
            )
        return results

    def fetch(self, url: str, max_chars: Optional[int] = None, live: bool = False) -> FetchResult:
        # 严格 schema：body 里只有 url。maxChars/live 在这里没有对应参数（抽取始终是实时的，
        # 服务端正文上限约 50k），所以截断在本地做。
        data = _post_json(self._http, self.ENDPOINT_EXTRACT, {"url": url}, "anysearch")
        doc = data.get("data")
        if not doc:
            raise ProviderError("anysearch 抓取无结果")
        raw = str(doc.get("content") or "").strip()
        if raw == "":
            raise ProviderError("anysearch 抓取返回空正文")
        return FetchResult(
            url=doc.get("url") or url,
            title=doc.get("title") or "",
            content=raw[:max_chars] if max_chars else raw,
            provider=self.name,
        )


class TinyFishProvider(SearchProvider):
    """TinyFish — GET api.search.tinyfish.ai / POST api.fetch.tinyfish.ai，X-API-Key 请求头。

    注意鉴权头是 `X-API-Key`（不是 Bearer）：带 `Authorization` 会被直接 401。

    Search 与 Fetch 在所有档位都是 $0（不扣 wallet/credits），额度很宽
    （12,000 次搜索/天、500/小时，1,000 个抓取 URL/天），所以适配层不需要省额度，只要贴合
    接口形状：
      - 搜索是 GET，参数全在 query string；
      - 没有 maxResults 参数，每页固定 10 条。要超过 10 条就得再发一次 page=1，两页会有
        少量重叠，合并时按 url 去重；
      - recency_minutes 是相对窗口，时间过滤能精确表达（这点和 AnySearch 相反）；
      - fetch 即使页面失败也返回 HTTP 200，失败信息在 errors[] 里，必须先检查。
    """
    name = "tinyfish"
    ENDPOINT = "https://api.search.tinyfish.ai"
    ENDPOINT_FETCH = "https://api.fetch.tinyfish.ai"
    # 每页固定 10 条，没有 max_results 参数。
    PAGE_SIZE = 10

    def __init__(self, api_key: str):
        self._http = httpx.Client(
            timeout=HTTP_TIMEOUT, headers={"X-API-Key": api_key}
        )

    def _search_page(
        self, query: str, time_range: Optional[str], page: int
    ) -> list[dict]:
        params: dict = {"query": query}
        if time_range:
            params["recency_minutes"] = str(TINYFISH_RECENCY_MINUTES[time_range])
        if page > 0:
            params["page"] = str(page)
        data = _get_json(self._http, self.ENDPOINT, params, "tinyfish")
        return data.get("results") or []

    def search(self, query: str, max_results: int, time_range: Optional[str]) -> list[SearchResult]:
        first = self._search_page(query, time_range, 0)
        # 只有调用方要的条数超过一页时才值得再发一次；不到一页的由 Balancer 截断。
        pages = [first]
        if max_results > self.PAGE_SIZE:
            pages.append(self._search_page(query, time_range, 1))
        seen: set[str] = set()
        results = []
        for item in (entry for page in pages for entry in page):
            url = item.get("url") or ""
            if url == "" or url in seen:
                continue
            seen.add(url)
            results.append(
                SearchResult(
                    title=item.get("title") or "",
                    url=url,
                    content=str(item.get("snippet") or "").strip(),
                    # results[].date 是"8 hours ago"这类人类可读字符串，不是 ISO 8601 且常缺失，
                    # 从它反推时间点等于编造厂商没给的精度，所以不填。
                    provider=self.name,
                )
            )
        return results

    def fetch(self, url: str, max_chars: Optional[int] = None, live: bool = False) -> FetchResult:
        body: dict = {"urls": [url], "format": "markdown"}
        # 不传 ttl 表示接受任意缓存；ttl: 0 是厂商的"回源"，对应本插件到处使用的 live 语义。
        if live:
            body["ttl"] = 0
        data = _post_json(self._http, self.ENDPOINT_FETCH, body, "tinyfish")
        results = data.get("results") or []
        item = results[0] if results else None
        if not item:
            # 单 URL 失败是 HTTP 200 + errors[]，不能当成"没有结果"。
            failures = data.get("errors") or []
            failure = failures[0] if failures else None
            if failure:
                detail = failure.get("error") or "未知错误"
                status = failure.get("status")
                suffix = f" (HTTP {status})" if status else ""
                raise ProviderError(f"tinyfish 抓取失败: {detail}{suffix}")
            raise ProviderError("tinyfish 抓取无结果")
        raw = str(item.get("text") or "").strip()
        if raw == "":
            raise ProviderError("tinyfish 抓取返回空正文")
        return FetchResult(
            url=item.get("final_url") or item.get("url") or url,
            title=item.get("title") or item.get("description") or "",
            content=raw[:max_chars] if max_chars else raw,
            provider=self.name,
        )


class Balancer:
    """round-robin 轮换；某 provider 失败时自动尝试下一个，全部失败才抛错。

    - 搜索与抓取各自独立推进游标（一次抓取不会改变下次搜索的起点）；
    - time_range 的请求只在"支持时间过滤"的 provider 之间轮换，池子里一家都不支持时
      才退回整个池子；
    - auth / quota / rate 失败会让该 provider 进入短暂的 cooldown（见 COOLDOWN_SECONDS），
      冷却中的 provider 不会被分配新请求；若全部都在冷却，则照常轮换整个池子
      （过期的 cooldown 绝不能演变成"没有可用 provider"）。
    """

    def __init__(self, providers: list[SearchProvider]):
        if not providers:
            raise ValueError("至少需要一个 provider")
        self._providers = providers
        # 两个能力各用独立游标，刻意不共享：搜索和抓取的调用频率不同，共用一个游标会让
        # 轮换失效 —— 只有两个 provider 且请求搜索/抓取交替出现时，会把每次搜索都钉在
        # A 家、每次抓取都钉在 B 家。（JS 版早已拆分，这是 Python 侧的历史 bug。）
        self._next_search = 0
        self._next_fetch = 0
        # provider.name → 单调时钟时间点，在此之前跳过该 provider。
        self._cooldown_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def _take(self, providers: list[SearchProvider], cursor: str) -> int:
        """领取该能力的起始下标并推进它自己的游标。"""
        with self._lock:
            current = getattr(self, cursor)
            start = current % len(providers)
            setattr(self, cursor, (current + 1) % len(providers))
            return start

    def _usable(self, providers: list[SearchProvider]) -> list[SearchProvider]:
        """当前值得尝试的 provider（保持轮换顺序）；全在冷却时原样返回。"""
        now = time.monotonic()
        with self._lock:
            fresh = [
                p for p in providers if self._cooldown_until.get(p.name, 0.0) <= now
            ]
        return fresh or providers

    def _park(self, provider: SearchProvider, error: Exception) -> None:
        seconds = COOLDOWN_SECONDS.get(getattr(error, "kind", "generic"))
        if seconds:
            with self._lock:
                self._cooldown_until[provider.name] = time.monotonic() + seconds

    def search(
        self, query: str, max_results: int, time_range: Optional[str] = None
    ) -> tuple[str, list[SearchResult]]:
        providers = self._usable(self._providers)
        if time_range:
            # 不是每家都能按时间过滤（AnySearch 根本没有这个参数），用未过滤结果冒充过滤
            # 结果会悄悄破坏调用方的契约。只在有能力的厂商里轮换；一家都没有才退回全池。
            capable = [p for p in providers if p.supports_time_range]
            if capable:
                providers = capable
        start = self._take(providers, "_next_search")
        errors = []
        for offset in range(len(providers)):
            provider = providers[(start + offset) % len(providers)]
            try:
                results = provider.search(query, max_results, time_range)
                return provider.name, results[:max_results]
            except Exception as e:  # 任何异常都切换下一个 provider
                self._park(provider, e)
                errors.append(f"{provider.name}: {e}")
        raise ProviderError("全部搜索 provider 均失败 → " + " | ".join(errors))

    def fetch(
        self, url: str, max_chars: Optional[int] = None, live: bool = False
    ) -> tuple[str, FetchResult]:
        providers = self._usable(self._providers)
        start = self._take(providers, "_next_fetch")
        errors = []
        for offset in range(len(providers)):
            provider = providers[(start + offset) % len(providers)]
            try:
                result = provider.fetch(url, max_chars, live)
                return provider.name, result
            except Exception as e:  # 任何异常都切换下一个 provider
                self._park(provider, e)
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
    if env.get("ANYSEARCH_API_KEY"):
        providers.append(AnySearchProvider(env["ANYSEARCH_API_KEY"]))
    if env.get("TINYFISH_API_KEY"):
        providers.append(TinyFishProvider(env["TINYFISH_API_KEY"]))
    if not providers:
        raise RuntimeError(
            "未配置任何搜索 API key（请设置 KEENABLE_API_KEY / EXA_API_KEY / TAVILY_API_KEY "
            "/ FIRECRAWL_API_KEY / ANYSEARCH_API_KEY / TINYFISH_API_KEY）"
        )
    return Balancer(providers)
