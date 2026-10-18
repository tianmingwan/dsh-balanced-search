# Where to get the five API keys (at least one is required) / 五个 API key 的注册领取说明（至少配置其中一个）

**English:** This plugin can use up to five independent search backends. It needs **at least one** of them: providers whose key is missing are skipped entirely, and with none configured the tools fail with a `未配置任何搜索 API key` message. Each provider below is a separate company with its own account, dashboard, and quota. Four of them are ordinary REST APIs; Bright Data is a hosted MCP server, which is why its section reads differently.

**中文：** 本插件最多可接五个互相独立的搜索后端，**至少需要配置其中一个**：没配 key 的服务会被直接跳过；一个都没配时，工具会以 `未配置任何搜索 API key` 失败。下面五家是各自独立的公司，账号、后台、额度互不相通。其中四家是普通 REST API，Bright Data 是托管的 MCP 服务，所以它那一节的接法和别家不一样。

Account sign-up links, key pages, quotas, and pricing all change over time — the official pages linked below are authoritative; the numbers here are a snapshot taken on **2026-10-18** and are only meant for a quick orientation. / 注册入口、key 页面、额度与价格都会变动，一切以本文链接的官方页面为准；下面的数字是 **2026-10-18** 的快照，只供快速判断。

## Summary / 总览

| Provider | Sign up / 注册 | Where to create the key / key 在哪创建 | Environment variable / 环境变量 | Key shape / key 形态 | Free allowance / 免费额度 | Official docs / 官方文档 |
|---|---|---|---|---|---|---|
| **Keenable** (Keen Search) | <https://app.keenable.ai/login> | Console: <https://app.keenable.ai/console> | `KEENABLE_API_KEY` | `keen_…` | **100,000 requests / month**, resets monthly | <https://docs.keenable.ai> |
| **Exa** | <https://dashboard.exa.ai/onboarding-guest> | Dashboard → **API Keys** tab | `EXA_API_KEY` | opaque string | **$20 on sign-up + $10 every month**, no payment method | <https://exa.ai/pricing> |
| **Tavily** | <https://app.tavily.com> | Dashboard → **API Keys** section | `TAVILY_API_KEY` | `tvly-…` (dev keys may look like `tvly-dev-…`) | **1,000 credits / month**, resets on the 1st | <https://docs.tavily.com/documentation/quickstart> |
| **Firecrawl** | <https://www.firecrawl.dev/signin> (or **Sign Up** on <https://www.firecrawl.dev/pricing>) | <https://www.firecrawl.dev/app/api-keys> | `FIRECRAWL_API_KEY` | `fc-…` | **1,000 credits / month**, refreshed monthly; search 2 credits / 10 results, scrape 1 credit / page; 10 req/min on the free plan | <https://docs.firecrawl.dev/features/search> |
| **Bright Data MCP** | <https://brightdata.com> (**Start free trial**, or <https://brightdata.com/cp/start>) | Control panel: <https://brightdata.com/cp/setting/users> | `BRIGHTDATA_API_TOKEN` | UUID, e.g. `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` | **5,000 requests / month**, renews on the 1st | <https://brightdata.com/pricing/mcp-server> |

## 1. Keenable (Keen Search)

**English**
1. Open <https://app.keenable.ai/login> and sign in (create an account if you do not have one).
2. Go to the **console** at <https://app.keenable.ai/console> and create an API key. Keys are scoped to your workspace, do not expire on their own, and can be rotated at any time.
3. Copy it (it starts with `keen_`) into `KEENABLE_API_KEY`.

The plugin sends it in the `X-API-Key` header. Keenable also accepts `Authorization: Bearer keen_…`; if both headers are present, `X-API-Key` wins.

Keenable's own console page points at a CLI path instead of manual key copying: `keenable login` runs a device-code flow that handles account creation, authentication and API key generation, and `keenable configure-mcp --all` then wires the key into supported MCP clients. That is convenient for MCP clients, but this plugin reads the key from the environment — so if you use the CLI, copy the resulting key into `KEENABLE_API_KEY` (or export it from the same shell that starts dsh).

**中文**
1. 打开 <https://app.keenable.ai/login> 登录（没有账号就注册）。
2. 到 **console** <https://app.keenable.ai/console> 创建 API key。key 绑定你的 workspace，不会自动过期，可随时轮换。
3. 复制（形如 `keen_…`）填入 `KEENABLE_API_KEY`。

