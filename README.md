# dsh-balanced-search

**English:** A balanced web search plugin / MCP server that round-robins across **Keenable (Keen Search) / Exa / Tavily / Firecrawl / AnySearch / TinyFish** — six independent search & fetch backends — and automatically fails over to the next provider. Returns normalized titles, links, and content summaries.

**中文：** 均衡搜索插件 / MCP 服务器：把 **Keenable（Keen Search）/ Exa / Tavily / Firecrawl / AnySearch / TinyFish** 六个搜索 / 抓取 API **轮流调用**（round-robin），某个服务失败时**自动切换下一个**，统一返回标题 / 链接 / 摘要。

This repository provides two forms / 本仓库同时提供两种形态：

1. **DeepSeek Harness native plugin (recommended) / dsh 原生插件（推荐）** — registers `balanced_search` / `balanced_fetch` as dsh tools **and** automatically takes over the built-in `web_search` / `web_fetch`, no Python required. / 既注册 `balanced_search` / `balanced_fetch` 两个 dsh 工具，**同时自动接管内置的 `web_search` / `web_fetch`**，无需 Python。
2. **Generic MCP server / 通用 MCP 服务器** — exposes `search` / `fetch` over stdio via `server.py` for any MCP client. / 通过 `server.py` 以 stdio 方式暴露 `search` / `fetch`，可供任意 MCP 客户端使用。

## Features / 功能

