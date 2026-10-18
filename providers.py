"""balanced-search providers: Keenable / Exa / Tavily / Firecrawl / BrightData
统一客户端与轮换调度。

- 每个 provider 一个类，search() 返回归一化的 SearchResult 列表
- Balancer 负责 round-robin 轮换 + 某个 provider 失败时自动切换下一个
- build_balancer() 按环境变量里配置的 key 构建 provider 列表
"""
from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

import httpx

HTTP_TIMEOUT = httpx.Timeout(30.0)

# time_range (day/week/month/year) 映射
DAYS_BY_RANGE = {"day": 1, "week": 7, "month": 30, "year": 365}
# Keenable 支持相对时间: min / h / d / mo / y
KEENABLE_REL = {"day": "1d", "week": "7d", "month": "1mo", "year": "1y"}
# Firecrawl 用 Google 的 tbs 相对时间窗口码表达"最近多久"
FIRECRAWL_TBS = {"day": "qdr:d", "week": "qdr:w", "month": "qdr:m", "year": "qdr:y"}

# Bright Data 的工具是远端代理任务而非索引查询，延迟波动很大：SERP 抓取实测 2.7–27s
# （并发时更慢）、页面抓取约 17s、连 initialize 都要约 1s。沿用通用的 30s 会让 Balancer
# 在它的不少轮次上直接超时切走，所以按能力单独放宽到覆盖长尾。抓取用 45s 而不是 60s：
# 工具层预算是 60s，provider 吃满整个预算就再没有故障切换的余量。
BRIGHTDATA_SEARCH_TIMEOUT = httpx.Timeout(40.0)
BRIGHTDATA_FETCH_TIMEOUT = httpx.Timeout(45.0)


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