插件通过 `X-API-Key` 头传递。Keenable 也接受 `Authorization: Bearer keen_…`；两个头同时存在时以 `X-API-Key` 为准。

Keenable 的 console 页推荐的是走 CLI 而不是手工复制 key：`keenable login` 用设备码流程完成账号创建、认证和 key 生成，再用 `keenable configure-mcp --all` 把 key 配进支持的 MCP 客户端。这对 MCP 客户端很方便，但**本插件是从环境变量读 key** 的——如果你用了 CLI，请把生成的 key 填进 `KEENABLE_API_KEY`（或在启动 dsh 的那个 shell 里 export）。

**Notes worth knowing / 值得知道的几点**

- The free allowance is **100,000 requests a month for authenticated usage**, and it recurs — it is a budget, not a one-off trial. Search and fetch cost 1 credit each (SKUs `search.realtime` and `fetch`). / 免费额度是**认证用量的 100,000 请求/月**，且每月重置——是预算而非一次性试用。search 与 fetch 各 1 credit（SKU：`search.realtime` / `fetch`）。
- This plugin always searches in **`realtime` mode**, which requires an authenticated key. Keenable's keyless `/public` endpoints (no key, but a shared 1,000 requests/hour per-IP pool and a required `X-Keenable-Title` header) are **not** used by this plugin — with no key it simply skips Keenable. / 本插件的搜索固定用 **`realtime` 模式**，需要认证 key。Keenable 的无 key `/public` 端点（共享 1,000 请求/小时、按 IP 限流，且必须带 `X-Keenable-Title` 头）**不被本插件使用**——没配 key 时直接跳过 Keenable。
- Authenticated rate limit: **10 requests/second per organization**. Enforced per organization, not per key. / 认证态限流：**每组织 10 请求/秒**，按组织而非按 key 计。
- Error codes to expect: `400` malformed key, `401` missing/invalid key, `402` no credits left, `403` key disabled or revoked, `429` rate limited. / 常见错误码：`400` key 格式错、`401` key 缺失/无效、`402` 额度用尽、`403` key 被禁用或吊销、`429` 触发限流。

## 2. Exa

**English**
1. Sign up at <https://dashboard.exa.ai/onboarding-guest> (this is the link on Exa's own pricing page under "Start building for free"). Email sign-up works; no payment method is required for the free tier.
2. In the dashboard, open the **API Keys** tab and generate a new key. Give it a descriptive name so you can revoke it later without breaking everything else.
3. Copy it into `EXA_API_KEY`.

The plugin sends it in the `x-api-key` header.

**中文**
1. 在 <https://dashboard.exa.ai/onboarding-guest> 注册（这是 Exa 官方定价页 "Start building for free" 的链接）。邮箱注册即可，免费档不需要绑卡。
2. 在 dashboard 里打开 **API Keys** 页，生成新 key。建议取个有意义的名字，方便以后单独吊销而不影响其它用途。
3. 复制填入 `EXA_API_KEY`。

插件通过 `x-api-key` 头传递。

**Notes worth knowing / 值得知道的几点**

- Free tier: **$20 in credits on sign-up plus $10 every month**, with no payment method required. Past that it is pay-as-you-go: Search **$7 per 1,000 requests**, Contents **$1 per 1,000 pages**. / 免费档：**注册送 $20，之后每月 $10**，无需绑卡。超出后按量计费：Search **$7/1,000 次**，Contents **$1/1,000 页**。
- The free tier allows 10 search QPS. / 免费档搜索 10 QPS。
- This plugin maps the seam's result cap onto Exa's `numResults`, and requests up to 3,000 characters of text per result. / 本插件把 seam 的条数上限映射到 Exa 的 `numResults`，并为每条结果请求最多 3,000 字符正文。

## 3. Tavily

**English**
1. Sign in or create an account at the Tavily platform: <https://app.tavily.com>. No credit card is required.
2. Your API keys are on the dashboard. Use the **+** button next to the API keys section to create an additional key if you want separate keys per use case.
3. When creating a key you can set a **Key Name**, a **Key Type** (Development = up to 100 requests/min, Production = up to 1,000 requests/min), and a **Monthly Limit** to cap credit spend.
4. Copy the key (it starts with `tvly-`) into `TAVILY_API_KEY`.

