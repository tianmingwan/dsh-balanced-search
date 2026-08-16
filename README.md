# balanced-search MCP

一个均衡搜索 MCP 服务器：把 **Keenable（Keen Search）/ Exa / Tavily** 三个搜索 API **轮流调用**（round-robin），某个服务失败时**自动切换下一个**，统一返回标题 / 链接 / 摘要。

## 功能

- `search`：搜索网页，返回标题、链接和内容摘要。
- `fetch`：抓取指定 URL 的网页正文，返回 clean markdown。
- 三个服务轮流调用，单个服务失败时自动切换下一个。
- 通过环境变量配置 API key；未配置的服务不会启用。

## 目录结构

| 文件 | 说明 |
|---|---|
| `server.py` | MCP server（stdio），暴露 `search` / `fetch` 工具 |
| `providers.py` | 三个 API 客户端 + 轮换 / 故障切换（`Balancer`） |
| `requirements.txt` | Python 依赖 |
| `.env.example` | API key 配置模板（复制为 `.env` 使用） |
| `.gitignore` | 排除 `.env`、虚拟环境、缓存等 |

## 环境变量

至少配置一个搜索服务的 API key：

```bash
KEENABLE_API_KEY=...
EXA_API_KEY=...
TAVILY_API_KEY=...
```

服务器启动时会自动读取同目录下的 `.env` 文件（也可直接通过进程环境变量注入）。

## 安装

```bash
python -m venv .venv
# Windows
.venv\Scripts\python.exe -m pip install -r requirements.txt
# Linux / macOS
.venv/bin/python -m pip install -r requirements.txt
```

## 运行

```bash
# stdio 模式，供 MCP 客户端连接
python server.py
# 或使用虚拟环境中的 Python
.venv\Scripts\python.exe server.py   # Windows
.venv/bin/python server.py           # Linux / macOS
```

## MCP 客户端接入示例

以 stdio transport 为例：

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

## 工具用法

### `search`

- `query`（必填）：搜索关键词或自然语言问题
- `max_results`：1–20，默认 8
- `time_range`：`day` / `week` / `month` / `year`（Tavily 原生；Exa 映射为 `startPublishedDate`；Keenable 映射为 `published_after`）

返回 JSON：

```json
{
  "provider": "keenable|exa|tavily",
  "count": 1,
  "results": [
    {"title": "...", "url": "...", "content": "...", "published_at": "...", "score": 0.5}
  ]
}
```

### `fetch`

- `url`（必填）：要抓取的网页地址
- `max_chars`：返回内容的最大字符数，默认 30000，上限 50000
- `live`：是否实时从源站抓取（绕过索引/缓存），默认 `false`

返回 JSON：

```json
{
  "provider": "keenable|exa|tavily",
  "result": {"url": "...", "title": "...", "content": "..."}
}
```

## 配置说明

- 换 key：编辑 `.env`，或通过 MCP 客户端的 `env` 注入。
- 轮换策略：`providers.py` 的 `Balancer`（当前为 round-robin + 失败切换，可改成加权/健康度感知）。
- 新增服务：在 `providers.py` 写一个 `SearchProvider` 子类，在 `build_balancer()` 里注册即可。

## License

MIT