- Search the web and return titles, links, and content summaries. / 搜索网页，返回标题、链接和内容摘要。
- Fetch a URL and return clean markdown text. / 抓取指定 URL 的网页正文，返回 clean markdown。
- Round-robin across six providers — all ordinary REST APIs — with automatic failover. / 六个服务（均为 REST API）轮流调用，单个服务失败时自动切换下一个。
- Configure API keys via environment variables; providers without a key are skipped. / 通过环境变量配置 API key；未配置的服务不会启用。
- **Takes over the built-in `web_search` / `web_fetch` automatically** — the bundle pins dsh's `web` row to this plugin's `balanced` provider, so no manual profile edit is needed. / **自动接管内置的 `web_search` / `web_fetch`**：bundle 层把 dsh 的 `web` 行钉到本插件的 `balanced` provider，**无需手工改任何配置**。
- **Fetch happens server-side, at the vendor** — so it also works where the shipped local `http` fetch provider cannot. See [Configuration Notes](#configuration-notes--配置说明). / **抓取在厂商服务端完成**，因此在 dsh 自带本地抓取 provider 无法工作的环境下依然可用，见[配置说明](#configuration-notes--配置说明)。

## Environment Variables / 环境变量

Configure at least one search provider API key / 至少配置一个搜索服务的 API key：

```bash
KEENABLE_API_KEY=...
EXA_API_KEY=...
TAVILY_API_KEY=...
FIRECRAWL_API_KEY=...
ANYSEARCH_API_KEY=...
TINYFISH_API_KEY=...
```

> 👉 **Where to register and get each key (all six) — sign-up links, where the key lives in each dashboard, free quotas, and what one call costs: [`API_KEYS.md`](API_KEYS.md).**
> **六家的注册入口、key 在各家后台的哪个页面、免费额度、以及单次调用消耗，见 [`API_KEYS.md`](API_KEYS.md)。**

| Provider | Sign up / 注册 | Env var | Free tier / 免费额度 | Docs / 文档 |
|---|---|---|---|---|
| Keenable | <https://app.keenable.ai/login> | `KEENABLE_API_KEY` | 100,000 requests / month | <https://docs.keenable.ai> |
| Exa | <https://dashboard.exa.ai/onboarding-guest> | `EXA_API_KEY` | $20 on sign-up + $10 / month | <https://docs.exa.ai> |
| Tavily | <https://app.tavily.com> | `TAVILY_API_KEY` | 1,000 credits / month | <https://docs.tavily.com> |
| Firecrawl | <https://www.firecrawl.dev/signin> | `FIRECRAWL_API_KEY` | 1,000 credits / month (≈500 searches or 1,000 page fetches; 10 req/min) / 1,000 credits / 月（≈500 次搜索或 1,000 页抓取，10 req/min） | <https://docs.firecrawl.dev> |
| AnySearch | <https://www.anysearch.com/login> | `ANYSEARCH_API_KEY` | 1,000 requests / day (search + extract share it), 20 QPS per key; hard cap of 10 results and no recency filter / 1,000 请求/天（search 与 extract 共用），每 key 20 QPS；结果硬上限 10 条、不支持时间过滤 | <https://anysearch.com/docs/api-endpoints> |
| TinyFish | <https://agent.tinyfish.ai/api-keys> | `TINYFISH_API_KEY` | Search & Fetch are **$0** — 12,000 searches / day (500 / hour, 30 / min) plus 1,000 fetched URLs / day / 搜索与抓取均为 **$0**——12,000 次搜索/天（500/小时、30/分），抓取 1,000 个 URL/天 | <https://docs.tinyfish.ai> |

Free-tier figures are as of 2026-10-22 and change often — always check the vendor's pricing page. / 以上免费额度为 2026-10-22 的快照，各家随时可能调整，请以官方定价页为准。

The dsh native plugin reads process environment variables directly. The Python MCP server also loads a `.env` file in the same directory. / dsh 原生插件直接读取进程环境变量；Python MCP 服务器还会自动读取同目录下的 `.env` 文件。

## Directory Structure / 目录结构

| File / 文件 | Description / 说明 |
|---|---|
| `index.js` | dsh native plugin entry; registers `balanced_search` / `balanced_fetch` and the `ctx.web` provider `balanced` / dsh 原生插件入口：注册两个工具，并向 `ctx.web` 注册 `balanced` provider |
| `cordis.patch.yml` | dsh bundle config layer; inserts the plugin and pins the `web` row to the `balanced` provider / dsh bundle 配置层：插入插件，并把 `web` 行钉到 `balanced` provider |
| `package.json` | dsh bundle manifest / dsh bundle 声明 |
| `server.py` | Generic MCP server (stdio); exposes `search` / `fetch` / 通用 MCP server |
| `providers.py` | Python providers + round-robin / failover / Python 版 API 客户端与轮换 |
| `scripts/probe.mjs` | Probe a single vendor in isolation through the real plugin code / 通过真实插件代码单独探测试某一家厂商 |
| `requirements.txt` | Python MCP server dependencies / Python MCP 服务器依赖 |
| `.env.example` | Template for all six API keys (copy to `.env`) / 六个 API key 的配置模板（复制为 `.env`） |
| `API_KEYS.md` | Where to register the six APIs and get keys / 六个 API 的注册与 key 领取说明 |
| `.gitignore` | Excludes `.env`, virtualenvs, caches / 排除本地敏感与缓存文件 |

## Install as a dsh Plugin / 安装为 dsh 插件

Requirements / 要求：DeepSeek Harness (dsh) installed, Node.js ≥ 20.

```sh
dsh plugin --profile web add github:tianmingwan/dsh-balanced-search
```

After restarting `dsh --profile web` / 重启 `dsh --profile web` 之后：

- Two extra tools appear / 新增两个工具：`balanced_search`、`balanced_fetch`
- The built-in `web_search` / `web_fetch` are **taken over automatically** — no manual profile edit / 内置的 `web_search` / `web_fetch` **被自动接管**，无需手工修改 profile 配置

No Python dependencies required / 无需安装 Python 依赖。

### How the takeover works / 接管是怎么实现的

`package.json` declares `dsh.bundle.patch`, which makes this package a **bundle layer**. Installing it composes `cordis.patch.yml` on top of the bundles listed before it — notably `@deepseek-ai/dsh-base`, which mounts the `web` row — and that layer pins the row's providers:

```yaml
- id: web
  name: '@deepseek-ai/dsh-web'
  config:
    searchProvider: balanced
    fetchProvider: balanced
```

`index.js` registers a single provider with id `balanced` into **both** the seam's search and fetch registries, so the pin covers both capabilities. (A patch replaces the targeted row's whole `config` rather than merging, which is why both fields are restated.)

### Key requirement / key 要求

The takeover needs at least one of `KEENABLE_API_KEY` / `EXA_API_KEY` / `TAVILY_API_KEY` / `FIRECRAWL_API_KEY` / `ANYSEARCH_API_KEY` / `TINYFISH_API_KEY`. With none set, the `balanced` provider reports itself unavailable and the built-in tools fail with `WEB_PROVIDER_CONFIGURED_UNAVAILABLE` naming `balanced`. / 接管需要至少配置一个 key（六种任选其一）；一个都没有时，`balanced` provider 会报告不可用，内置工具会以 `WEB_PROVIDER_CONFIGURED_UNAVAILABLE` 失败。