The plugin sends it as `Authorization: Bearer tvly-…`.

**中文**
1. 在 Tavily 平台 <https://app.tavily.com> 登录或注册，无需信用卡。
2. API key 就在 dashboard 上。想给不同用途分开发 key，点 API keys 区域旁的 **+** 按钮新建。
3. 创建时可设置 **Key Name**、**Key Type**（Development 上限 100 请求/分，Production 上限 1,000 请求/分）以及 **Monthly Limit**（封顶 credit 消耗）。
4. 复制（形如 `tvly-…`）填入 `TAVILY_API_KEY`。

插件以 `Authorization: Bearer tvly-…` 发送。

**Notes worth knowing / 值得知道的几点**

- Free tier: **1,000 API credits per month**, resetting on the **1st of each month** regardless of your billing date. Running out stops requests until the reset. / 免费档：**每月 1,000 credits**，在**每月 1 日**重置（与账单日无关）。用尽后请求会停到下次重置。
- **Credit cost depends on depth, and this plugin always uses `advanced`.** Search with `advanced` depth costs **2 credits per request**, so the free 1,000 credits are roughly **500 searches/month**. Extract with `advanced` depth costs **2 credits per 5 successful extractions**, so a single-URL fetch is about 0.4 credits. / **消耗取决于深度，而本插件固定用 `advanced`。** `advanced` 搜索**每次 2 credits**，所以免费 1,000 credits 约合**每月 500 次搜索**；`advanced` 抽取为**每 5 次成功抽取 2 credits**，即单 URL 抓取约 0.4 credits。
- You are not charged for failed URL extractions. / 抽取失败不计费。

## 4. Firecrawl

**English**
1. Sign up at <https://www.firecrawl.dev/signin> — the **Sign Up** button on <https://www.firecrawl.dev/pricing> leads to the same page. No credit card is required for the free tier.
2. Open the API keys page at <https://www.firecrawl.dev/app/api-keys> and create a key. It starts with `fc-`.
3. Copy it into `FIRECRAWL_API_KEY`.

The plugin sends it as `Authorization: Bearer fc-…`. One key covers two REST endpoints: `POST https://api.firecrawl.dev/v2/search` for search, and `POST https://api.firecrawl.dev/v2/scrape` for fetching a URL as markdown.

**中文**
1. 在 <https://www.firecrawl.dev/signin> 注册（定价页 <https://www.firecrawl.dev/pricing> 上的 **Sign Up** 按钮指向同一页面）。免费档不用信用卡。
2. 打开 API keys 页面 <https://www.firecrawl.dev/app/api-keys> 创建 key，形如 `fc-…`。
3. 复制填入 `FIRECRAWL_API_KEY`。

插件以 `Authorization: Bearer fc-…` 发送。同一个 key 覆盖两个 REST 端点：搜索用 `POST https://api.firecrawl.dev/v2/search`，抓取用 `POST https://api.firecrawl.dev/v2/scrape`（返回 markdown）。

**Notes worth knowing / 值得知道的几点**

