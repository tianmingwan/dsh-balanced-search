// dsh-balanced-search — native DeepSeek Harness plugin.
//
// Two surfaces, one provider pool:
//
//   1. The `balanced_search` / `balanced_fetch` tools, for callers that want
//      `time_range`, an explicit result count, or `max_chars`/`live` — the
//      controls the seam does not carry.
//   2. A `ctx.web` seam provider with id `balanced`, which takes over dsh's
//      built-in `web_search` / `web_fetch` through cordis.patch.yml's pin.
//
// Both surfaces share one {@link Balancer}, so round-robin and failover behave
// identically no matter which one is called.
//
// The GUI draws its search card, globe icon and step wording from the literal
// tool names `web_search` / `web_fetch`, so those two keep the official look
// via the seam. The two plugin-owned tools are given the same look by this
// package's client half (lib/client.js), which claims their views through the
// public `tool.call.toolview` slot and appends a "· balanced" suffix — see the
// `dsh.client` declaration in package.json. `output.presentationMeta` feeds
// that view the structured result (sources, provider, elapsed time).
//
// Deliberately zero dependencies and no imports: the profile directory
// ($DSH_HOME/profiles/<name>) does not resolve `@deepseek-ai/*` packages, so a
// runtime import of the seam's types would fail there. Only Node globals
// (fetch, AbortController) are used.

export const name = 'dsh-balanced-search'
export const inject = ['tools']

const TIME_RANGES = ['day', 'week', 'month', 'year']
const DAYS_BY_RANGE = { day: 1, week: 7, month: 30, year: 365 }
const KEENABLE_REL = { day: '1d', week: '7d', month: '1mo', year: '1y' }
/** Firecrawl expresses recency as Google's `tbs` relative-window codes. */
const FIRECRAWL_TBS = { day: 'qdr:d', week: 'qdr:w', month: 'qdr:m', year: 'qdr:y' }

/**
 * Per-request timeouts, split by capability and deliberately NOT shared.
 *
 * dsh's own tool layer allows a search far longer than a fetch
 * (`searchTimeoutMs` 60000 vs the 30000 fetch default), and the vendors differ
 * the same way: a search is a single fast index query, while an extraction
 * (Tavily's advanced extract in particular) has a server-side 30s budget of its
 * own. A 45s fetch budget therefore lets the Balancer fail over to a second
 * vendor instead of dying on the first one's timeout.
 */
const SEARCH_TIMEOUT_MS = 20_000
const FETCH_TIMEOUT_MS = 45_000

const NO_KEY_MESSAGE =
  '未配置任何搜索 API key（请设置 KEENABLE_API_KEY / EXA_API_KEY / TAVILY_API_KEY / FIRECRAWL_API_KEY）'

/** Provider id registered into the `ctx.web` seam; the `web` row pins this value. */
const WEB_PROVIDER_ID = 'balanced'

/**
 * Body cap applied to seam fetches.
 *
 * The seam's `WebFetchRequest` carries only `url` — no `maxChars`/`live`
 * (those are deployment policy there), so this fixed cap IS the deployment
 * policy. 100_000 matches what dsh's shipped HTTP fetch provider hands the tool
 * layer, so a takeover does not silently shorten fetched pages. It is passed to
 * the vendors that accept one AND enforced locally on the way back, so
 * `truncated` reports what was actually cut.
 */
const WEB_FETCH_MAX_CHARS = 100_000

class ProviderError extends Error {}

function json(value) {
  return JSON.stringify(value, null, 2)
}

function isoDaysAgo(days) {
  return new Date(Date.now() - days * 86_400_000).toISOString().replace(/\.\d{3}Z$/, '.000Z')
}

/**
 * One request with its own timeout, abort wiring and error normalisation.
 *
 * The response BODY is read inside the guarded window, not handed back as a
 * `Response`: a body read that happened after `finally` had already torn this
 * timer down and removed the outer abort listener would be unbounded, and dsh's
 * tool timeout policy awaits the handler rather than abandoning it — so a
 * server that sent headers and then stalled the body would hang the whole tool
 * call instead of failing over.
 */
