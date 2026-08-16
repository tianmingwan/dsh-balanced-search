# dsh-balanced-search

均衡搜索插件 / MCP 服务器：把 **Keenable（Keen Search）/ Exa / Tavily** 三个搜索 API **轮流调用**（round-robin），某个服务失败时**自动切换下一个**，统一返回标题 / 链接 / 摘要。

这个仓库同时提供两种形态：

1. **DeepSeek Harness 原生插件（推荐）**：直接注册 `balanced_search` / `balanced_fetch` 两个 dsh 工具，无需 Python。
2. **通用 MCP 服务器**：通过 `server.py` 以 stdio 方式暴露 `search` / `fetch`，可供任意 MCP 客户端使用。

## 功能

- 搜索网页，返回标题、链接和内容摘要。
- 抓取指定 URL 的网页正文，返回 clean markdown。
- 三个服务轮流调用，单个服务失败时自动切换下一个。
- 通过环境变量配置 API key；未配置的服务不会启用。

## 环境变量

至少配置一个搜索服务的 API key：

```bash
KEENABLE_API_KEY=...
EXA_API_KEY=...
TAVILY_API_KEY=...
```

dsh 原生插件直接读取进程环境变量；Python MCP 服务器还会自动读取同目录下的 `.env` 文件。

## 目录结构

| 文件 | 说明 |
|---|---|
| `index.js` | dsh 原生插件入口，注册 `balanced_search` / `balanced_fetch` |
| `cordis.patch.yml` | dsh bundle 配置层，插入插件行 |
| `package.json` | dsh bundle 声明 |
| `server.py` | 通用 MCP server（stdio），暴露 `search` / `fetch` |
| `providers.py` | Python 版三个 API 客户端 + 轮换 / 故障切换 |
| `requirements.txt` | Python MCP 服务器依赖 |
| `.env.example` | API key 配置模板（复制为 `.env` 使用） |
| `.gitignore` | 排除 `.env`、虚拟环境、缓存等 |

## 安装为 dsh 插件

要求：DeepSeek Harness（dsh）已安装，Node.js ≥ 20。

```sh
dsh plugin --profile web add github:tianmingwan/balanced-search
```

重启 `dsh --profile web` 后，会话中会出现两个工具：

- `balanced_search`
- `balanced_fetch`

无需安装 Python 依赖。

## 作为通用 MCP 服务器使用

### 安装

```bash
python -m venv .venv
# Windows
.venv\Scripts\python.exe -m pip install -r requirements.txt
# Linux / macOS
.venv/bin/python -m pip install -r requirements.txt
```

### 运行

```bash
# stdio 模式，供 MCP 客户端连接
python server.py
# 或使用虚拟环境中的 Python
.venv\Scripts\python.exe server.py   # Windows
.venv/bin/python server.py           # Linux / macOS
```

### MCP 客户端接入示例

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

### dsh 原生工具

- `balanced_search`：参数 `query` / `max_results` / `time_range`
- `balanced_fetch`：参数 `url` / `max_chars` / `live`

### MCP 工具

- `search`：参数 `query` / `max_results` / `time_range`
- `fetch`：参数 `url` / `max_chars` / `live`

### 参数说明

- `query`（必填）：搜索关键词或自然语言问题
- `max_results`：1–20，默认 8
- `time_range`：`day` / `week` / `month` / `year`（Tavily 原生；Exa 映射为 `startPublishedDate`；Keenable 映射为 `published_after`）
- `max_chars`：抓取内容最大字符数，默认 30000，上限 50000
- `live`：是否实时从源站抓取（绕过索引/缓存），默认 `false`

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

抓取返回：

```json
{
  "provider": "keenable|exa|tavily",
  "result": {"url": "...", "title": "...", "content": "..."}
}
```

## 配置说明

- 换 key：dsh 插件通过环境变量注入；MCP 服务器通过 `.env` 或客户端 `env` 注入。
- 轮换策略：`Balancer`（当前为 round-robin + 失败切换，可改成加权/健康度感知）。
- 新增服务：在 `providers.py` 写一个 `SearchProvider` 子类，在 `build_balancer()` 里注册；或在 `index.js` 中增加对应 Provider 类。

## License

MIT
