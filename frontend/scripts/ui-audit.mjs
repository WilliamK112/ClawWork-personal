#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'

const ROOT = path.resolve(process.cwd(), 'src')
const APP = path.resolve(ROOT, 'App.jsx')

function walk(dir) {
  const out = []
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name)
    if (ent.isDirectory()) out.push(...walk(p))
    else if (/\.(jsx|tsx|js|ts)$/.test(ent.name)) out.push(p)
  }
  return out
}

function lineNo(s, idx) {
  return s.slice(0, idx).split('\n').length
}

const files = walk(ROOT)
const issues = []

// collect declared routes from App.jsx
const appSrc = fs.readFileSync(APP, 'utf8')
const routeSet = new Set()
for (const m of appSrc.matchAll(/<Route\s+path=\"([^\"]+)\"/g)) routeSet.add(m[1])

for (const file of files) {
  const src = fs.readFileSync(file, 'utf8')
  const rel = path.relative(process.cwd(), file)

  // 1) button should have onClick OR type=submit/reset OR disabled explicit (rare static)
  for (const m of src.matchAll(/<button\b([^>]*)>/g)) {
    const attrs = m[1]
    const ln = lineNo(src, m.index)
    const hasOnClick = /onClick\s*=/.test(attrs)
    const hasTypeSubmitReset = /type\s*=\s*['\"](submit|reset)['\"]/.test(attrs)
    if (!hasOnClick && !hasTypeSubmitReset) {
      issues.push({ file: rel, line: ln, kind: 'button-missing-handler', detail: attrs.trim() })
    }
  }

  // 2) Link routes should exist in App routes (allow dynamic and root)
  for (const m of src.matchAll(/<Link\b([^>]*)\bto=\"([^\"]+)\"/g)) {
    const ln = lineNo(src, m.index)
    const to = m[2]
    const ok = routeSet.has(to)
    if (!ok) {
      issues.push({ file: rel, line: ln, kind: 'link-route-mismatch', detail: to })
    }
  }

  // 3) onClick declared with empty body
  for (const m of src.matchAll(/onClick=\{\(\)\s*=>\s*\{\s*\}\}/g)) {
    const ln = lineNo(src, m.index)
    issues.push({ file: rel, line: ln, kind: 'onclick-empty', detail: m[0] })
  }
}

if (issues.length) {
  console.error('UI audit failed with issues:')
  for (const i of issues) {
    console.error(`- ${i.file}:${i.line} [${i.kind}] ${i.detail}`)
  }
  process.exit(1)
}

console.log(`UI audit passed: ${files.length} files checked, no dead buttons/links detected.`)
