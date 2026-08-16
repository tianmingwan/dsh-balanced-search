# dsh-balanced-search

**English:** A balanced web search plugin / MCP server that round-robins across **Keenable (Keen Search) / Exa / Tavily** and automatically fails over to the next provider. Returns normalized titles, links, and content summaries.

**中文：** 均衡搜索插件 / MCP 服务器：把 **Keenable（Keen Search）/ Exa / Tavily** 三个搜索 API **轮流调用**（round-robin），某个服务失败时**自动切换下一个**，统一返回标题 / 链接 / 摘要。

This repository provides two forms / 本仓库同时提供两种形态：

1. **DeepSeek Harness native plugin (recommended) / dsh 原生插件（推荐）** — registers `balanced_search` / `balanced_fetch` directly as dsh tools, no Python required. / 直接注册 `balanced_search` / `balanced_fetch` 两个 dsh 工具，无需 Python。
2. **Generic MCP server / 通用 MCP 服务器** — exposes `search` / `fetch` over stdio via `server.py` for any MCP client. / 通过 `server.py` 以 stdio 方式暴露 `search` / `fetch`，可供任意 MCP 客户端使用。

## Features / 功能

- Search the web and return titles, links, and content summaries. / 搜索网页，返回标题、链接和内容摘要。
- Fetch a URL and return clean markdown text. / 抓取指定 URL 的网页正文，返回 clean markdown。
- Round-robin across providers with automatic failover. / 三个服务轮流调用，单个服务失败时自动切换下一个。
- Configure API keys via environment variables; providers without a key are skipped. / 通过环境变量配置 API key；未配置的服务不会启用。

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
| `index.js` | dsh native plugin entry; registers `balanced_search` / `balanced_fetch` / dsh 原生插件入口 |
| `cordis.patch.yml` | dsh bundle config layer / dsh bundle 配置层 |
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

After restarting `dsh --profile web`, these tools will be available / 重启后会话中会出现两个工具：

- `balanced_search`
- `balanced_fetch`

No Python dependencies required / 无需安装 Python 依赖。

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
- Failover strategy / 轮换策略：`Balancer` (currently round-robin + failover; can be changed to weighted or health-aware).
- Add a provider / 新增服务：add a `SearchProvider` subclass in `providers.py` and register it in `build_balancer()`; or add a Provider class in `index.js`.

## License

MIT