- Free tier: **1,000 credits every month, refreshed monthly**, no credit card. A search bills **2 credits per 10 results (rounded up)** and a scrape bills **1 credit per page**, so the free allowance is roughly **500 searches or 1,000 page fetches a month** — search and scrape draw on the same balance. / 免费档：**每月 1,000 credits、每月刷新**，免信用卡。搜索按 **10 条结果 2 credits（向上取整）**计费，抓取**每页 1 credit**，所以免费额度约合**每月 500 次搜索或 1,000 页抓取**——搜索和抓取共用同一份额度。
- The free plan caps `/search`, `/scrape` and `/map` at **10 requests/min each** and allows only **2 concurrent browsers**, which is the real bottleneck here: this plugin treats Firecrawl as one member of the rotation, not the workhorse. / 免费档把 `/search`、`/scrape`、`/map` 各自限到 **10 请求/分**，并发浏览器只有 **2 个**，这是真正的瓶颈：本插件把 Firecrawl 当成轮询池的一员，而不是主力。
- The plugin requests `sources: ['web']` only and keeps the cheap `description` snippet — it never turns a search into per-result scrapes, which would cost 1 credit per result. It also passes `max_results` straight through as `limit`, so asking for more than 10 results costs another 2 credits (12 results = 4 credits). / 本插件只请求 `sources: ['web']`，并用便宜的 `description` 摘要，不会把一次搜索变成逐条抓取（那样每条结果要多花 1 credit）。它还把 `max_results` 原样当作 `limit` 传入，所以请求超过 10 条会再多花 2 credits（12 条 = 4 credits）。
- **Caching:** Firecrawl may serve a copy up to **2 days old** by default (`maxAge` defaults to `172800000` ms). The plugin's fetch uses that cache by default; `live: true` sends `maxAge: 0` to force a fresh scrape — slower, and more likely to fail on sites with bot protection. A cache hit still costs **1 credit**, so caching buys speed, not quota. / **缓存**：Firecrawl 默认可能返回**最多 2 天旧**的缓存副本（`maxAge` 默认 `172800000` 毫秒）。本插件的抓取默认走缓存；传 `live: true` 时会带 `maxAge: 0` 强制重新抓取——更慢，在被反爬的站点上也更容易失败。命中缓存**照样扣 1 credit**，缓存省的是时间而不是额度。
- This is the only provider here that **reports the origin page's HTTP status** (`metadata.statusCode`) on a fetch, so a result can honestly show a non-200 status instead of a hardcoded 200. / 它是这里唯一会在抓取结果里**返回原页面 HTTP 状态码**（`metadata.statusCode`）的服务，因此结果能如实显示非 200 状态，而不是写死的 200。
- Billing edge cases: a scrape that returns no result is not charged, but a page answering `403`/`404` is still returned to you and costs 1 credit. Feature docs: <https://docs.firecrawl.dev/features/search> and <https://docs.firecrawl.dev/features/scrape>. / 计费边界：完全无结果的抓取不扣费，但返回 `403`/`404` 的页面仍会返回给你并扣 1 credit。功能说明见 <https://docs.firecrawl.dev/features/search> 与 <https://docs.firecrawl.dev/features/scrape>。

## 5. Bright Data MCP

**English**
1. Create an account at <https://brightdata.com> — use **Start free trial** on the homepage, or open <https://brightdata.com/cp/start> directly. No credit card is required for the free tier.
2. Open the control panel's user settings at <https://brightdata.com/cp/setting/users> and copy your **API token** (a UUID such as `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`). This is a *token*, not an API key — the MCP server authenticates with it in the URL.
3. Put it in `BRIGHTDATA_API_TOKEN`. The plugin builds `https://mcp.brightdata.com/mcp?token=<token>` and talks JSON-RPC to it. If you run your own endpoint, set the base URL in `BRIGHTDATA_MCP_URL` and the plugin appends the token query parameter itself.

Bright Data MCP is not a REST API: the plugin performs the MCP handshake (`initialize` → `notifications/initialized`) and then calls two tools — `search_engine` (Google/Bing/Yandex SERP; this plugin always passes `engine: 'google'`) and `scrape_as_markdown`.

**中文**
1. 在 <https://brightdata.com> 注册账号——点首页的 **Start free trial**，或直接打开 <https://brightdata.com/cp/start>。免费档不需要信用卡。
2. 打开控制台的用户设置页 <https://brightdata.com/cp/setting/users>，复制 **API token**（UUID 形态，如 `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`）。注意它是 **token 而不是普通 API key**——MCP 服务靠 URL 里的它来认证。
3. 填入 `BRIGHTDATA_API_TOKEN`。插件会拼出 `https://mcp.brightdata.com/mcp?token=<token>` 并用 JSON-RPC 通信。若你用的是自建端点，把基地址设进 `BRIGHTDATA_MCP_URL`，token 查询参数由插件自己附加。

Bright Data MCP 不是 REST API：插件先完成 MCP 握手（`initialize` → `notifications/initialized`），再调用两个工具——`search_engine`（Google/Bing/Yandex 的搜索结果；本插件固定传 `engine: 'google'`）与 `scrape_as_markdown`（把网页转成 markdown）。

**Notes worth knowing / 值得知道的几点**

