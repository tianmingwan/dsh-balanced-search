# dsh-balanced-search

**English:** A balanced web search plugin / MCP server that round-robins across **Keenable (Keen Search) / Exa / Tavily** and automatically fails over to the next provider. Returns normalized titles, links, and content summaries.

**中文：** 均衡搜索插件 / MCP 服务器：把 **Keenable（Keen Search）/ Exa / Tavily** 三个搜索 API **轮流调用**（round-robin），某个服务失败时**自动切换下一个**，统一返回标题 / 链接 / 摘要。

This repository provides two forms / 本仓库同时提供两种形态：

1. **DeepSeek Harness native plugin (recommended) / dsh 原生插件（推荐）** — registers `balanced_search` / `balanced_fetch` as dsh tools **and** automatically takes over the built-in `web_search` / `web_fetch`, no Python required. / 既注册 `balanced_search` / `balanced_fetch` 两个 dsh 工具，**同时自动接管内置的 `web_search` / `web_fetch`**，无需 Python。
2. **Generic MCP server / 通用 MCP 服务器** — exposes `search` / `fetch` over stdio via `server.py` for any MCP client. / 通过 `server.py` 以 stdio 方式暴露 `search` / `fetch`，可供任意 MCP 客户端使用。

## Features / 功能

- Search the web and return titles, links, and content summaries. / 搜索网页，返回标题、链接和内容摘要。
- Fetch a URL and return clean markdown text. / 抓取指定 URL 的网页正文，返回 clean markdown。
- Round-robin across providers with automatic failover. / 三个服务轮流调用，单个服务失败时自动切换下一个。
- Configure API keys via environment variables; providers without a key are skipped. / 通过环境变量配置 API key；未配置的服务不会启用。
- **Takes over the built-in `web_search` / `web_fetch` automatically** — the bundle pins dsh's `web` row to this plugin's `balanced` provider, so no manual profile edit is needed. / **自动接管内置的 `web_search` / `web_fetch`**：bundle 层把 dsh 的 `web` 行钉到本插件的 `balanced` provider，**无需手工改任何配置**。
- **Fetch happens server-side, at the vendor** — so it also works where the shipped local `http` fetch provider cannot. See [Configuration Notes](#configuration-notes--配置说明). / **抓取在厂商服务端完成**，因此在 dsh 自带本地抓取 provider 无法工作的环境下依然可用，见[配置说明](#configuration-notes--配置说明)。

## Environment Variables / 环境变量

Configure at least one search provider API key / 至少配置一个搜索服务的 API key：

```bash
KEENABLE_API_KEY=...
EXA_API_KEY=...
TAVILY_API_KEY=...
```

The dsh native plugin reads process environment variables directly. The Python MCP server also loads a `.env` file in the same directory. / dsh 原生插件直接读取进程环境变量；Python MCP 服务器还会自动读取同目录下的 `.env` 文件。

## Directory Structure / 目录结构

| File / 文件 | Description / 说明 |
|---|---|
| `index.js` | dsh native plugin entry; registers `balanced_search` / `balanced_fetch` and the `ctx.web` provider `balanced` / dsh 原生插件入口：注册两个工具，并向 `ctx.web` 注册 `balanced` provider |
| `cordis.patch.yml` | dsh bundle config layer; inserts the plugin and pins the `web` row to the `balanced` provider / dsh bundle 配置层：插入插件，并把 `web` 行钉到 `balanced` provider |
| `package.json` | dsh bundle manifest / dsh bundle 声明 |
| `server.py` | Generic MCP server (stdio); exposes `search` / `fetch` / 通用 MCP server |
| `providers.py` | Python providers + round-robin / failover / Python 版 API 客户端与轮换 |
| `requirements.txt` | Python MCP server dependencies / Python MCP 服务器依赖 |
| `.env.example` | API key template (copy to `.env`) / API key 配置模板 |
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

The takeover needs at least one of `KEENABLE_API_KEY` / `EXA_API_KEY` / `TAVILY_API_KEY`. With none set, the `balanced` provider reports itself unavailable and the built-in tools fail with `WEB_PROVIDER_CONFIGURED_UNAVAILABLE` naming `balanced`. / 接管需要至少配置一个 key；一个都没有时，`balanced` provider 会报告不可用，内置工具会以 `WEB_PROVIDER_CONFIGURED_UNAVAILABLE` 失败。

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
        "TAVILY_API_KEY": "..."
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
- `time_range`: `day` / `week` / `month` / `year` (native for Tavily; Exa maps to `startPublishedDate`; Keenable maps to `published_after`) / （Tavily 原生；Exa 映射为 `startPublishedDate`；Keenable 映射为 `published_after`）
- `max_chars`: Maximum characters to return, default 30000, max 50000 / 抓取内容最大字符数，默认 30000，上限 50000
- `live`: Fetch live from the source (bypass index/cache), default `false` / 是否实时从源站抓取（绕过索引/缓存），默认 `false`

Search response / 搜索返回 JSON：

```json
{
  "provider": "keenable|exa|tavily",
  "count": 1,
  "results": [
    {"title": "...", "url": "...", "content": "...", "published_at": "...", "score": 0.5}
  ]
}
```

Fetch response / 抓取返回 JSON：

```json
{
  "provider": "keenable|exa|tavily",
  "result": {"url": "...", "title": "...", "content": "..."}
}
```

## Configuration Notes / 配置说明

- Change keys / 换 key：dsh plugin uses environment variables; MCP server uses `.env` or client `env` injection.
- Failover strategy / 轮换策略：`Balancer` (currently round-robin + failover; can be changed to weighted or health-aware). Search and fetch advance independent cursors, so a fetch does not shift the next search's starting provider. / 搜索与抓取各自独立推进游标，一次抓取不会改变下次搜索的起点。
- Add a provider / 新增服务：add a `SearchProvider` subclass in `providers.py` and register it in `build_balancer()`; or add a Provider class in `index.js`.
- Server-side fetch / 服务端抓取：the fetch call is made by Keenable / Exa / Tavily, so the page is retrieved from *their* network, not yours. This is why fetching still works when the local machine's DNS maps hosts into private or benchmark ranges — for example a Clash / mihomo TUN in `fake-ip` mode answering with `198.18.0.0/15` addresses — where dsh's shipped local `http` fetch provider refuses with `resolves to a non-public IP address`. / 抓取由 Keenable / Exa / Tavily 发起，网页是在**它们的网络**里取的。因此当本机 DNS 把域名解析到私有或保留网段（例如 Clash / mihomo TUN 的 `fake-ip` 模式返回 `198.18.0.0/15` 地址）时，抓取依然可用；而 dsh 自带的本地 `http` provider 会以 `resolves to a non-public IP address` 拒绝。
- Reporting a fetch status / 关于抓取状态码：the seam's `WebFetchResult` requires a `statusCode`, and every vendor extracts server-side without exposing the origin page's status, so the provider reports `200` for a successful extraction and infers `truncated` from whether the body reached its cap. / seam 要求返回 `statusCode`，而三家厂商都是服务端抽取、不暴露原页面状态码，因此抽取成功即记为 `200`，`truncated` 按正文是否触顶推断。

## License

MIT
