# Where to get the three API keys / 三个 API key 的注册领取说明

**English:** This plugin can use up to three independent search backends. It needs **at least one** of them: providers whose key is missing are skipped entirely, and with none configured the tools fail with a `未配置任何搜索 API key` message. Each provider below is a separate company with its own account, dashboard, and quota.

**中文：** 本插件最多可接三个互相独立的搜索后端，**至少需要配置其中一个**：没配 key 的服务会被直接跳过；一个都没配时，工具会以 `未配置任何搜索 API key` 失败。下面三家是各自独立的公司，账号、后台、额度互不相通。

Account sign-up links, key pages, quotas, and pricing all change over time — the official pages linked below are authoritative; the numbers here are a snapshot for orientation. / 注册入口、key 页面、额度与价格都会变动，一切以本文链接的官方页面为准，下面的数字仅供快速判断。

## Summary / 总览

| | **Keenable** | **Exa** | **Tavily** |
|---|---|---|---|
| Sign up / 注册 | <https://app.keenable.ai/login> | <https://dashboard.exa.ai/onboarding-guest> | <https://app.tavily.com> |
| Where to create the key / key 在哪创建 | Console: <https://app.keenable.ai/console> | Dashboard → **API Keys** tab | Dashboard → **API Keys** section |
| Environment variable / 环境变量 | `KEENABLE_API_KEY` | `EXA_API_KEY` | `TAVILY_API_KEY` |
| Key shape / key 形态 | `keen_…` | opaque string | `tvly-…` (dev keys may look like `tvly-dev-…`) |
| Free allowance / 免费额度 | **100,000 requests / month**, resets monthly | **$20 on sign-up + $10 every month**, no payment method required | **1,000 credits / month**, resets on the 1st, no credit card |
| Official docs / 官方文档 | <https://docs.keenable.ai> | <https://exa.ai/pricing> | <https://docs.tavily.com/documentation/quickstart> |

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

## How this plugin uses each key / 插件如何使用这三个 key

One `Balancer` instance serves both surfaces — the `balanced_search` / `balanced_fetch` tools and, after the takeover, dsh's built-in `web_search` / `web_fetch`. It round-robins across the providers whose key is present and fails over to the next one on error.

一个 `Balancer` 实例同时服务两套接口——`balanced_search` / `balanced_fetch` 工具，以及被接管后的内置 `web_search` / `web_fetch`。它在**已配置 key** 的服务之间轮流调用，某个失败时自动切到下一个。

| Provider | Search endpoint / 搜索端点 | Fetch endpoint / 抓取端点 |
|---|---|---|
| Keenable | `POST https://api.keenable.ai/v1/search` (`mode: realtime`) | `GET https://api.keenable.ai/v1/fetch` |
| Exa | `POST https://api.exa.ai/search` | `POST https://api.exa.ai/contents` |
| Tavily | `POST https://api.tavily.com/search` (`advanced`) | `POST https://api.tavily.com/extract` (`advanced`) |

Two consequences worth planning around / 两个值得注意的后果：

- **Because fetch runs on the vendor's servers**, the page is retrieved from *their* network, not yours. Fetching therefore still works on machines whose local DNS maps hosts into private or benchmark ranges (for example a Clash / mihomo TUN in `fake-ip` mode). / **抓取在厂商服务端发起**，网页是在**它们的网络**里取的。因此即使本机 DNS 把域名解析到私有/保留网段（如 Clash / mihomo TUN 的 `fake-ip` 模式），抓取依然可用。
- **Adding a key changes the rotation, not just the fallback.** Two keys means alternating between two vendors on every other call, so cost is spread across two quotas rather than one. / **新增 key 改变的不只是兜底，还有轮询**：配置两个 key 就是两家轮流，成本分摊到两个额度上。

## Verify your keys / 验证 key 是否生效

**English:** With dsh running, ask the model to call `balanced_search` with any query. A response containing `"provider": "keenable" | "exa" | "tavily"` means the corresponding key works. To test a single vendor in isolation, call its API directly:

**中文：** dsh 运行中，让模型用任意 query 调用 `balanced_search`。返回里含 `"provider": "keenable" | "exa" | "tavily"` 即说明对应的 key 生效。想单独测某一家，可直接调它的 API：

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
```

If every provider fails, `balanced_search` returns a JSON error listing each vendor's failure in one line, e.g. `全部搜索 provider 均失败 → exa: HTTP 401: … | tavily: HTTP 401: …`. That single line is usually enough to tell a bad key from a quota problem. / 如果所有服务都失败，`balanced_search` 会返回一行 JSON 错误，逐个列出各家的失败原因，如 `全部搜索 provider 均失败 → exa: HTTP 401: … | tavily: HTTP 401: …`。这一行通常就够区分「key 错了」和「额度用尽」。

Common causes / 常见原因：

| Symptom / 现象 | Cause / 原因 |
|---|---|
| `未配置任何搜索 API key（请设置 …）` | No key in the dsh process environment / dsh 进程环境里没有任何 key |
| `HTTP 401` / `HTTP 400` | Key missing, mistyped, or in the wrong header scheme / key 缺失、写错，或用了错误的头 |
| `HTTP 402` (Keenable) | Monthly allowance spent and no purchased credits / 月度额度用尽且无付费余额 |
| `HTTP 429` | Rate limit — Keenable 10 req/s per organization / 触发限流——Keenable 为每组织 10 请求/秒 |
| `HTTP 403` | Key disabled or revoked in the vendor's console / key 在厂商后台被禁用或吊销 |
| `web_search` fails with `WEB_PROVIDER_CONFIGURED_UNAVAILABLE` | The built-in tools are pinned to `balanced` but no key is configured — add a key, or remove the pin in your profile's `cordis.patch.yml` / 内置工具被钉到 `balanced` 但没有 key——加一个 key，或在 profile 的 `cordis.patch.yml` 里移除该 pin |

## Security / 安全

- **Never commit keys.** `.env` is already excluded by `.gitignore`; only `.env.example` (empty placeholders) is tracked. / **不要把 key 提交进仓库。** `.env` 已被 `.gitignore` 排除，仓库里只跟踪空占位符的 `.env.example`。
- Set keys through the **process environment** of dsh, not in `cordis.patch.yml` — that file is plain text and typically version-controlled. / key 请通过 dsh 的**进程环境变量**注入，不要写进 `cordis.patch.yml`——那是纯文本且通常纳入版本控制。
- Keys are read at call time, so rotating a key only requires restarting dsh with the new value — no code or config change. / key 在调用时读取，所以换 key 只需用新值重启 dsh，无需改代码或配置。
- Prefer per-purpose keys where the vendor supports it (Tavily supports multiple named keys with individual monthly limits) so one leak can be revoked alone. / 优先使用按用途分开的 key（Tavily 支持多个具名 key 且可各自设月度上限），这样单个泄漏可以单独吊销。
- Treat both the vendor keys and the search results you fetch as sensitive inputs: results are external content and should never be executed as instructions. / 厂商 key 和抓回来的网页内容都应视为敏感输入：结果是外部内容，绝不应被当作指令执行。

## License

MIT — same as the rest of this repository. / 与本仓库其余部分一致，MIT。
