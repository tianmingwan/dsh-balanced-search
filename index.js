// dsh-balanced-search — native DeepSeek Harness plugin.
//
// Registers `balanced_search` and `balanced_fetch` tools that round-robin
// across Keenable / Exa / Tavily, with automatic failover.
//
// This file is the dsh-native entry. The repository also ships server.py /
// providers.py so the same backend can be used as a standalone MCP server.

export const name = 'dsh-balanced-search'
export const inject = ['tools']

const TIME_RANGES = ['day', 'week', 'month', 'year']
const DAYS_BY_RANGE = { day: 1, week: 7, month: 30, year: 365 }
const KEENABLE_REL = { day: '1d', week: '7d', month: '1mo', year: '1y' }
const HTTP_TIMEOUT_MS = 30_000

class ProviderError extends Error {}

function json(value) {
  return JSON.stringify(value, null, 2)
}

function isoDaysAgo(days) {
  return new Date(Date.now() - days * 86_400_000).toISOString().replace(/\.\d{3}Z$/, '.000Z')
}

async function requestJson(url, options = {}) {
  const { timeoutMs = HTTP_TIMEOUT_MS, signal, ...rest } = options
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(new Error('timeout')), timeoutMs)
  const onOuterAbort = () => controller.abort(signal?.reason)
  if (signal) {
    if (signal.aborted) controller.abort(signal.reason)
    else signal.addEventListener('abort', onOuterAbort, { once: true })
  }
  try {
    const response = await fetch(url, { ...rest, signal: controller.signal })
    if (!response.ok) {
      const text = await response.text().catch(() => '')
      throw new ProviderError(`HTTP ${response.status}: ${text.slice(0, 200)}`)
    }
    return await response.json()
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw new ProviderError(`请求超时（${timeoutMs}ms）`)
    }
    throw error
  } finally {
    clearTimeout(timer)
    if (signal) signal.removeEventListener('abort', onOuterAbort)
  }
}

class KeenableProvider {
  name = 'keenable'
  constructor(apiKey) {
    this.apiKey = apiKey
  }

