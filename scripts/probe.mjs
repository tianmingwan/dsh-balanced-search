#!/usr/bin/env node
// scripts/probe.mjs — probe exactly one provider, in isolation, through the
// real plugin code.
//
// The pool rotates, so "which vendor answered?" is normally left to failover.
// This script builds a Balancer containing a single provider (by handing
// buildBalancer an env object with only that vendor's key) and runs one search
// and/or one fetch, printing the normalized result. Handy for checking a new
// key, a vendor's free-plan parameter limits, or a regression in one adapter.
//
// Usage:
//   set -a; . ~/.dsh/.env; set +a
//   node scripts/probe.mjs <vendor> ["query"] [--fetch <url>] [--range day|week|month|year] [--max 8]
//
//   <vendor> is one of: keenable exa tavily firecrawl anysearch tinyfish
//
// Exit code is 0 when every requested operation succeeded, 1 otherwise.
import process from 'node:process'
import { buildBalancer } from '../index.js'

const VENDOR_ENV = {
  keenable: 'KEENABLE_API_KEY',
  exa: 'EXA_API_KEY',
  tavily: 'TAVILY_API_KEY',
  firecrawl: 'FIRECRAWL_API_KEY',
  anysearch: 'ANYSEARCH_API_KEY',
  tinyfish: 'TINYFISH_API_KEY',
}

function parseArgs(argv) {
  const opts = { vendor: '', query: '', fetch: '', range: null, max: 8 }
  const rest = []
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]
    if (arg === '--fetch') opts.fetch = argv[++i] || ''
    else if (arg === '--range') opts.range = argv[++i] || null
    else if (arg === '--max') opts.max = Number(argv[++i]) || 8
    else rest.push(arg)
  }
  opts.vendor = rest[0] || ''
  opts.query = rest.slice(1).join(' ') || 'deepseek harness release notes'
  return opts
}

function line(title) {
  console.log(`\n=== ${title} ===`)
}

async function main() {
  const opts = parseArgs(process.argv.slice(2))
  const envVar = VENDOR_ENV[opts.vendor]
  if (!envVar) {
    console.error(`unknown vendor ${JSON.stringify(opts.vendor)}; expected one of ${Object.keys(VENDOR_ENV).join(', ')}`)
    return 2
  }
  const key = process.env[envVar]
  if (!key) {
    console.error(`${envVar} is not set in this shell (source ~/.dsh/.env first)`)
    return 2
  }

  const balancer = buildBalancer({ [envVar]: key })
  let failed = false

  line(`search · ${opts.vendor} · query=${JSON.stringify(opts.query)} · max=${opts.max} · range=${opts.range ?? 'none'}`)
  const startedAt = Date.now()
  try {
    const { provider, results } = await balancer.search(opts.query, opts.max, opts.range)
    console.log(`provider=${provider} count=${results.length} elapsed=${Date.now() - startedAt}ms`)
    for (const item of results) {
      console.log(`- ${item.title || '(no title)'}`)
      console.log(`  ${item.url}`)
      console.log(`  ${String(item.content || '').replace(/\s+/g, ' ').slice(0, 160)}`)
      if (item.published_at) console.log(`  published_at=${item.published_at}`)
    }
  } catch (error) {
    failed = true
    console.error(`search FAILED after ${Date.now() - startedAt}ms: ${error?.message || error}`)
  }

  if (opts.fetch) {
    line(`fetch · ${opts.vendor} · url=${opts.fetch}`)
    const fetchStart = Date.now()
    try {
      const { provider, result } = await balancer.fetch(opts.fetch, 3000, false)
      console.log(`provider=${provider} title=${JSON.stringify(result.title)} status=${result.statusCode ?? 'n/a'} chars=${String(result.content || '').length} elapsed=${Date.now() - fetchStart}ms`)
      console.log(String(result.content || '').replace(/\s+/g, ' ').slice(0, 300))
    } catch (error) {
      failed = true
      console.error(`fetch FAILED after ${Date.now() - fetchStart}ms: ${error?.message || error}`)
    }
  }

  return failed ? 1 : 0
}

process.exitCode = await main()
