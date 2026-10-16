// Browser smoke test: drives the real UI in headless Chrome against a running backend.
//
//   $env:API_URL = "http://127.0.0.1:8000"     (backend)
//   $env:APP_URL = "http://localhost:5173"     (npm run dev)
//   $env:SEED_PASSWORD = "..."                 (the password used with the seed script)
//   npm run smoke
//
// It creates synthetic requests through the API, then walks the UI: log in, filter and create
// requests (including a server-side field error), run a plan, open every tab, try a what-if,
// approve, publish, view the calendar, and check what a viewer and a department user can see.
// It fails if the browser logs a console error or the page throws.
import { mkdirSync, readdirSync, rmSync } from 'node:fs'
import puppeteer from 'puppeteer-core'

const API_URL = (process.env.API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')
const APP_URL = (process.env.APP_URL ?? 'http://localhost:5173').replace(/\/$/, '')
const PASSWORD = process.env.SEED_PASSWORD
const CHROME =
  process.env.CHROME_PATH ?? 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe'
const SHOTS = new URL('../screenshots/', import.meta.url)
const HORIZON_START = process.env.HORIZON_START ?? '2026-10-19'

if (!PASSWORD) {
  console.error('Set SEED_PASSWORD to the demo users password.')
  process.exit(2)
}
mkdirSync(SHOTS, { recursive: true })
for (const name of readdirSync(SHOTS)) if (name.endsWith('.png')) rmSync(new URL(name, SHOTS))

// ---------- API preparation (plain fetch) ----------

async function api(method, path, token, body) {
  const response = await fetch(`${API_URL}/api/v1${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await response.text()
  const data = text ? JSON.parse(text) : null
  if (!response.ok) throw new Error(`${method} ${path} -> ${response.status} ${text}`)
  return data
}

async function login(email) {
  const pair = await api('POST', '/auth/login', null, { email, password: PASSWORD })
  return pair.access_token
}

async function prepare() {
  const planner = await login('planner@blockplanner.test')
  await api('POST', '/traffic/synthetic', planner, {})
  const end = new Date(Date.parse(`${HORIZON_START}T00:00:00Z`) + 6 * 86400000).toISOString().slice(0, 10)
  await api('POST', '/traffic/rebuild', planner, { date_from: HORIZON_START, date_to: end })
  const plan = [
    ['engg', 'A-B', 120, 'track'],
    ['trd', 'A-B', 120, 'ohe'],
    ['snt', 'A-B', 90, 'signal'],
    ['engg', 'B-C', 180, 'track'],
    ['trd', 'B-C', 120, 'ohe'],
    ['snt', 'C-D', 120, 'signal'],
  ]
  for (const [who, section, minutes, type] of plan) {
    const token = await login(`${who}@blockplanner.test`)
    const request = await api('POST', '/requests', token, {
      section_code: section,
      work_type: type,
      duration_minutes: minutes,
      earliest_date: HORIZON_START,
      deadline_date: new Date(Date.parse(`${HORIZON_START}T00:00:00Z`) + 4 * 86400000).toISOString().slice(0, 10),
      priority: 2,
    })
    await api('POST', `/requests/${request.id}/submit`, token, {})
  }
  return plan.length
}

// ---------- browser helpers ----------

const results = []
const consoleErrors = []
const pageErrors = []
let shot = 0

function expect(condition, message) {
  if (!condition) throw new Error(message)
}

async function snap(page, name) {
  shot += 1
  const file = new URL(`${String(shot).padStart(2, '0')}-${name}.png`, SHOTS)
  await page.screenshot({ path: file.pathname.replace(/^\/([A-Za-z]:)/, '$1'), fullPage: true })
}

async function step(page, name, fn) {
  const started = Date.now()
  try {
    await fn()
    results.push({ name, ok: true })
    console.log(`  ok    ${name} (${((Date.now() - started) / 1000).toFixed(1)} s)`)
  } catch (error) {
    results.push({ name, ok: false, error: error.message })
    console.log(`  FAIL  ${name}: ${error.message}`)
    await snap(page, `FAIL-${name.replace(/\W+/g, '-')}`).catch(() => {})
  }
}

const text = (page) => page.evaluate(() => document.body.innerText)

async function waitText(page, needle, timeout = 15000) {
  await page.waitForFunction((n) => document.body.innerText.includes(n), { timeout }, needle)
}

async function click(page, selector) {
  const locator = page.locator(selector)
  await locator.setTimeout(10000).click()
}

async function fillByLabel(page, label, value, scope = 'body') {
  const handle = await page.evaluateHandle(
    (labelText, scopeSelector) => {
      const root = document.querySelector(scopeSelector)
      const label = [...root.querySelectorAll('label.field')].find((l) =>
        l.querySelector('.field-label')?.textContent.trim().startsWith(labelText),
      )
      return label?.querySelector('input, select, textarea') ?? null
    },
    label,
    scope,
  )
  const element = handle.asElement()
  expect(element, `no field labelled "${label}"`)
  await element.click({ clickCount: 3 })
  await element.type(String(value))
}

/** Set the value of a React-controlled input (such as a date) and fire the events React listens to. */
async function setInput(element, value) {
  await element.evaluate((el, v) => {
    const proto = el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v)
    el.dispatchEvent(new Event('input', { bubbles: true }))
    el.dispatchEvent(new Event('change', { bubbles: true }))
  }, value)
}

async function signIn(page, email) {
  await page.goto(`${APP_URL}/login`, { waitUntil: 'networkidle0' })
  await page.evaluate(() => sessionStorage.clear())
  await page.goto(`${APP_URL}/login`, { waitUntil: 'networkidle0' })
  await page.type('input[type=email]', email)
  await page.type('input[type=password]', PASSWORD)
  await click(page, 'button[type=submit]')
  await page.waitForFunction(() => !location.pathname.startsWith('/login'), { timeout: 15000 })
}

async function signOut(page) {
  await page.evaluate(() => sessionStorage.clear())
  await page.goto(`${APP_URL}/login`, { waitUntil: 'networkidle0' })
}

// ---------- the walk ----------

const created = await prepare()
console.log(`Prepared ${created} synthetic requests and traffic through the API.`)

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: ['--no-sandbox', '--disable-gpu'],
  defaultViewport: { width: 1440, height: 900 },
})
const page = await browser.newPage()
page.on('console', (message) => {
  if (message.type() === 'error') consoleErrors.push(message.text())
})
page.on('pageerror', (error) => pageErrors.push(String(error)))
page.on('requestfailed', (request) => consoleErrors.push(`request failed: ${request.url()} ${request.failure()?.errorText}`))

console.log('Planner walk-through')

await step(page, 'signed-out visitor is sent to the login page', async () => {
  await page.goto(APP_URL, { waitUntil: 'networkidle0' })
  expect(new URL(page.url()).pathname === '/login', `ended at ${page.url()}`)
  expect((await text(page)).includes('All data is synthetic (simulation)'), 'banner missing on login')
  await snap(page, 'login')
})

await step(page, 'wrong password shows a plain message', async () => {
  await page.type('input[type=email]', 'planner@blockplanner.test')
  await page.type('input[type=password]', 'definitely-wrong')
  await click(page, 'button[type=submit]')
  await waitText(page, 'That email and password do not match.')
})

await step(page, 'planner signs in and sees the dashboard', async () => {
  await signIn(page, 'planner@blockplanner.test')
  await waitText(page, 'No finished plan yet')
  const body = await text(page)
  expect(body.includes('submitted'), 'expected request counts by status')
  await snap(page, 'dashboard-empty')
})

await step(page, 'requests table lists the requests and the status filter works', async () => {
  await page.goto(`${APP_URL}/requests`, { waitUntil: 'networkidle0' })
  await page.waitForSelector('table.table tbody tr')
  expect((await page.$$('table.table tbody tr')).length === created, 'wrong number of rows')
  await page.select('select', 'draft')
  await waitText(page, 'No requests match')
  await page.select('select', 'submitted')
  await page.waitForSelector('table.table tbody tr')
  expect((await page.$$('table.table tbody tr')).length === created, 'submitted filter lost rows')
  await snap(page, 'requests')
})

await step(page, 'creating a request shows the server error under the right field', async () => {
  await click(page, 'button.btn-primary')
  await page.waitForSelector('[role=dialog]')
  // a planner must name the department; an empty date gets a plain local message ...
  await click(page, '[role=dialog] button[type=submit]')
  await page.waitForSelector('[role=dialog] .field-error')
  const local = await page.$$eval('[role=dialog] .field-error', (nodes) => nodes.map((n) => n.textContent))
  expect(local.includes('Choose a department'), `local errors were: ${local.join(' | ')}`)
  expect(local.includes('Choose the earliest date'), `local errors were: ${local.join(' | ')}`)
  await page.select('[role=dialog] select', 'SNT')
  // ... and the server's own rules are shown under the right field
  const dates = await page.$$('[role=dialog] input[type=date]')
  await setInput(dates[0], '2026-10-20')
  await setInput(dates[1], '2026-10-22')
  await fillByLabel(page, 'Duration (minutes)', '5', '[role=dialog]')
  await click(page, '[role=dialog] button[type=submit]')
  await waitText(page, 'greater than or equal to 15')
  const errors = await page.$$eval('[role=dialog] .field-error', (nodes) => nodes.map((n) => n.textContent))
  expect(errors.some((e) => e.includes('greater than or equal to 15')), `errors were: ${errors.join(' | ')}`)
  await snap(page, 'request-form-errors')
  await click(page, '[role=dialog] button[aria-label=Close]')
})

await step(page, 'planner creates a draft request for a department', async () => {
  await click(page, 'button.btn-primary')
  await page.waitForSelector('[role=dialog]')
  await page.select('[role=dialog] select', 'SNT')
  const dates = await page.$$('[role=dialog] input[type=date]')
  await setInput(dates[0], '2026-10-20')
  await setInput(dates[1], '2026-10-22')
  await click(page, '[role=dialog] button[type=submit]')
  await waitText(page, 'was created')
})

await step(page, 'planner runs a plan and it finishes', async () => {
  await page.goto(`${APP_URL}/plans`, { waitUntil: 'networkidle0' })
  await setInput(await page.$('input[type=date]'), HORIZON_START)
  await fillByLabel(page, 'Solver time limit', '10')
  await snap(page, 'plans-form')
  await click(page, 'button[type=submit]')
  await page.waitForFunction(() => document.querySelector('.run-status')?.innerText.includes('succeeded'), { timeout: 120000 })
  await snap(page, 'plans-run-done')
})

await step(page, 'plan detail: schedule tab draws the Gantt and shows member requests on hover', async () => {
  await click(page, '.run-status a')
  await page.waitForSelector('.gantt-svg')
  const blocks = await page.$$('.gantt-block')
  expect(blocks.length > 0, 'no closures drawn')
  await blocks[0].hover()
  await page.waitForSelector('[role=tooltip]')
  const tip = await page.$eval('[role=tooltip]', (n) => n.innerText)
  expect(/R\d+/.test(tip), `tooltip had no request: ${tip}`)
  await snap(page, 'plan-schedule')
})

await step(page, 'compare tab shows the chart and the table', async () => {
  await click(page, 'button[role=tab]::-p-text(Compare)')
  await page.waitForSelector('.recharts-wrapper svg')
  const body = await text(page)
  expect(body.includes('Independent') && body.includes('Integrated'), 'comparison labels missing')
  await snap(page, 'plan-compare')
})

await step(page, 'conflicts and explanations tabs show content', async () => {
  await click(page, 'button[role=tab]::-p-text(Conflicts)')
  await page.waitForSelector('article.conflict')
  await click(page, 'button[role=tab]::-p-text(Explanations)')
  await page.waitForSelector('article.explanation')
  const body = await text(page)
  expect(body.includes('MERGED') || body.includes('LOW_TRAFFIC'), 'no reason codes shown')
  await snap(page, 'plan-explanations')
})

await step(page, 'what-if shows the difference without saving', async () => {
  await click(page, 'button[role=tab]::-p-text(What-if)')
  await page.waitForSelector('button::-p-text(Try this move)')
  await click(page, 'button::-p-text(Try this move)')
  await page.waitForFunction(
    () => document.body.innerText.includes('What would change') || document.body.innerText.includes('Not possible'),
    { timeout: 60000 },
  )
  await snap(page, 'plan-whatif')
})

await step(page, 'approve asks for confirmation and then approves', async () => {
  await click(page, '[role=group][aria-label="Review actions"] button::-p-text(Approve)')
  await page.waitForSelector('[role=dialog]')
  await snap(page, 'plan-approve-dialog')
  await click(page, '[role=dialog] button.btn-primary')
  await page.waitForFunction(() => document.querySelector('h1 .badge')?.textContent === 'approved', { timeout: 20000 })
})

await step(page, 'publish asks for confirmation and then publishes', async () => {
  await click(page, '[role=group][aria-label="Review actions"] button::-p-text(Publish)')
  await page.waitForSelector('[role=dialog]')
  await click(page, '[role=dialog] button.btn-primary')
  await page.waitForFunction(() => document.querySelector('h1 .badge')?.textContent === 'published', { timeout: 20000 })
  await snap(page, 'plan-published')
})

await step(page, 'published calendar shows the closures', async () => {
  await page.goto(`${APP_URL}/calendar`, { waitUntil: 'networkidle0' })
  await page.waitForSelector('.cal-block')
  await snap(page, 'calendar')
})

await step(page, 'dashboard shows KPI cards and the comparison chart', async () => {
  await page.goto(APP_URL, { waitUntil: 'networkidle0' })
  await page.waitForSelector('.kpi')
  expect((await page.$$('.kpi')).length === 4, 'expected four KPI cards')
  const body = await text(page)
  // the label is upper-cased by CSS, so innerText returns it in capitals
  expect(/improvement vs independent\s*-?\d+%/i.test(body), 'improvement KPI missing')
  await page.waitForSelector('.recharts-wrapper svg')
  await snap(page, 'dashboard')
})

await step(page, 'a dead session sends the user to the login page', async () => {
  await page.evaluate(() => {
    sessionStorage.setItem('bp.access', 'garbage')
    sessionStorage.setItem('bp.refresh', 'garbage')
  })
  await page.goto(`${APP_URL}/requests`, { waitUntil: 'networkidle0' })
  await page.waitForFunction(() => location.pathname === '/login', { timeout: 15000 })
})

console.log('Viewer (read-only)')
await step(page, 'viewer cannot create requests or run plans', async () => {
  await signIn(page, 'viewer@blockplanner.test')
  await page.goto(`${APP_URL}/requests`, { waitUntil: 'networkidle0' })
  await page.waitForSelector('table.table')
  let body = await text(page)
  expect(body.includes('Read-only view'), 'no read-only notice')
  expect(!(await page.$('button.btn-primary')), 'viewer sees a primary action on requests')
  expect((await page.$$('td.actions button')).length === 0, 'viewer sees row actions')
  await page.goto(`${APP_URL}/plans`, { waitUntil: 'networkidle0' })
  body = await text(page)
  expect(body.includes('Only planners and administrators can run plans'), 'viewer sees the run form')
  await snap(page, 'viewer-plans')
})

await step(page, 'viewer can read a plan but has no review buttons', async () => {
  await page.waitForSelector('table.table a')
  await click(page, 'table.table a')
  await page.waitForSelector('.gantt-svg')
  const body = await text(page)
  expect(body.includes('Only planners and administrators can override, approve or publish'), 'missing role note')
  expect(!(await page.$('[role=group][aria-label="Review actions"]')), 'viewer sees review actions')
  await click(page, 'button[role=tab]::-p-text(What-if)')
  await waitText(page, 'Planners and administrators only')
})

console.log('Department user (Engineering)')
await step(page, 'department user can act only on their own department', async () => {
  await signIn(page, 'engg@blockplanner.test')
  await page.goto(`${APP_URL}/requests`, { waitUntil: 'networkidle0' })
  await page.waitForSelector('table.table tbody tr')
  const rows = await page.$$eval('table.table tbody tr', (trs) =>
    trs.map((tr) => ({
      dept: tr.querySelector('.chip')?.textContent.trim(),
      actions: [...tr.querySelectorAll('td.actions button')].map((b) => b.textContent.trim()),
    })),
  )
  const others = rows.filter((r) => r.dept !== 'ENGG')
  expect(others.length > 0, 'expected rows of other departments')
  expect(others.every((r) => r.actions.length === 0), 'department user can act on another department')
  expect(rows.some((r) => r.dept === 'ENGG'), 'no ENGG rows')
  expect((await page.$('button.btn-primary')), 'department user cannot create requests')
})

await browser.close()

// ---------- verdict ----------

// API errors the walk causes on purpose (422 form validation) show up as console messages.
const expected = (message) => /Failed to load resource: the server responded with a status of (4\d\d)/.test(message)
const realErrors = consoleErrors.filter((m) => !expected(m))
const failed = results.filter((r) => !r.ok)
console.log('')
console.log(`${results.length - failed.length}/${results.length} steps passed`)
console.log(`console errors: ${realErrors.length} (plus ${consoleErrors.length - realErrors.length} expected 4xx API responses)`)
console.log(`page errors: ${pageErrors.length}`)
for (const message of realErrors) console.log(`  console: ${message}`)
for (const message of pageErrors) console.log(`  page: ${message}`)
console.log(`screenshots: ${SHOTS.pathname}`)
process.exit(failed.length || realErrors.length || pageErrors.length ? 1 : 0)