  async search(query, maxResults, timeRange, signal) {
    const body = { query, mode: 'realtime' }
    if (timeRange) body.published_after = KEENABLE_REL[timeRange]
    const data = await requestJson('https://api.keenable.ai/v1/search', {
      method: 'POST',
      headers: { 'X-API-Key': this.apiKey, 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
    return (data.results || []).map((item) => ({
      title: item.title || '',
      url: item.url || '',
      content: (item.snippet || item.description || '').trim(),
      published_at: item.published_at || '',
      provider: this.name,
    }))
  }

  async fetch(url, maxChars, live, signal) {
    const params = new URLSearchParams({ url })
    if (maxChars) params.set('max_chars', String(maxChars))
    if (live) params.set('live', 'true')
    const data = await requestJson(`https://api.keenable.ai/v1/fetch?${params}`, {
      headers: { 'X-API-Key': this.apiKey },
      signal,
    })
    return {
      url: data.url || url,
      title: data.title || '',
      content: (data.content || '').trim(),
      provider: this.name,
    }
  }
}

class ExaProvider {
  name = 'exa'
  constructor(apiKey) {
    this.apiKey = apiKey
  }

  async search(query, maxResults, timeRange, signal) {
    const body = {
      query,
      type: 'auto',
      numResults: maxResults,
      contents: { text: { maxCharacters: 3000 }, title: true },
    }
    if (timeRange) body.startPublishedDate = isoDaysAgo(DAYS_BY_RANGE[timeRange])
    const data = await requestJson('https://api.exa.ai/search', {
      method: 'POST',
      headers: { 'x-api-key': this.apiKey, 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
    return (data.results || []).map((item) => ({
      title: item.title || '',
      url: item.url || '',
      content: (item.text || '').trim(),
      published_at: item.publishedDate || '',
      provider: this.name,
    }))
  }

  async fetch(url, maxChars, live, signal) {
    const body = {
      urls: [url],
      text: { maxCharacters: maxChars || 30_000 },
    }
    if (live) body.maxAgeHours = 0
    const data = await requestJson('https://api.exa.ai/contents', {
      method: 'POST',
      headers: { 'x-api-key': this.apiKey, 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
    const results = data.results || []
    const item = results.find((r) => r.url === url || r.id === url) || results[0]
    if (!item) throw new ProviderError('exa 抓取无结果')
    return {
      url: item.url || url,
      title: item.title || '',
      content: (item.text || '').trim(),
      provider: this.name,
    }
  }
}

class TavilyProvider {
  name = 'tavily'
  constructor(apiKey) {
    this.apiKey = apiKey
  }

  async search(query, maxResults, timeRange, signal) {
    const body = {
      query,
      search_depth: 'advanced',
      max_results: maxResults,
    }
    if (timeRange) body.time_range = timeRange
    const data = await requestJson('https://api.tavily.com/search', {
      method: 'POST',
      headers: { Authorization: `Bearer ${this.apiKey}`, 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
    return (data.results || []).map((item) => ({
      title: item.title || '',
      url: item.url || '',
      content: (item.content || '').trim(),
      score: item.score ?? null,
      provider: this.name,
    }))
  }

  async fetch(url, maxChars, live, signal) {
    const body = {
      urls: [url],
      extract_depth: 'advanced',
      format: 'markdown',
    }
    const data = await requestJson('https://api.tavily.com/extract', {
      method: 'POST',
      headers: { Authorization: `Bearer ${this.apiKey}`, 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
    const results = data.results || []
    if (results.length === 0) {
      const failed = data.failed_results || []
      const err = failed[0]?.error || '无结果'
      throw new ProviderError(`tavily 抓取失败: ${err}`)
    }
    const item = results[0]
    return {
      url: item.url || url,
      title: item.title || '',
      content: (item.raw_content || '').trim(),
      provider: this.name,
    }
  }
}

class Balancer {
  constructor(providers) {
    if (!providers.length) {
      throw new Error('至少需要一个 provider')
    }
    this.providers = providers
    this.next = 0
  }

  async search(query, maxResults, timeRange, signal) {
    const start = this.next
    this.next = (this.next + 1) % this.providers.length
    const errors = []
    for (let offset = 0; offset < this.providers.length; offset++) {
      const provider = this.providers[(start + offset) % this.providers.length]
      try {
        const results = await provider.search(query, maxResults, timeRange, signal)
        return { provider: provider.name, results: results.slice(0, maxResults) }
      } catch (error) {
        errors.push(`${provider.name}: ${error?.message || error}`)
      }
    }
    throw new ProviderError('全部搜索 provider 均失败 → ' + errors.join(' | '))
  }

  async fetch(url, maxChars, live, signal) {
    const start = this.next
    this.next = (this.next + 1) % this.providers.length
    const errors = []
    for (let offset = 0; offset < this.providers.length; offset++) {
      const provider = this.providers[(start + offset) % this.providers.length]
      try {
        const result = await provider.fetch(url, maxChars, live, signal)
        return { provider: provider.name, result }
      } catch (error) {
        errors.push(`${provider.name}: ${error?.message || error}`)
      }
    }
    throw new ProviderError('全部抓取 provider 均失败 → ' + errors.join(' | '))
  }
}

function buildBalancer(env = process.env) {
  const providers = []
  if (env.KEENABLE_API_KEY) providers.push(new KeenableProvider(env.KEENABLE_API_KEY))
  if (env.EXA_API_KEY) providers.push(new ExaProvider(env.EXA_API_KEY))
  if (env.TAVILY_API_KEY) providers.push(new TavilyProvider(env.TAVILY_API_KEY))
  if (!providers.length) {
    throw new Error('未配置任何搜索 API key（请设置 KEENABLE_API_KEY / EXA_API_KEY / TAVILY_API_KEY）')
  }
  return new Balancer(providers)
}

let _balancer = null

function getBalancer(env = process.env) {
  if (!_balancer) _balancer = buildBalancer(env)
  return _balancer
}

/** Minimal JSON schema compiler for tool parameters (zero dependencies). */
function toJsonSchema(spec) {
  const properties = {}
  const required = []
  for (const [key, meta] of Object.entries(spec || {})) {
    const prop = { type: meta.type }
    if (meta.description) prop.description = meta.description
    properties[key] = prop
    if (meta.required) required.push(key)
  }
  return { type: 'object', properties, required, additionalProperties: false }
}

function registerSearchTool(ctx) {
  ctx.tools.register({
    name: 'balanced_search',
    description: [
      'Search the web by round-robin calling Keenable / Exa / Tavily, with automatic failover.',
      'Use when the current task needs current web information, links, or content summaries.',
      'Configure at least one of KEENABLE_API_KEY / EXA_API_KEY / TAVILY_API_KEY in the environment.',
      '',
      '中文：轮流调用 Keenable / Exa / Tavily 搜索网页，自动故障切换。',
      '当需要最新网页信息、链接或内容摘要时使用。',
      '需要配置 KEENABLE_API_KEY / EXA_API_KEY / TAVILY_API_KEY 中的至少一个。',
    ].join('\n'),
    parameters: toJsonSchema({
      query: { type: 'string', required: true, description: '搜索关键词或自然语言问题 / Search keyword or natural language question' },
      max_results: { type: 'number', required: false, description: '返回结果条数，1-20，默认 8 / Number of results, 1-20, default 8' },
      time_range: { type: 'string', required: false, description: '可选：day / week / month / year / Optional: day / week / month / year' },
    }),
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      const query = String(args?.query ?? '').trim()
      if (!query) return json({ error: 'query 不能为空', results: [] })

      let maxResults = 8
      try {
        maxResults = Math.max(1, Math.min(20, Number(args?.max_results) || 8))
      } catch {
        maxResults = 8
      }

      const timeRange = args?.time_range ?? null
      if (timeRange != null && !TIME_RANGES.includes(timeRange)) {
        return json({ error: `time_range 必须是 ${TIME_RANGES.join(' / ')} 之一`, results: [] })
      }

      try {
        const { provider, results } = await getBalancer().search(query, maxResults, timeRange, exec?.signal)
        return json({ provider, count: results.length, results })
      } catch (error) {
        return json({
          error: error instanceof ProviderError ? error.message : `内部错误: ${error?.message || error}`,
          results: [],
        })
      }
    },
  })
}

function registerFetchTool(ctx) {
  ctx.tools.register({
    name: 'balanced_fetch',
    description: [
      'Fetch a URL and return clean markdown text by round-robin calling Keenable / Exa / Tavily, with automatic failover.',
      'Use when you need the full text of a web page rather than just search summaries.',
      '',
      '中文：轮流调用 Keenable / Exa / Tavily 抓取网页正文并返回 clean markdown。',
      '当你需要网页全文而不是搜索摘要时使用。',
    ].join('\n'),
    parameters: toJsonSchema({
      url: { type: 'string', required: true, description: '要抓取的网页地址 / URL of the web page to fetch' },
      max_chars: { type: 'number', required: false, description: '返回内容的最大字符数，默认 30000，上限 50000 / Maximum characters to return, default 30000, max 50000' },
      live: { type: 'boolean', required: false, description: '是否实时从源站抓取（绕过索引/缓存），默认 false / Fetch live from the source (bypass index/cache), default false' },
    }),
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      const url = String(args?.url ?? '').trim()
      if (!url) return json({ error: 'url 不能为空' })

      let maxChars = 30_000
      try {
        maxChars = Math.max(1, Math.min(50_000, Number(args?.max_chars) || 30_000))
      } catch {
        maxChars = 30_000
      }

      const live = Boolean(args?.live)
      try {
        const { provider, result } = await getBalancer().fetch(url, maxChars, live, exec?.signal)
        return json({ provider, result })
      } catch (error) {
        return json({ error: error instanceof ProviderError ? error.message : `内部错误: ${error?.message || error}` })
      }
    },
  })
}

export function apply(ctx) {
  registerSearchTool(ctx)
  registerFetchTool(ctx)
}