- Free tier: **5,000 requests a month, renewing on the 1st**, no credit card and no rollover. It is one **account-wide credit pool** shared with Bright Data's other products (Web Unlocker, SERP API, …), every MCP tool call counts as one request, and team members share the same pool. / 免费档：**每月 5,000 requests，每月 1 日续**，免信用卡，不结转。它是**账号级的共享额度池**，与 Bright Data 其它产品（Web Unlocker、SERP API 等）共用；每次 MCP 工具调用算一个 request，团队成员共用同一份额度。
- Past the free tier it is **$1.50 per 1,000 requests**. An account with no deposited funds simply starts failing instead of running up a bill, and you can set a spend cap in the control panel. / 免费额度用完后按量计费为 **$1.50 / 1,000 requests**；没充值的账号会直接开始失败而不是产生账单，你也可以在控制台设 spend cap 封顶。
- **Slower than the rest by design.** Both tools are remote proxy jobs rather than index lookups: SERP scrapes measured **2.7–27 seconds** across calls, a page scrape around **17 seconds** (simple static pages are much faster; the slow tail is worse than the median), and `initialize` alone about a second. The plugin therefore gives Bright Data its own longer budgets — **40 s for search and 45 s for fetch** in both the JS plugin and the Python server — instead of the generic budgets used for the REST providers. What that means in practice depends on which tool you call: the plugin's own `balanced_search` / `balanced_fetch` budget 60 s, so a slow Bright Data call is abandoned with time left to try the next vendor; the **taken-over `web_search` / `web_fetch` run on dsh's own budgets** (`fetchTimeoutMs` defaults to 30 s), where a single slow call can consume the whole budget and surface as `TOOL_TIMEOUT` instead of falling through. Raise `fetchTimeoutMs` on the `tool-web` row if you want the same headroom there. / **天然比别家慢。** 两个工具都是远程代理任务而非索引查询：SERP 抓取实测 **2.7–27 秒**（波动很大）、普通页面抓取约 **17 秒**（简单静态页会快很多，长尾比中位数更慢），连 `initialize` 都要约 1 秒。因此插件给 Bright Data 单独配了更长的超时——**搜索 40 秒、抓取 45 秒**，JS 插件和 Python 服务器都是如此——而不是 REST 服务用的通用超时。实际后果取决于你调的是哪个工具：插件自己的 `balanced_search` / `balanced_fetch` 预算 60 秒，慢调用会被放弃、还来得及切下一家；**被接管的 `web_search` / `web_fetch` 则跑在 dsh 自己的预算上**（`fetchTimeoutMs` 默认 30 秒），一次慢调用就可能吃满整个预算，表现为 `TOOL_TIMEOUT` 而不是自动落到下一家。想要同样的余量，就把 `tool-web` 行的 `fetchTimeoutMs` 调大。
- **No recency filter.** `search_engine` takes only a query and an engine, so a `balanced_search` call with `time_range` makes Bright Data decline immediately (the JS plugin records `不支持按时间范围过滤，已跳过`; the Python MCP server raises `brightdata 搜索不支持 time_range`) and the Balancer moves on to the next provider. The `web_search` takeover path carries no recency controls anyway, so it is unaffected. / **不支持时间过滤。** `search_engine` 只接受 query 和引擎，所以带 `time_range` 的 `balanced_search` 会让 Bright Data 直接弃权（JS 插件记录 `不支持按时间范围过滤，已跳过`，Python MCP 服务器则抛 `brightdata 搜索不支持 time_range`），由 Balancer 换下一家。接管后的 `web_search` 本来就不带时间参数，因此不受影响。
- **The token travels in the URL query string**, so it can end up in proxy logs, shell history, or crash reports that record full URLs. Inject it through the environment (as this plugin does), never paste a full `https://mcp.brightdata.com/mcp?token=…` URL into issues or CI logs, and rotate the token in the control panel if it leaks. / **token 出现在 URL 查询串里**，因此可能落进代理日志、shell history 或记录完整 URL 的崩溃报告。请像本插件一样通过环境变量注入，不要把完整的 `https://mcp.brightdata.com/mcp?token=…` 贴进 issue 或 CI 日志；一旦泄漏，在控制台轮换 token。
- A fetch returns **markdown only** — no final URL and no origin HTTP status — so a result reports the URL you requested and leaves the status field out entirely instead of claiming 200. / 抓取只返回 **markdown 正文**：既没有最终 URL，也没有原始 HTTP 状态码，因此结果里报告的是你请求的 URL，状态码字段直接留空，而不是假装 200。
- `BRIGHTDATA_API_KEY` is still accepted as a legacy alias, but use `BRIGHTDATA_API_TOKEN` — that is the name its docs and this repo's examples use. / 旧的别名 `BRIGHTDATA_API_KEY` 仍然能识别，但请用 `BRIGHTDATA_API_TOKEN`——它的官方文档和本仓库示例都用这个名字。
- Docs: <https://github.com/brightdata/brightdata-mcp> (protocol, tools, free-tier wording), <https://brightdata.com/pricing/mcp-server>, and the free-tier rules at <https://docs.brightdata.com/general/account/billing-and-pricing/free-tier>. / 文档：<https://github.com/brightdata/brightdata-mcp>（协议、工具与免费档说明）、<https://brightdata.com/pricing/mcp-server>，免费档细则见 <https://docs.brightdata.com/general/account/billing-and-pricing/free-tier>。