async function requestJson(url, options = {}) {
  const { timeoutMs = FETCH_TIMEOUT_MS, signal, ...rest } = options
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(new Error('timeout')), timeoutMs)
  const onOuterAbort = () => controller.abort(signal?.reason)
  if (signal) {
    if (signal.aborted) controller.abort(signal.reason)
    else signal.addEventListener('abort', onOuterAbort, { once: true })
  }
  try {
    const response = await fetch(url, { ...rest, signal: controller.signal })
    const text = await response.text()
    if (!response.ok) {
      throw new ProviderError(`HTTP ${response.status}: ${text.slice(0, 200)}`)
    }
    try {
      return JSON.parse(text)
    } catch {
      throw new ProviderError(`响应不是合法 JSON: ${text.slice(0, 200)}`)
    }
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

  async search(query, maxResults, timeRange, signal, timeoutMs) {
    // `max_results` is NOT optional in practice: left out, the endpoint applies
    // its own default of 10, so an explicit 1-20 request would be silently
    // ignored (Keenable SearchRequest: 1-50, default 10).
    const body = { query, mode: 'realtime', max_results: maxResults }
    if (timeRange) body.published_after = KEENABLE_REL[timeRange]
    const data = await requestJson('https://api.keenable.ai/v1/search', {
      method: 'POST',
      headers: { 'X-API-Key': this.apiKey, 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal,
      timeoutMs,
    })
    return (data.results || []).map((item) => ({
      title: item.title || '',
      url: item.url || '',
      content: (item.snippet || item.description || '').trim(),
      published_at: item.published_at || '',
      provider: this.name,
    }))
  }

  async fetch(url, maxChars, live, signal, timeoutMs) {
    const params = new URLSearchParams({ url })
    if (maxChars) params.set('max_chars', String(maxChars))
    if (live) params.set('live', 'true')
    const data = await requestJson(`https://api.keenable.ai/v1/fetch?${params}`, {
      headers: { 'X-API-Key': this.apiKey },
      signal,
      timeoutMs,
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

  async search(query, maxResults, timeRange, signal, timeoutMs) {
    // `type: 'auto'` is Exa's own default and their documented recommendation.
    // `contents.title` is NOT a member of the current ContentsOptions (title
    // arrives on the result itself), so sending it was noise at best; the text
    // budget is trimmed to 2000 because sources are rendered as card snippets,
    // not read whole.
    const body = {
      query,
      type: 'auto',
      numResults: maxResults,
      contents: { text: { maxCharacters: 2000 } },
    }
    if (timeRange) body.startPublishedDate = isoDaysAgo(DAYS_BY_RANGE[timeRange])
    const data = await requestJson('https://api.exa.ai/search', {
      method: 'POST',
      headers: { 'x-api-key': this.apiKey, 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal,
      timeoutMs,
    })
    return (data.results || []).map((item) => ({
      title: item.title || '',
      url: item.url || '',
      content: (item.text || '').trim(),
      published_at: item.publishedDate || '',
      provider: this.name,
    }))
  }

  async fetch(url, maxChars, live, signal, timeoutMs) {
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
      timeoutMs,
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

  async search(query, maxResults, timeRange, signal, timeoutMs) {
    // `search_depth: 'advanced'` costs 2 credits per call against 1 for
    // 'basic'; the Balancer spreads calls over five vendors, so one provider's
    // quota is spent roughly a fifth as fast, and the extra depth is affordable
    // and materially better for research-shaped queries.
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
      timeoutMs,
    })
    return (data.results || []).map((item) => ({
      title: item.title || '',
      url: item.url || '',
      content: (item.content || '').trim(),
      score: item.score ?? null,
      provider: this.name,
    }))
  }

  async fetch(url, maxChars, live, signal, timeoutMs) {
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
      timeoutMs,
    })
    const results = data.results || []
    if (results.length === 0) {
      const failed = data.failed_results || []
      const err = failed[0]?.error || '无结果'
      throw new ProviderError(`tavily 抓取失败: ${err}`)
    }
    const item = results[0]
    // Tavily's extract API exposes no output-length control, so the cap has to
    // be applied here. Without it the seam receives far more text than it asked
    // for, and the caller's own truncation bookkeeping would be wrong.
    const raw = (item.raw_content || '').trim()
    return {
      url: item.url || url,
      title: item.title || '',
      content: maxChars && raw.length > maxChars ? raw.slice(0, maxChars) : raw,
      provider: this.name,
    }
  }
}

/**
 * Firecrawl — REST at api.firecrawl.dev, `Authorization: Bearer fc-…`.
 *
 * It is the only provider that serves both capabilities from a single vendor
 * *and* reports the origin page's status code, so it is also the only one whose
 * fetches can truthfully answer with something other than 200.
 *
 * Two costs drive the shaping of these calls:
 *   * search bills 2 credits per 10 results (rounded up), so asking for the
 *     caller's exact `maxResults` instead of a fat fixed window matters;
 *   * `scrapeOptions` on /search would turn a search into a scrape per result
 *     (1 credit each). The plugin only wants card snippets, so it requests the
 *     cheap default `description` and never asks for page content there.
 */
class FirecrawlProvider {
  name = 'firecrawl'

  constructor(apiKey) {
    this.apiKey = apiKey
  }

  async search(query, maxResults, timeRange, signal, timeoutMs) {
    // `sources: ['web']` pins the result group: without it the response may
    // also carry `news`/`images`, which this normalized result has no place for.
    const body = { query, limit: maxResults, sources: ['web'] }
    if (timeRange) body.tbs = FIRECRAWL_TBS[timeRange]
    const data = await requestJson('https://api.firecrawl.dev/v2/search', {
      method: 'POST',
      headers: { Authorization: `Bearer ${this.apiKey}`, 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal,
      timeoutMs,
    })
    const web = data?.data?.web || []
    return web.map((item) => ({
      title: item.title || '',
      url: item.url || '',
      // `description` is the search snippet, but for some pages it is the
      // extracted page text — far too long for a card. Trim it the way the Exa
      // search trims its `text` budget.
      content: String(item.description ?? '').trim().slice(0, 2000),
      provider: this.name,
    }))
  }

  async fetch(url, maxChars, live, signal, timeoutMs) {
    const body = {
      url,
      formats: ['markdown'],
      // The rest of the page chrome (nav, footer, cookie banners) is noise for
      // every tool call this serves; `onlyMainContent` is what the markdown
      // output is normally wanted for.
      onlyMainContent: true,
    }
    // Firecrawl serves a cached copy up to 2 days old by default. `live` means
    // "bypass the index/cache" everywhere else in this plugin, and `maxAge: 0`
    // is Firecrawl's equivalent — at the cost of a slower, more failure-prone
    // full scrape.
    if (live) body.maxAge = 0
    const data = await requestJson('https://api.firecrawl.dev/v2/scrape', {
      method: 'POST',
      headers: { Authorization: `Bearer ${this.apiKey}`, 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal,
      timeoutMs,
    })
    const doc = data?.data
    if (!doc) throw new ProviderError('firecrawl 抓取无结果')
    const raw = String(doc.markdown ?? '').trim()
    if (raw === '') throw new ProviderError('firecrawl 抓取返回空正文')
    const metadata = doc.metadata || {}
    return {
      url: metadata.sourceURL || doc.url || url,
      title: metadata.title || metadata.ogTitle || '',
      content: maxChars && raw.length > maxChars ? raw.slice(0, maxChars) : raw,
      // Unlike Keenable/Exa/Tavily, Firecrawl does not extract on its own
      // account: `metadata.statusCode` IS the page's HTTP status (`data.metadata
      // .error` may carry detail). Kept as-is so the fetch result can report the
      // origin's own status instead of a hardcoded 200.
      statusCode: Number.isInteger(metadata.statusCode) ? metadata.statusCode : undefined,
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
    // One cursor per capability, deliberately NOT shared: search and fetch are
    // consumed at different rates, and a shared cursor makes the rotation
    // collapse. With exactly two providers and an alternating
    // search/fetch workload a single cursor pins every search to provider A and
    // every fetch to provider B, defeating the round-robin entirely.
    this.nextSearch = 0
    this.nextFetch = 0
  }

  /** Claim the next starting index for one capability and advance its cursor. */
  #take(cursor) {
    const start = this[cursor]
    this[cursor] = (this[cursor] + 1) % this.providers.length
    return start
  }

  async search(query, maxResults, timeRange, signal) {
    const start = this.#take('nextSearch')
    const errors = []
    for (let offset = 0; offset < this.providers.length; offset++) {
      const provider = this.providers[(start + offset) % this.providers.length]
      try {
        const results = await provider.search(query, maxResults, timeRange, signal, SEARCH_TIMEOUT_MS)
        return { provider: provider.name, results: results.slice(0, maxResults) }
      } catch (error) {
        errors.push(`${provider.name}: ${error?.message || error}`)
      }
    }
    throw new ProviderError('全部搜索 provider 均失败 → ' + errors.join(' | '))
  }

  async fetch(url, maxChars, live, signal) {
    const start = this.#take('nextFetch')
    const errors = []
    for (let offset = 0; offset < this.providers.length; offset++) {
      const provider = this.providers[(start + offset) % this.providers.length]
      try {
        const result = await provider.fetch(url, maxChars, live, signal, FETCH_TIMEOUT_MS)
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
  if (env.FIRECRAWL_API_KEY) providers.push(new FirecrawlProvider(env.FIRECRAWL_API_KEY))
  if (!providers.length) {
    throw new Error(NO_KEY_MESSAGE)
  }
  return new Balancer(providers)
}

let _balancer = null

/**
 * The pool, built once and cached.
 *
 * Keys are therefore read once per process: adding or rotating a key needs a
 * restart, which is also what the profile's `.env` load implies.
 */
function getBalancer(env = process.env) {
  if (!_balancer) _balancer = buildBalancer(env)
  return _balancer
}

/**
 * Cheap local availability check; never throws and never makes a network call.
 *
 * The seam calls `available()` on every provider selection, and a pinned
 * provider that reports unavailable fails the call with
 * `WEB_PROVIDER_CONFIGURED_UNAVAILABLE`, so this must stay trivial.
 */
function hasProviderKeys(env = process.env) {
  return Boolean(
    env.KEENABLE_API_KEY || env.EXA_API_KEY || env.TAVILY_API_KEY || env.FIRECRAWL_API_KEY,
  )
}

/**
 * The `ctx.web` seam provider (id {@link WEB_PROVIDER_ID}).
 *
 * One instance is registered into BOTH the search and the fetch registry: the
 * seam keys each registry by `provider.id` independently, so sharing an object
 * across the two capability kinds is fine.
 *
 * Mapping notes: the seam's search request carries only `query`/`maxResults`
 * (recency controls are deferred there), so `timeRange` is always null.
 */
class BalancedWebProvider {
  id = WEB_PROVIDER_ID

  available() {
    return hasProviderKeys()
  }

  async search(request, signal) {
    const balancer = getBalancer()
    const { results } = await balancer.search(request.query, request.maxResults ?? 8, null, signal)
    return {
      sources: results
        .filter((item) => item?.url)
        .map((item) => ({
          url: item.url,
          title: item.title || undefined,
          snippet: item.content || undefined,
          publishedAt: item.published_at || undefined,
        })),
      truncated: false,
    }
  }

  async fetch(request, signal) {
    const balancer = getBalancer()
    // `live=false` is deliberate deployment policy: a WebFetchRequest carries
    // only `url`, and serving from the vendor index keeps latency down. Switch
    // this to `true` to force an origin fetch (Keenable `live=true`, Exa
    // `maxAgeHours=0`, Firecrawl `maxAge=0`; Tavily's extract API and Bright
    // Data's scrape tool have no equivalent control).
    const { result } = await balancer.fetch(request.url, WEB_FETCH_MAX_CHARS, false, signal)
    const raw = (result.content || '').trim()
    // Enforce the cap here as well: a vendor that ignores `maxChars` must not
    // make `truncated` lie.
    const content = raw.length > WEB_FETCH_MAX_CHARS ? raw.slice(0, WEB_FETCH_MAX_CHARS) : raw
    return {
      url: result.url || request.url,
      // Only Firecrawl reports the origin page's own status. The other vendors
      // extract server-side and never see it, so they report a successful
      // extraction as 200 — for them a 403/404 at the origin is
      // indistinguishable and will read as HTTP 200 to the model.
      statusCode: Number.isInteger(result.statusCode) ? result.statusCode : 200,
      body: { kind: 'text', content },
      truncated: raw.length > WEB_FETCH_MAX_CHARS,
    }
  }
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

/**
 * Structured meta for lib/client.js, which draws the tool card from it.
 *
 * The registry deep-freezes the result and requires losslessly serializable
 * JSON, so every field is always present — no `undefined`, which would drop the
 * key and leave the view branching on a missing member.
 */
function searchMeta(args, value) {
  const queries = [String(args?.query ?? '')]
  try {
    const parsed = JSON.parse(String(value))
    return {
      balanced: true,
      kind: 'search',
      queries,
      provider: typeof parsed?.provider === 'string' ? parsed.provider : '',
      elapsedMs: Number.isFinite(parsed?.elapsed_ms) ? parsed.elapsed_ms : 0,
      count: Number.isFinite(parsed?.count) ? parsed.count : 0,
      truncated: parsed?.truncated === true,
      sources: Array.isArray(parsed?.results)
        ? parsed.results.map((item) => ({
            title: String(item?.title ?? ''),
            url: String(item?.url ?? ''),
            snippet: String(item?.content ?? ''),
          }))
        : [],
      error: typeof parsed?.error === 'string' ? parsed.error : '',
    }
  } catch {
    return { balanced: true, kind: 'search', queries, provider: '', elapsedMs: 0, count: 0, truncated: false, sources: [], error: '' }
  }
}

function fetchMeta(args, value) {
  const url = String(args?.url ?? '')
  try {
    const parsed = JSON.parse(String(value))
    const result = parsed?.result ?? {}
    const content = typeof result?.content === 'string' ? result.content : ''
    return {
      balanced: true,
      kind: 'fetch',
      url: typeof result?.url === 'string' && result.url ? result.url : url,
      provider: typeof parsed?.provider === 'string' ? parsed.provider : '',
      elapsedMs: Number.isFinite(parsed?.elapsed_ms) ? parsed.elapsed_ms : 0,
      // Only Firecrawl reports the origin's own status; the rest extract
      // server-side and never see it, so they report `null` and the card omits
      // the HTTP token rather than claiming a status nobody observed. (`0` here
      // would render as a literal `HTTP 0`: the client half only skips `null`.)
      statusCode: Number.isInteger(result?.statusCode) ? result.statusCode : null,
      length: content.length,
      truncated: false,
      error: typeof parsed?.error === 'string' ? parsed.error : '',
    }
  } catch {
    return { balanced: true, kind: 'fetch', url, provider: '', elapsedMs: 0, statusCode: null, length: 0, truncated: false, error: '' }
  }
}

function registerSearchTool(ctx) {
  ctx.tools.register({
    name: 'balanced_search',
    description: [
      'Search the web through a Keenable / Exa / Tavily / Firecrawl round-robin pool with automatic failover.',
      'Use for current web information, links, or content summaries; supports a recency window.',
      'Prefer a single call: issue one query per call and do not fan out several searches in parallel — each query is a separate vendor request.',
      'Configure at least one of KEENABLE_API_KEY / EXA_API_KEY / TAVILY_API_KEY / FIRECRAWL_API_KEY in the environment.',
      '',
      '中文：轮流调用 Keenable / Exa / Tavily / Firecrawl 搜索网页，自动故障切换。',
      '当需要最新网页信息、链接或内容摘要时使用，支持时间范围过滤。',
      '建议一次只发一个查询，不要并行发起多个搜索——每个查询都是一次独立的厂商调用。',
      '需要配置 KEENABLE_API_KEY / EXA_API_KEY / TAVILY_API_KEY / FIRECRAWL_API_KEY 中的至少一个。',
    ].join('\n'),
    parameters: toJsonSchema({
      query: { type: 'string', required: true, description: '搜索关键词或自然语言问题 / Search keyword or natural language question' },
      max_results: { type: 'number', required: false, description: '返回结果条数，1-20，默认 8 / Number of results, 1-20, default 8' },
      time_range: { type: 'string', required: false, description: '可选：day / week / month / year / Optional: day / week / month / year' },
    }),
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
      presentationMeta: searchMeta,
    },
    timeoutMs: 60_000,
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

      const startedAt = Date.now()
      try {
        const { provider, results } = await getBalancer().search(query, maxResults, timeRange, exec?.signal)
        return json({ provider, count: results.length, elapsed_ms: Date.now() - startedAt, truncated: false, results })
      } catch (error) {
        return json({
          error: error instanceof ProviderError ? error.message : `内部错误: ${error?.message || error}`,
          elapsed_ms: Date.now() - startedAt,
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
      'Fetch a URL and return clean markdown text through the same Keenable / Exa / Tavily / Firecrawl round-robin pool, with automatic failover.',
      'Use when you need the full text of a web page rather than just search summaries.',
      'Prefer a single call: one URL per call.',
      '',
      '中文：轮流调用 Keenable / Exa / Tavily / Firecrawl 抓取网页正文并返回 clean markdown。',
      '当你需要网页全文而不是搜索摘要时使用，建议一次只抓一个 URL。',
    ].join('\n'),
    parameters: toJsonSchema({
      url: { type: 'string', required: true, description: '要抓取的网页地址 / URL of the web page to fetch' },
      max_chars: { type: 'number', required: false, description: '返回内容的最大字符数，默认 30000，上限 50000 / Maximum characters to return, default 30000, max 50000' },
      live: { type: 'boolean', required: false, description: '是否实时从源站抓取（绕过索引/缓存），默认 false / Fetch live from the source (bypass index/cache), default false' },
    }),
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
      presentationMeta: fetchMeta,
    },
    timeoutMs: 60_000,
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
      const startedAt = Date.now()
      try {
        const { provider, result } = await getBalancer().fetch(url, maxChars, live, exec?.signal)
        return json({ provider, elapsed_ms: Date.now() - startedAt, result })
      } catch (error) {
        return json({
          error: error instanceof ProviderError ? error.message : `内部错误: ${error?.message || error}`,
          elapsed_ms: Date.now() - startedAt,
        })
      }
    },
  })
}

export function apply(ctx) {
  // Surface 1: the two plugin-owned tools.
  registerSearchTool(ctx)
  registerFetchTool(ctx)

  // Surface 2: the seam provider that takes over dsh's built-in
  // `web_search` / `web_fetch`. cordis.patch.yml pins the `web` row's
  // searchProvider/fetchProvider to WEB_PROVIDER_ID.
  //
  // Written as a dynamic injection rather than an `inject` entry on purpose:
  // Cordis' `inject` has no optional form (every listed service is required and
  // gates the whole plugin), so a hard `web` dependency would keep the provider
  // registration PENDING in any composition that does not mount
  // @deepseek-ai/dsh-web.
  ctx.inject(['web'], (ctx) => {
    const provider = new BalancedWebProvider()
    ctx.web.registerSearchProvider(provider)
    ctx.web.registerFetchProvider(provider)
  })
}