### Opting out / 取消接管

A user's own `~/.dsh/profiles/<profile>/cordis.patch.yml` is applied *after* every bundle layer, so the pin can be overridden or removed there — restoring dsh's shipped `deepseek-official` search / `http` fetch while keeping the two extra tools. / 用户自己的 `cordis.patch.yml` 在**所有** bundle 层之后应用，因此可以在那里覆盖或删除这两行，恢复 dsh 自带的 provider，同时保留两个额外工具。

## Use as a Generic MCP Server / 作为通用 MCP 服务器使用

### Install / 安装

```bash
python -m venv .venv
# Windows
.venv\Scripts\python.exe -m pip install -r requirements.txt
# Linux / macOS
.venv/bin/python -m pip install -r requirements.txt
```

### Run / 运行

```bash
# stdio mode for MCP clients / stdio 模式，供 MCP 客户端连接
python server.py
# or use the virtualenv Python / 或使用虚拟环境中的 Python
.venv\Scripts\python.exe server.py   # Windows
.venv/bin/python server.py           # Linux / macOS
```

### MCP Client Example / MCP 客户端接入示例

```json
{
  "mcpServers": {
    "balanced-search": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["/absolute/path/to/server.py"],
      "env": {
        "KEENABLE_API_KEY": "...",
        "EXA_API_KEY": "...",
        "TAVILY_API_KEY": "...",
        "FIRECRAWL_API_KEY": "...",
        "ANYSEARCH_API_KEY": "...",
        "TINYFISH_API_KEY": "..."
      }
    }
  }
}
```

## Tool Usage / 工具用法

### dsh Native Tools / dsh 原生工具

- `balanced_search` — parameters / 参数：`query` / `max_results` / `time_range`
- `balanced_fetch` — parameters / 参数：`url` / `max_chars` / `live`

### Built-in Tools after Takeover / 接管后的内置工具

These keep dsh's own schemas — this plugin supplies the retrieval backend only, so their parameters are fixed by dsh, not by this plugin. / 它们沿用 dsh 自己的工具签名：本插件只提供检索后端，参数由 dsh 决定。

| | `web_search` | `balanced_search` |
|---|---|---|
| Query / 查询 | `queries: string[]` (up to 4 per call / 一次最多 4 条) | `query: string` |
| Result count / 条数 | deployment config (default 8) / 部署配置，默认 8 | `max_results` 1–20 |
| Time range / 时间范围 | ✗ (deferred by the seam / seam 明确暂不支持) | `time_range` |

- `web_fetch` — parameter / 参数：`url` only / 仅 `url`。No `max_chars` / `live`; timeout and output cap are deployment policy / 没有这两个参数，超时与输出上限属部署策略。
- `balanced_fetch` — keeps / 保留 `max_chars` / `live`.

The two surfaces complement each other / 两套接口互补：use `web_search` / `web_fetch` for dsh-native naming and multi-query, and `balanced_search` / `balanced_fetch` when you need `time_range`, `live`, or `max_chars`.

### MCP Tools / MCP 工具

- `search` — parameters / 参数：`query` / `max_results` / `time_range`
- `fetch` — parameters / 参数：`url` / `max_chars` / `live`

### Parameter Reference / 参数说明