## How this plugin uses each key / 插件如何使用这五个 key

One `Balancer` instance serves both surfaces — the `balanced_search` / `balanced_fetch` tools and, after the takeover, dsh's built-in `web_search` / `web_fetch`. It keeps **two independent rotation cursors** (one for search, one for fetch), so a workload that alternates search and fetch does not pin each capability to the same vendor. When a provider fails or declines, the next one in the pool is tried. The Python MCP server (`server.py`) uses the same provider list and the same two-cursor rotation, exposed as the `search` / `fetch` tools.

一个 `Balancer` 实例同时服务两套接口——`balanced_search` / `balanced_fetch` 工具，以及被接管后的内置 `web_search` / `web_fetch`。它维护**两个互相独立的轮询游标**（搜索一个、抓取一个），所以「搜索、抓取交替」的负载不会把每种能力钉死在同一家。某个服务失败或弃权时，会自动尝试池子里的下一家。Python MCP 服务器（`server.py`）用的是同一份 provider 列表和同样的双游标轮换，只是对外暴露为 `search` / `fetch` 两个工具。

| Provider | Search endpoint / 搜索端点 | Fetch endpoint / 抓取端点 |
|---|---|---|
| Keenable | `POST https://api.keenable.ai/v1/search` (`mode: realtime`) | `GET https://api.keenable.ai/v1/fetch` |
| Exa | `POST https://api.exa.ai/search` | `POST https://api.exa.ai/contents` |
| Tavily | `POST https://api.tavily.com/search` (`advanced`) | `POST https://api.tavily.com/extract` (`advanced`) |
| Firecrawl | `POST https://api.firecrawl.dev/v2/search` (`sources: ['web']`, `tbs` for recency) | `POST https://api.firecrawl.dev/v2/scrape` (`formats: ['markdown']`) |
| Bright Data MCP | MCP `tools/call` → `search_engine` (`engine: google`) | MCP `tools/call` → `scrape_as_markdown` |

Three consequences worth planning around / 三个值得注意的后果：

- **The pool holds up to five vendors** — only the ones with a key configured are in it. Round-robin means each call goes to the next configured vendor, so cost is spread across several quotas rather than one; the exception is **time-filtered searches, which always skip Bright Data**, leaving the REST vendors to serve those calls. / **池子最多五家**，只有配了 key 的才在里面。轮询意味着每次调用落到下一个已配置的服务，成本因此摊到多个额度上——例外是**带时间过滤的搜索永远跳过 Bright Data**，这类调用由其余几家来承担。
- **Because fetch runs on the vendor's servers**, the page is retrieved from *their* network, not yours. Fetching therefore still works on machines whose local DNS maps hosts into private or benchmark ranges (for example a Clash / mihomo TUN in `fake-ip` mode). / **抓取在厂商服务端发起**，网页是在**它们的网络**里取的。因此即使本机 DNS 把域名解析到私有/保留网段（如 Clash / mihomo TUN 的 `fake-ip` 模式），抓取依然可用。
- **Adding a key changes the rotation, not just the fallback.** Every extra provider joins the queue, so calls are spread one step thinner over a new quota, and a failure still falls through to the next vendor instead of failing the call. / **新增 key 改变的不只是兜底，还有轮询**：每多一家就多一个轮转位，调用会被摊到新额度上；某一家失败时仍会自动落到下一家，而不是让整个调用失败。