class BrightDataProvider(SearchProvider):
    """Bright Data MCP — 托管在 https://mcp.brightdata.com/mcp?token=<token> 的
    Streamable HTTP MCP 服务，不是 REST API。

    它说 JSON-RPC：initialize → notifications/initialized → tools/call。这里只借用两个
    工具：search_engine（Google SERP 抓取）和 scrape_as_markdown（过反爬基础设施的正文
    抽取，所以慢）。由此带来的四个实现约束：

    1. 两个工具都是远端代理任务，比普通索引查询慢得多，所以按能力各配一个更长的
       超时（见文件顶部的 BRIGHTDATA_SEARCH_TIMEOUT / BRIGHTDATA_FETCH_TIMEOUT）。
    2. tools/call 的文本被服务端包在安全提示 + =====UNTRUSTED_<id>_BEGIN/END=====
       标记里，这是线上格式的一部分，剥壳之后才是 JSON（搜索）或 markdown（抓取）。
    3. 响应通常是 text/event-stream；一次调用只关心最后一条 data: 帧。
    4. Mcp-Session-Id 由 initialize 响应头给出，之后每次调用都要回带；会话会过期，
       过期时重建一次再失败切换。所有调用串行化：一个 session 就是一段会话，
       交错的 initialize 会互相踩。

    刻意不用：search_engine 没有日期过滤参数。带 time_range 的请求直接抛错让
    Balancer 换下一家，而不是花 5s 跑一次注定无法满足时间过滤的搜索。
    """
    name = "brightdata"
    DEFAULT_ENDPOINT = "https://mcp.brightdata.com/mcp"
    PROTOCOL_VERSION = "2025-06-18"
    CLIENT_INFO = {"name": "dsh-balanced-search", "version": "0.3.0"}

    # 服务端包装：安全提示 + =====UNTRUSTED_<32 位 hex>_BEGIN=====\n<真实内容>\n=====..._END=====
    _UNTRUSTED_RE = re.compile(
        r"=====UNTRUSTED_[0-9a-f]+_BEGIN=====\n([\s\S]*?)\n=====UNTRUSTED_[0-9a-f]+_END====="
    )

    def __init__(self, token: str, endpoint: Optional[str] = None):
        self._endpoint = endpoint or self.DEFAULT_ENDPOINT
        # token 放进 query string，所以显式编码；即使被拼进少数几条错误消息也不会
        # 因为 token 里的特殊字符把 URL 弄坏。
        sep = "&" if "?" in self._endpoint else "?"
        self._url = f"{self._endpoint}{sep}token={quote(token, safe='')}"
        self._session_id: Optional[str] = None
        self._next_id = 1
        # 一个 session 一段会话：并发调用会交错 initialize/notifications 通知，
        # 也拿不到稳定的 session 语义，所以统统串行。
        self._lock = threading.Lock()
        # 超时按能力分开（搜索 40s / 抓取 45s），每次请求显式传入覆盖 client 默认值。
        # 抓取预算刻意低于工具层 60s 预算：吃满整个预算就没机会故障切换。
        self._http = httpx.Client()

    # ---- MCP 传输层 ----

    def _headers(self) -> dict:
        headers = {
            "content-type": "application/json",
            # 两个都必须带：缺一个服务端直接 406；而且它即使客户端接受 JSON，
            # 也仍然用 SSE 回复。
            "accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["mcp-session-id"] = self._session_id
        return headers

    @staticmethod
    def _parse_reply(resp: httpx.Response) -> Optional[dict]:
        """从 SSE 或普通 JSON 响应里取出 JSON-RPC 回复；纯通知的 202 返回 None。"""
        text = resp.text
        if text.strip() == "":
            return None
        if "text/event-stream" in (resp.headers.get("content-type") or ""):
            last = None
            for line in text.split("\n"):
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "":
                    continue
                try:
                    last = json.loads(raw)
                except ValueError:
                    # 单帧坏掉就跳过；一条都解析不出来时下面的调用方会报错，
                    # 而不是拿半截回复继续跑。
                    continue
            return last
        try:
            return json.loads(text)
        except ValueError as e:
            raise ProviderError(f"brightdata 响应不是 JSON: {text[:200]}") from e

    def _rpc(self, payload: dict, timeout: httpx.Timeout) -> Optional[dict]:
        """一次 JSON-RPC 往返；session 从响应头滚动更新。"""
        try:
            resp = self._http.post(self._url, json=payload, headers=self._headers(), timeout=timeout)
        except httpx.HTTPError as e:
            raise ProviderError(f"brightdata 网络错误: {e}") from e
        session_id = resp.headers.get("mcp-session-id")
        if session_id:
            self._session_id = session_id
        if resp.status_code >= 400:
            # 4xx 里最关键的是 400/404/409（session 无效/不存在/冲突），交给
            # _call_tool 判断是否需要重建；错误体最多 200 字符，避免把整页塞进消息。
            raise ProviderError(f"brightdata HTTP {resp.status_code}: {resp.text[:200]}")
        return self._parse_reply(resp)

    def _send(self, method: str, params, timeout: httpx.Timeout) -> Optional[dict]:
        # 先取号再发送：请求失败时 id 也已经消耗掉，不会和之后的重试撞号。
        request_id = self._next_id
        self._next_id += 1
        reply = self._rpc(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
            timeout,
        )
        if reply and reply.get("error"):
            err = reply["error"]
            msg = err.get("message") if isinstance(err, dict) else err
            raise ProviderError(f"brightdata {method} 失败: {msg or 'unknown'}")
        return (reply or {}).get("result")

    def _initialize(self, timeout: httpx.Timeout) -> None:
        self._session_id = None
        self._send(
            "initialize",
            {
                "protocolVersion": self.PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": self.CLIENT_INFO,
            },
            timeout,
        )
        # 规范要求在 tools/call 之前发这条通知，服务端据此认定 session 可用（202 空 body）。
        # 它是通知（不带 id），个别网关会回一个 JSON-RPC error；这不该让整次调用失败。
        try:
            self._rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, timeout)
        except ProviderError:
            pass

    @staticmethod
    def _is_session_error(error: Exception) -> bool:
        """是否为会话过期/未知（可安全重试一次）。"""
        if not isinstance(error, ProviderError):
            return False
        msg = str(error)
        return re.search(r"HTTP (?:400|404|409|410)\b", msg) is not None or "session" in msg.lower()

    def _call_tool(self, name: str, args: dict, timeout: httpx.Timeout) -> str:
        """调用一个 MCP 工具，返回其 text 内容；session 过期时重建并重试一次。"""
        with self._lock:
            def run_once() -> str:
                if not self._session_id:
                    self._initialize(timeout)
                result = self._send("tools/call", {"name": name, "arguments": args}, timeout)
                if result and result.get("isError"):
                    raise ProviderError(
                        f"brightdata {name} 失败: {self._tool_text(result)[:200]}"
                    )
                return self._tool_text(result)

            try:
                return run_once()
            except Exception as e:
                if self._session_id and self._is_session_error(e):
                    self._session_id = None
                    return run_once()
                raise

    @staticmethod
    def _tool_text(result: Optional[dict]) -> str:
        """拼出 MCP 工具结果里的文本（这两个工具都只回一个 text part）。"""
        parts = (result or {}).get("content") or []
        return "\n".join(
            part["text"] for part in parts
            if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str)
        )

    @classmethod
    def _unwrap_untrusted(cls, text: str) -> str:
        """剥掉 Bright Data 的 untrusted-content 包装，只留真实内容。

        标记缺失时原样返回（错误路径或未来换了响应格式），让调用方在解析时
        如实失败，而不是悄悄漏掉安全提示或拿到半截内容。
        """
        match = cls._UNTRUSTED_RE.search(text)
        return match.group(1) if match else text

    # ---- 工具层 ----

    def search(self, query: str, max_results: int, time_range: Optional[str]) -> list[SearchResult]:
        if time_range:
            # 该工具没有日期过滤能力：与其发一次注定不符的请求，不如直接让位。
            raise ProviderError("brightdata 搜索不支持 time_range")
        text = self._call_tool(
            "search_engine", {"query": query, "engine": "google"}, BRIGHTDATA_SEARCH_TIMEOUT
        )
        payload = self._unwrap_untrusted(text)
        try:
            parsed = json.loads(payload)
        except ValueError as e:
            raise ProviderError(f"brightdata 搜索结果不是 JSON: {payload[:200]}") from e
        organic = parsed.get("organic") if isinstance(parsed, dict) else None
        results = []
        for item in organic if isinstance(organic, list) else []:
            results.append(
                SearchResult(
                    title=item.get("title") or "",
                    url=item.get("link") or "",
                    content=str(item.get("description") or "").strip(),
                    provider=self.name,
                )
            )
        return results

    def fetch(self, url: str, max_chars: Optional[int] = None, live: bool = False) -> FetchResult:
        # live 在这里天然成立：scrape_as_markdown 每次都走代理实时抓源站，没有缓存可绕，
        # 所以参数不用下发（也没有对应字段）——保留签名只是为了和其他 provider 一致。
        text = self._call_tool(
            "scrape_as_markdown", {"url": url}, BRIGHTDATA_FETCH_TIMEOUT
        )
        raw = self._unwrap_untrusted(text).strip()
        if raw == "":
            # 该工具在抓取失败时也可能返回 200 + 空标记正文（见实测），必须按失败处理。
            raise ProviderError("brightdata 抓取返回空正文")
        return FetchResult(
            # 工具只回 markdown，不带最终 URL 和页面状态；如实回填请求的 URL、状态码留 None。
            url=url,
            title="",
            content=raw[:max_chars] if max_chars else raw,
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
    # token 也可以按文档里的别名 BRIGHTDATA_API_KEY 提供；MCP 端点可覆盖，
    # 便于自建或换区域的部署。
    brightdata_token = env.get("BRIGHTDATA_API_TOKEN") or env.get("BRIGHTDATA_API_KEY")
    if brightdata_token:
        providers.append(BrightDataProvider(brightdata_token, env.get("BRIGHTDATA_MCP_URL")))
    if not providers:
        raise RuntimeError(
            "未配置任何搜索 API key（请设置 KEENABLE_API_KEY / EXA_API_KEY / TAVILY_API_KEY "
            "/ FIRECRAWL_API_KEY / BRIGHTDATA_API_TOKEN）"
        )
    return Balancer(providers)