- `query` (required / 必填): Search keyword or natural language question / 搜索关键词或自然语言问题
- `max_results`: 1–20, default 8 / 1–20，默认 8
- `time_range`: `day` / `week` / `month` / `year` (native for Tavily; Exa maps to `startPublishedDate`; Keenable maps to `published_after`; Firecrawl maps to a relative recency window (`tbs`); TinyFish maps to `recency_minutes`; AnySearch has **no** recency parameter at all, so it is skipped for time-filtered searches whenever a capable vendor is configured) / （Tavily 原生；Exa 映射为 `startPublishedDate`；Keenable 映射为 `published_after`；Firecrawl 映射为回溯时间窗口（`tbs`）；TinyFish 映射为 `recency_minutes`；AnySearch **完全没有** recency 参数，因此只要池子里有支持回溯的厂商，带时间过滤的搜索就不会发给它）
- `max_chars`: Maximum characters to return, default 30000, max 50000. AnySearch and TinyFish have no length parameter, so the cap is applied client-side (AnySearch's server already caps near 50k) / 抓取内容最大字符数，默认 30000，上限 50000。AnySearch 与 TinyFish 没有长度参数，截断在客户端完成（AnySearch 服务端正文本来就以约 50k 封顶）
- `live`: Fetch live from the source (bypass index/cache), default `false`. Honoured by Keenable, Exa, Firecrawl (`maxAge: 0` forces an origin re-scrape) and TinyFish (`ttl: 0`); Tavily's extract API and AnySearch's extract have no equivalent control. / 是否实时从源站抓取（绕过索引/缓存），默认 `false`。Keenable、Exa、Firecrawl（Firecrawl 传 `maxAge: 0` 强制回源）与 TinyFish（`ttl: 0`）支持；Tavily 的 extract 与 AnySearch 的 extract 没有对应开关。

#### Provider differences / 各家能力差异

| Provider | Search / 搜索 | Fetch / 抓取 | Notable limits / 需要注意 |
|---|---|---|---|
| Keenable | REST | REST | supports `time_range` and `live` / 支持时间范围与实时抓取 |
| Exa | REST | REST | supports `time_range` (`startPublishedDate`) and `live` / 支持时间范围与实时抓取 |
| Tavily | REST | REST | native `time_range`; no live control / 原生时间范围；无实时开关 |
| Firecrawl | REST | REST | both capabilities supported; fetch serves a cached copy up to 2 days old unless `live=true` (then `maxAge: 0`, slower and more failure-prone); free tier is capped at 10 req/min, so it is one pool member rather than the main engine; the only backend that reports the origin page's HTTP status (see below) / 搜索与抓取都支持；抓取默认走最长 2 天的缓存，`live=true` 时传 `maxAge: 0` 回源（更慢、更容易失败）；免费档硬限 10 req/min，因此它是池中的一员而非主力；也是唯一会返回原页面 HTTP 状态码的后端（见下） |
| AnySearch | REST | REST (`extract`) | hard caps `max_results` at 10 (silently truncates more) and has **no recency parameter**, so `time_range` searches skip it; `extract` takes exactly `{"url": …}`, returns ~50k chars of Markdown; search and `extract` share 1,000 requests/day / `max_results` 硬上限 10（超过静默截断）且**没有 recency 参数**，带 `time_range` 的搜索会跳过它；`extract` 请求体严格只有 `{"url": …}`，返回约 50k 字符的 Markdown；search 与 `extract` 共用每日 1,000 次请求 |
| TinyFish | REST (GET) | REST | auth uses `X-API-Key` (not Bearer); no `max_results`, exactly 10 results per page, so `max_results > 10` costs a second `page=1` request merged by URL; `recency_minutes` supports all four time ranges; both search and fetch are free / 鉴权用 `X-API-Key`（不是 Bearer）；没有 `max_results` 参数，每页固定 10 条，`max_results > 10` 时要再发一次 `page=1` 并按 URL 去重合并；`recency_minutes` 支持全部四种时间范围；搜索与抓取都免费 |

On the fetch side, Firecrawl is the only backend that reports the origin page's own status (it is a scrape, not an index extraction); the other five extract server-side and never see it. / 抓取侧只有 Firecrawl 会返回原页面状态码（它是真实抓取而非索引抽取）；其余五家都是服务端抽取、看不到原页面状态。

Search response / 搜索返回 JSON：

```json
{
  "provider": "keenable|exa|tavily|firecrawl|anysearch|tinyfish",
  "count": 1,
  "results": [
    {"title": "...", "url": "...", "content": "...", "published_at": "...", "score": 0.5}
  ]
}
```

Fetch response / 抓取返回 JSON：

```json
{
  "provider": "keenable|exa|tavily|firecrawl|anysearch|tinyfish",
  "result": {"url": "...", "title": "...", "content": "..."}
}
```

The `result` of a Firecrawl fetch may also carry `statusCode` — the origin page's own HTTP status. / Firecrawl 的抓取结果还可能带 `statusCode`，即原页面的 HTTP 状态码。

## Free-tier parameter design / 免费档参数设计

Every default in the adapters is chosen so the pool stays inside the free plans and never spends quota on a parameter that does not change the answer. / 适配层的每个默认参数都以"不超免费额度、不为不改变结果的东西付费"为准。

| Vendor | Cost-safe choice / 成本安全的选择 | Why / 原因 |
|---|---|---|
| Keenable | one request per search or fetch, `realtime` mode, no extra options | a flat 100,000 requests/month: one call is one unit / 固定 100,000 请求/月，一次调用就是一个单位 |
| Exa | `type: auto`, 3,000-char text budget per result | the cheapest search type, and card snippets do not need whole pages / 最便宜的搜索类型；卡片摘要不需要整页正文 |
| Tavily | `advanced` depth kept on purpose | 2 credits/search buys materially better research results, and the cost is spread over six quotas / 2 credits/次换来更好的研究结果，且成本摊到六份额度上 |
| Firecrawl | no `scrapeOptions` on `/search`, `sources: ['web']`, caller's exact result count as `limit` | scraping each result would cost 1 credit per result on top of 2 credits per 10 results / 逐条抓取会在"2 credits / 10 条"之外再按条计费（每条 1 credit） |
| AnySearch | `max_results` clamped to 10 and **kept out of `time_range` searches** | the server silently truncates anything above 10, and there is no recency field at all — returning unfiltered results for a filtered request would silently break the caller's contract / 服务端对超过 10 条静默截断；而且根本没有 recency 字段——用未过滤结果冒充过滤结果会悄悄破坏调用方契约 |
| TinyFish | normally one request; a second `page=1` only when `max_results > 10`, merged by URL; `live` → `ttl: 0` | exactly 10 results per page with no `max_results` parameter, and the free plan is $0, so the extra page costs quota rather than money / 每页固定 10 条且没有 `max_results` 参数；免费档 $0，多翻一页占的是额度而不是钱 |

Two accounting notes / 两个额度记账要点：

- AnySearch's 1,000 requests/day is shared by search **and** extract, so every fetch spends the same budget as a search; that is another reason the vendor is one pool member rather than the workhorse. / AnySearch 的每日 1,000 次请求由 search **与** extract 共用，所以每次抓取消耗的额度和搜索一样——这也是它只做池中一员而非主力的原因。
- TinyFish's search and fetch allowances are counted separately (12,000 searches/day vs 1,000 URLs/day), and neither draws on a wallet balance. / TinyFish 的搜索与抓取额度分开计（12,000 次搜索/天 与 1,000 个 URL/天），两者都不扣 wallet 余额。

Why a cooldown exists / 为什么需要 cooldown：a spent daily/monthly quota or a revoked key fails the same way on every rotation, so retrying it every Nth call only adds latency. `auth` failures park the vendor for 30 minutes, `quota` for 20 minutes (a daily plan may reset sooner, and the user may top up mid-session), and `rate` for 30 seconds. A cooldown never empties the pool — when everything is cooling down, all vendors are tried again. / 额度用尽或被吊销的 key 每次轮换都会以同样方式失败，每 N 次调用重试一次只会增加延迟。`auth` 失败停放 30 分钟、`quota` 停放 20 分钟（日额度可能更早重置，用户也可能中途充值）、`rate` 只停 30 秒。cooldown 不会让池子变空：全部在冷却时仍会重试所有厂商。

## Configuration Notes / 配置说明

- Change keys / 换 key：dsh plugin uses environment variables; MCP server uses `.env` or client `env` injection.
- Failover strategy / 轮换策略：`Balancer` (currently round-robin + failover; can be changed to weighted or health-aware). Search and fetch advance independent cursors, so a fetch does not shift the next search's starting provider. A failed vendor can also be parked briefly by kind — `auth` 30 min, `quota` 20 min, `rate` 30 s — so a dry or revoked key is not retried on every rotation; if every vendor is cooling down they are all tried anyway, so a cooldown never turns into "no provider configured". / 搜索与抓取各自独立推进游标，一次抓取不会改变下次搜索的起点。失败的厂商还会按类别被短暂停放——`auth` 30 分钟、`quota` 20 分钟、`rate` 30 秒——避免对着已耗尽或已吊销的 key 每次轮换都重试；全部都在冷却时会照常重试全池，所以 cooldown 不会变成"没有可用 provider"。
- `time_range` routing / 时间过滤路由：providers that cannot filter by recency (`supports_time_range = False`, currently AnySearch) are left out of a time-filtered search as long as at least one capable vendor is configured — returning unfiltered results for a filtered request would silently break the caller's contract. The whole pool is used only when nobody can honour the filter. / 不支持时间过滤的厂商（`supports_time_range = False`，目前是 AnySearch）在池子里还有能过滤的厂商时不会参与带 `time_range` 的搜索——用未过滤结果冒充过滤结果会悄悄破坏调用方的契约；只有当全池都不支持时才会退回整个池子。
- Add a provider / 新增服务：there are six today. JS: add a Provider class in `index.js` and register it in `buildBalancer()`; Python: add a `SearchProvider` subclass in `providers.py` and register it in `build_balancer()`. Set `supports_time_range = False` on the class (or `supportsTimeRange = false` in JS) when the vendor has no recency parameter. Providers without a key are skipped, so adding one never changes behaviour for existing users. / 目前有六个。JS 侧在 `index.js` 里加一个 Provider 类并注册到 `buildBalancer()`；Python 侧在 `providers.py` 里加一个 `SearchProvider` 子类并注册到 `build_balancer()`。厂商没有回溯参数时，在类上标 `supports_time_range = False`（JS 为 `supportsTimeRange = false`）。没有 key 的 provider 会被跳过，因此新增一家不会影响既有用户。
- Round-robin cost / 轮询成本：calls are spread across all six quotas, so no single free tier is the bottleneck. / 调用现在摊到六个免费额度上，不再压在单一额度上。
- Server-side fetch / 服务端抓取：the fetch call is made by Keenable / Exa / Tavily / Firecrawl / AnySearch / TinyFish, so the page is retrieved from *their* network, not yours. This is why fetching still works when the local machine's DNS maps hosts into private or benchmark ranges — for example a Clash / mihomo TUN in `fake-ip` mode answering with `198.18.0.0/15` addresses — where dsh's shipped local `http` fetch provider refuses with `resolves to a non-public IP address`. / 抓取由 Keenable / Exa / Tavily / Firecrawl / AnySearch / TinyFish 发起，网页是在**它们的网络**里取的。因此当本机 DNS 把域名解析到私有或保留网段（例如 Clash / mihomo TUN 的 `fake-ip` 模式返回 `198.18.0.0/15` 地址）时，抓取依然可用；而 dsh 自带的本地 `http` provider 会以 `resolves to a non-public IP address` 拒绝。
- Reporting a fetch status / 关于抓取状态码：the seam's `WebFetchResult` requires a `statusCode`. Firecrawl reports the origin page's own status; the other five vendors extract server-side without exposing it, so the seam reports `200` for a successful extraction and infers `truncated` from whether the body reached its cap. The plugin's own tool keeps the field out of its JSON instead, and its card falls back to `HTTP 200` for the same reason the seam does. / seam 要求返回 `statusCode`。Firecrawl 会返回原页面状态码；其余五家都是服务端抽取、不暴露原页面状态，因此 seam 侧抽取成功即记为 `200`，`truncated` 按正文是否触顶推断。插件自己的工具则是在 JSON 里省略该字段，卡片出于同样理由回退显示 `HTTP 200`。
- Timeout budgets / 超时预算：每个 provider 有统一的单次请求预算（JS 插件为 20 s 搜索 / 45 s 抓取；Python MCP 版沿用统一的 30 s 客户端超时）；六家都是 REST 服务，Firecrawl 也用这个通用预算、没有专属值。插件自己的 `balanced_search` / `balanced_fetch` 工具预算是 60 s，所以一次慢调用被放弃后仍有时间切到下一家 —— **但接管的 `web_search` / `web_fetch` 用的是 dsh 自己的预算**：本 profile 里 `searchTimeoutMs: 60000`，而 `fetchTimeoutMs` 未配置、取 dsh 默认的 30 s。想在接管路径上保留同样的 failover 余量，就在自己的 profile `cordis.patch.yml` 里给 `tool-web` 行补 `fetchTimeoutMs`（补丁会整行替换 `config`，所以 `fetch: true` 与 `searchTimeoutMs` 要一起写上）。 / per-provider budgets are a uniform 20 s search / 45 s fetch in the JS plugin (the Python MCP server keeps a single 30 s client timeout); all six backends are REST services and Firecrawl uses that generic budget with no dedicated value. The plugin's own tools budget 60 s, so a slow vendor is abandoned with time left to try the next one; the **taken-over `web_search` / `web_fetch` use dsh's own budgets instead** — this profile sets `searchTimeoutMs: 60000` and leaves `fetchTimeoutMs` at dsh's 30 s default. To keep the same failover headroom on the takeover path, add `fetchTimeoutMs` to the `tool-web` row in your profile's `cordis.patch.yml` (a patch replaces the whole `config`, so restate `fetch: true` and `searchTimeoutMs` too).

## License

MIT