## Verify your keys / 验证 key 是否生效

**English:** With dsh running, ask the model to call `balanced_search` with any query. A response containing `"provider": "keenable" | "exa" | "tavily" | "firecrawl" | "brightdata"` means the corresponding key works. (The Python MCP server exposes the same pool as `search` / `fetch` and reports the same provider ids.) To test a single vendor in isolation, call its API directly:

**中文：** dsh 运行中，让模型用任意 query 调用 `balanced_search`。返回里含 `"provider": "keenable" | "exa" | "tavily" | "firecrawl" | "brightdata"` 即说明对应的 key 生效。（Python MCP 服务器把这套池子暴露为 `search` / `fetch`，provider 标识相同。）想单独测某一家，可直接调它的 API：

```bash
# Keenable
curl -X POST "https://api.keenable.ai/v1/search" \
  -H "X-API-Key: keen_YOUR_KEY" -H "Content-Type: application/json" \
  -d '{"query": "typescript best practices", "mode": "realtime"}'

# Exa
curl -X POST "https://api.exa.ai/search" \
  -H "x-api-key: YOUR_KEY" -H "Content-Type: application/json" \
  -d '{"query": "typescript best practices", "numResults": 3}'

# Tavily
curl -X POST "https://api.tavily.com/search" \
  -H "Authorization: Bearer tvly-YOUR_KEY" -H "Content-Type: application/json" \
  -d '{"query": "typescript best practices", "max_results": 3}'

# Firecrawl
curl -X POST "https://api.firecrawl.dev/v2/search" \
  -H "Authorization: Bearer fc-YOUR-API-KEY" -H "Content-Type: application/json" \
  -d '{"query": "typescript best practices", "limit": 3, "sources": ["web"]}'
```

Bright Data is not a single request: it needs the MCP `initialize` handshake first, then a `tools/call`. This block does both and reads the token from the environment — never paste a real token into a script or a commit. / Bright Data 不是一次请求就能测的：要先 `initialize` 握手拿到 session，再发 `tools/call`。下面这段两件事都做了，token 从环境变量读——不要把真实 token 写进脚本或提交。

```bash
# Bright Data MCP — export BRIGHTDATA_API_TOKEN first (or source the .env that has it)
# e.g. export BRIGHTDATA_API_TOKEN=YOUR_BRIGHT_DATA_TOKEN  ← placeholder only, never a real token
: "${BRIGHTDATA_API_TOKEN:?export BRIGHTDATA_API_TOKEN first}"
MCP_URL="https://mcp.brightdata.com/mcp?token=$BRIGHTDATA_API_TOKEN"
HDRS=(-H "Content-Type: application/json" -H "Accept: application/json, text/event-stream")

# 1) initialize: the session id comes back in a response header
SESSION=$(curl -sS -D - -o /dev/null -X POST "$MCP_URL" "${HDRS[@]}" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}' \
  | awk 'tolower($1)=="mcp-session-id:"{print $2}' | tr -d '\r')

# 2) notifications/initialized (answers 202 with an empty body)
curl -sS -o /dev/null -X POST "$MCP_URL" "${HDRS[@]}" -H "Mcp-Session-Id: $SESSION" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'

# 3) tools/call → the answer arrives as an SSE frame, so keep the data: lines
curl -sS -X POST "$MCP_URL" "${HDRS[@]}" -H "Mcp-Session-Id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search_engine","arguments":{"query":"typescript best practices","engine":"google"}}}' \
  | sed -n 's/^data: //p'
```

The `Mcp-Session-Id` is valid only for the conversation that `initialize` started — do not cache it across runs; a fresh `initialize` yields a new one. The result text is wrapped in a Bright Data security notice plus `=====UNTRUSTED_<id>_BEGIN/END=====` markers; the plugin strips that wrapper, and seeing `organic` with your results inside is the success signal. / `Mcp-Session-Id` 只对发起它的那次会话有效，不要跨进程复用，重新 `initialize` 会得到新的。返回文本外面套着 Bright Data 的安全提示和 `=====UNTRUSTED_<id>_BEGIN/END=====` 标记；插件会剥掉这层壳，你自己测时看到 `organic` 里带着结果就说明成功。

