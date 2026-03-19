#!/usr/bin/env node
import { chromium } from 'playwright'
import { spawn } from 'node:child_process'

const ORIGIN = 'http://127.0.0.1:3000'
const BASE = ORIGIN
const ROUTES = ['/', '/dashboard', '/artifacts', '/work', '/learning']

function sleep(ms) { return new Promise(r => setTimeout(r, ms)) }

async function waitForServer(url, timeoutMs = 30000) {
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    try {
      const r = await fetch(url)
      if (r.ok) return true
    } catch {}
    await sleep(500)
  }
  return false
}

function startPreview() {
  const p = spawn('npm', ['run', 'dev', '--', '--host', '127.0.0.1', '--port', '3000'], {
    stdio: 'pipe',
    shell: true,
  })
  p.stdout.on('data', d => process.stdout.write(`[dev] ${d}`))
  p.stderr.on('data', d => process.stderr.write(`[dev:err] ${d}`))
  return p
}

async function clickVisibleButtonsOnPage(page, route, report) {
  const pass = 1
  const total = await page.locator('button:visible').count()
  for (let i = 0; i < total; i++) {
    const btn = page.locator('button:visible').nth(i)
    try {
      const disabled = await btn.isDisabled().catch(() => false)
      if (disabled) {
        report.skipped.push({ route, pass, index: i, reason: 'disabled' })
        continue
      }

      const text = (await btn.innerText().catch(() => '')).trim().replace(/\s+/g, ' ').slice(0, 120)
      await btn.scrollIntoViewIfNeeded().catch(() => {})
      await btn.click({ timeout: 2500 })
      await page.waitForTimeout(180)

      // Dismiss transient modals/overlays so next buttons remain reachable.
      await page.keyboard.press('Escape').catch(() => {})
      await page.waitForTimeout(60)

      // Keep test in SPA; if route changed unexpectedly, normalize.
      const u = page.url()
      if (!u.startsWith(BASE)) {
        report.failures.push({ route, pass, index: i, text, error: `navigated away: ${u}` })
        await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded' })
        continue
      }

      report.clicked.push({ route, pass, index: i, text })
    } catch (e) {
      report.failures.push({
        route,
        pass,
        index: i,
        error: String(e?.message || e).slice(0, 300),
      })
      // recover baseline route after a failure
      try { await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded' }) } catch {}
    }
  }
}

async function main() {
  const report = { clicked: [], skipped: [], failures: [] }
  const preview = startPreview()

  try {
    const up = await waitForServer(`${BASE}/`)
    if (!up) throw new Error('preview server did not start in time')

    const browser = await chromium.launch({ headless: true })
    const context = await browser.newContext()
    const page = await context.newPage()

    for (const route of ROUTES) {
      await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(250)
      await clickVisibleButtonsOnPage(page, route, report)
    }

    await browser.close()

    const byRoute = {}
    for (const c of report.clicked) byRoute[c.route] = (byRoute[c.route] || 0) + 1
    for (const s of report.skipped) byRoute[s.route] = byRoute[s.route] || 0

    console.log('\n=== Button click smoke report ===')
    console.log(`clicked: ${report.clicked.length}`)
    console.log(`skipped(disabled): ${report.skipped.length}`)
    console.log(`failures: ${report.failures.length}`)
    console.log('by route:', byRoute)

    if (report.failures.length) {
      console.log('\nFailures:')
      for (const f of report.failures.slice(0, 50)) {
        console.log(`- ${f.route} [pass ${f.pass}] #${f.index}: ${f.error}`)
      }
      process.exitCode = 1
    }
  } finally {
    preview.kill('SIGTERM')
  }
}

main().catch(err => {
  console.error(err)
  process.exit(1)
})