If every provider fails, `balanced_search` returns a JSON error listing each vendor's failure in one line, e.g. `全部搜索 provider 均失败 → exa: HTTP 401: … | firecrawl: HTTP 401: … | brightdata: HTTP 401: …`. That single line is usually enough to tell a bad key from a quota problem. / 如果所有服务都失败，`balanced_search` 会返回一行 JSON 错误，逐个列出各家的失败原因，如 `全部搜索 provider 均失败 → exa: HTTP 401: … | firecrawl: HTTP 401: … | brightdata: HTTP 401: …`。这一行通常就够区分「key 错了」和「额度用尽」。

Common causes / 常见原因：

| Symptom / 现象 | Cause / 原因 |
|---|---|
| `未配置任何搜索 API key（请设置 …）` | No key in the dsh process environment / dsh 进程环境里没有任何 key |
| `HTTP 401` / `HTTP 400` | Key missing, mistyped, or in the wrong header scheme — for Bright Data, a bad or expired token in the URL / key 缺失、写错，或用了错误的头——Bright Data 则是 URL 里的 token 不对或已失效 |
| `HTTP 402` (Keenable) | Monthly allowance spent and no purchased credits / 月度额度用尽且无付费余额 |
| `HTTP 429` | Rate limit — Keenable 10 req/s per organization, Firecrawl free plan 10 req/min / 触发限流——Keenable 为每组织 10 请求/秒，Firecrawl 免费档为 10 请求/分 |
| `HTTP 403` | Key disabled or revoked in the vendor's console / key 在厂商后台被禁用或吊销 |
| Search fails with `brightdata: 不支持按时间范围过滤，已跳过` (JS) or `brightdata 搜索不支持 time_range` (Python) as the only entry | Bright Data is your only configured provider and `time_range` was set — add another key or drop `time_range` / Bright Data 是你唯一配置的服务，而请求带了 `time_range`——再配一家，或去掉 `time_range` |
| `web_search` fails with `WEB_PROVIDER_CONFIGURED_UNAVAILABLE` | The built-in tools are pinned to `balanced` but no key is configured — add a key, or remove the pin in your profile's `cordis.patch.yml` / 内置工具被钉到 `balanced` 但没有 key——加一个 key，或在 profile 的 `cordis.patch.yml` 里移除该 pin |

## Security / 安全

- **Never commit keys.** `.env` is already excluded by `.gitignore`; only `.env.example` (empty placeholders) is tracked. / **不要把 key 提交进仓库。** `.env` 已被 `.gitignore` 排除，仓库里只跟踪空占位符的 `.env.example`。
- Set keys through the **process environment** of dsh, not in `cordis.patch.yml` — that file is plain text and typically version-controlled. / key 请通过 dsh 的**进程环境变量**注入，不要写进 `cordis.patch.yml`——那是纯文本且通常纳入版本控制。
- **Bright Data's token is passed as a URL query parameter**, and URLs are logged far more often than headers are. Keep it out of committed files, CI output, and issue reports; rotate it in the control panel if it is exposed. / **Bright Data 的 token 通过 URL 查询参数传递**，而 URL 被记录下来（日志、CI、错误报告）的概率远高于请求头。别把它写进纳入版本控制的文件、CI 输出或 issue；一旦暴露，在控制台轮换。
- Keys are read from the process environment when the plugin builds its provider pool on first use, so rotating a key only requires restarting dsh with the new value — no code or config change. / key 在插件首次使用时构建 provider 池时从进程环境读取，所以换 key 只需用新值重启 dsh，无需改代码或配置。
- Prefer per-purpose keys where the vendor supports it (Tavily supports multiple named keys with individual monthly limits) so one leak can be revoked alone. / 优先使用按用途分开的 key（Tavily 支持多个具名 key 且可各自设月度上限），这样单个泄漏可以单独吊销。
- Treat both the vendor keys and the search results you fetch as sensitive inputs: results are external content and should never be executed as instructions. / 厂商 key 和抓回来的网页内容都应视为敏感输入：结果是外部内容，绝不应被当作指令执行。

## License

MIT — same as the rest of this repository. / 与本仓库其余部分一致，MIT。
