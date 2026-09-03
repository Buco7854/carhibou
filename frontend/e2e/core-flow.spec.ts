import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'

interface VehicleRecord { id: string; name: string }
interface Enrollment { token: string }
interface ProfileRecord { id: string; name: string }
interface AgentConfig { vehicle_profile: string | null; vehicle_profile_definition?: { signals?: Array<{ name: string }> } }
interface EnrolledAgent { agent_id: string; credential: string }
interface HookRecord { id: string }
interface HookExecution { status: string; logs: Array<Record<string, unknown>> }
interface DashboardWidgetRow { type: string; x: number; y: number; w: number; h: number }

const ONE_PIXEL_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2ZQAAAABJRU5ErkJggg==',
  'base64',
)

interface SampleInput {
  sequence: number
  recordedAt: string
  position: { latitude: number; longitude: number; altitude: number; speed: number; heading: number; accuracy: number }
  metrics: Record<string, number | boolean>
  agent: Record<string, number>
}

/**
 * One telemetry sample in the v2 observation wire model.
 *
 * A sample is an envelope of independent observations rather than a snapshot, so
 * every metric carries its own timestamp and the channel it came from, and the
 * fix travels whole with its own provenance. `(key, channel)` is unique within a
 * sample, so the CAN speed here and the GNSS speed on the fix are two candidates
 * the server resolves between rather than a conflict.
 */
function sample(input: SampleInput): Record<string, unknown> {
  return {
    id: randomUUID(),
    sequence: input.sequence,
    recorded_at: input.recordedAt,
    position: {
      value: input.position,
      observed_at: input.recordedAt,
      channel: 'gnss',
      method: 'direct',
    },
    observations: Object.entries(input.metrics).map(([key, value]) => ({
      key,
      value,
      observed_at: input.recordedAt,
      channel: 'can',
      method: 'direct',
    })),
    agent: input.agent,
  }
}

async function csrfToken(page: Page): Promise<string> {
  const cookies = await page.context().cookies()
  const csrf = cookies.find((cookie) => cookie.name === 'carhibou_csrf')?.value
  if (!csrf) throw new Error('browser session has no CSRF cookie')
  return csrf
}

async function browserJson<T>(page: Page, method: 'get' | 'post' | 'put', path: string, data?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (method !== 'get') headers['X-CSRF-Token'] = await csrfToken(page)
  const response = await page.request[method](path, { data, headers })
  expect(response.ok(), `${method.toUpperCase()} ${path}: ${await response.text()}`).toBeTruthy()
  return response.json() as Promise<T>
}

async function waitForExecutions(page: Page, hookId: string, count: number): Promise<HookExecution[]> {
  let rows: HookExecution[] = []
  await expect.poll(async () => {
    rows = await browserJson<HookExecution[]>(page, 'get', `/api/v1/hooks/${hookId}/executions`)
    return rows.filter((row) => row.status === 'success').length
  }, { timeout: 15_000 }).toBe(count)
  return rows
}

test('complete browser journey from bootstrapped admin to persistent hook state', async ({ page, request }) => {
  await page.goto('/login')
  await expect(page.getByRole('heading', { name: 'Sign in to Carhibou' })).toBeVisible()
  await expect(page.getByText('Open-source software · operated by you')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Create the initial administrator' })).toHaveCount(0)
  const loginAccessibility = await new AxeBuilder({ page }).analyze()
  expect(loginAccessibility.violations).toEqual([])

  await page.getByLabel('Email').fill('browser-owner@example.com')
  await page.getByLabel('Password').fill('browser-e2e-password-2026')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL('/')
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Overview/ })).toBeVisible()

  const rejectedRegistration = await request.post('/api/v1/auth/register', {
    data: {
      email: 'second-owner@example.com',
      password: 'another-browser-password-2026',
      display_name: 'Second Owner',
    },
  })
  expect(rejectedRegistration.status()).toBe(403)

  await page.getByRole('link', { name: 'Vehicles', exact: true }).click()
  await page.getByRole('button', { name: 'Add vehicle' }).click()
  await page.getByLabel('Name', { exact:true }).fill('Éclair')
  await page.getByRole('button', { name: 'Create vehicle' }).click()
  await expect(page.getByRole('heading', { name: 'Éclair' })).toBeVisible()
  await expect(page.getByRole('img', { name: 'No photo for Éclair' })).toBeVisible()
  await expect(page.locator('.vehicle-photo-placeholder .app-icon')).toBeVisible()
  // A vehicle with no telemetry states that plainly instead of drawing an empty
  // percentage gauge for a reading its agent may never produce.
  await expect(page.locator('.vehicle-card', { hasText:'Éclair' }).locator('.charge-reading'))
    .toHaveText('No telemetry reported yet')
  await expect(page.locator('.vehicle-card', { hasText:'Éclair' }).locator('.charge-reading i')).toHaveCount(0)
  const photoInput = page.locator('.vehicle-media input[type="file"]')
  await photoInput.focus()
  await expect(photoInput.locator('..')).toHaveCSS('outline-style', 'solid')
  const vehicleAccessibility = await new AxeBuilder({ page }).analyze()
  expect(vehicleAccessibility.violations).toEqual([])
  await page.evaluate(() => { document.documentElement.dataset.theme = 'dark' })
  await expect.poll(() => page.getByRole('heading', { name: 'Vehicles', exact: true }).evaluate((element) => getComputedStyle(element).color)).toBe('rgb(242, 242, 242)')
  await expect.poll(() => page.locator('html').evaluate((element) => getComputedStyle(element).filter)).toBe('none')
  const darkVehicleAccessibility = await new AxeBuilder({ page }).analyze()
  expect(darkVehicleAccessibility.violations).toEqual([])
  await page.evaluate(() => { document.documentElement.dataset.theme = 'light' })
  const cardHeightWithoutPhoto = await page.locator('.vehicle-card', { hasText:'Éclair' }).evaluate((card) => card.getBoundingClientRect().height)
  await photoInput.setInputFiles({
    name: 'eclair.png',
    mimeType: 'image/png',
    buffer: ONE_PIXEL_PNG,
  })
  await expect(page.getByText('Photo saved for Éclair.')).toBeVisible()
  const vehiclePhoto = page.locator('.vehicle-media img')
  await expect(vehiclePhoto).toBeVisible()
  expect(await vehiclePhoto.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBe(1)
  const cardHeightWithPhoto = await page.locator('.vehicle-card', { hasText:'Éclair' }).evaluate((card) => card.getBoundingClientRect().height)
  expect(Math.abs(cardHeightWithPhoto - cardHeightWithoutPhoto)).toBeLessThan(1)
  const [vehicle] = await browserJson<VehicleRecord[]>(page, 'get', '/api/v1/vehicles')
  expect(vehicle?.name).toBe('Éclair')
  await browserJson<VehicleRecord>(page, 'post', '/api/v1/vehicles', { name: 'Touring' })
  await page.reload()
  const secondVehicleCard = page.locator('.vehicle-card', { hasText: 'Touring' })
  await expect(secondVehicleCard).toBeVisible()
  await expect(secondVehicleCard.getByText(/Electric|Hybrid|Petrol|Diesel/)).toHaveCount(0)

  await page.locator('.sidebar').getByRole('link', { name:'Profiles', exact:true }).click()
  await expect(page.getByRole('heading', { name:'Telemetry profiles' })).toBeVisible()
  await page.getByRole('button', { name:'New CAN profile' }).click()
  await expect(page.getByRole('dialog', { name:'Create profile' })).toBeVisible()
  await page.getByRole('dialog', { name:'Create profile' }).getByRole('button', { name:'Add signal' }).click()
  await expect(page.getByRole('dialog', { name:'Add signal' })).toBeVisible()
  await page.getByRole('dialog', { name:'Add signal' }).getByRole('button', { name:'Close' }).click()
  await page.getByRole('dialog', { name:'Create profile' }).getByRole('button', { name:'Close' }).click()

  const profile = await browserJson<ProfileRecord>(page, 'post', '/api/v1/vehicle-profiles', {
    type: 'can',
    name: 'Browser decoder',
    description: 'Profile the browser flow enrolls its agent against',
    signals: [{
      name: 'battery.soc',
      display_name: 'Charge',
      source: { type: 'can', can_id: 0x374 },
      decoder: { byte_offset: 1, data_type: 'uint8', endianness: 'big', scale: 0.5, offset: -5 },
      unit: '%',
    }],
  })

  await page.getByRole('link', { name: 'Data sources' }).click()
  await page.getByRole('button', { name: 'Add agent' }).click()
  // The bundled implementation is preselected, and its hardware and setup style
  // are readable before a token is spent on it.
  await expect(page.locator('.implementation-card')).toContainText('Carhibou Go agent')
  await expect(page.locator('.implementation-card')).toContainText('One command')
  // The decoding profile is chosen on the agent now, so the estimate below it
  // follows the profile rather than the vehicle.
  await page.getByRole('combobox', { name: 'Decoding profile' }).click()
  await page.getByRole('option', { name: 'Browser decoder' }).click()
  const enrollmentResponse = page.waitForResponse((response) => response.url().includes('/enrollments') && response.request().method() === 'POST')
  await page.locator('.enrollment-panel').getByRole('button', { name: 'Add agent' }).click()
  const enrollment = await (await enrollmentResponse).json() as Enrollment
  await expect(page.locator('.setup-steps pre')).toContainText('--token')
  const copyCommand = page.getByRole('button', { name: 'Copy command' })
  await expect(copyCommand).toBeVisible()
  await expect(copyCommand).toHaveText('')
  await page.getByRole('dialog', { name:'Enroll an agent' }).getByRole('button', { name:'Close' }).first().click()

  const enrolledResponse = await request.post('/api/v1/agent/enroll', {
    data: { token: enrollment.token, implementation_id: 'carhibou.go', protocol_version: 2, agent_version: 'e2e-1.0.0', hostname: 'browser-simulator', hardware: { model: 'simulated-pi-zero' } },
  })
  expect(enrolledResponse.status()).toBe(201)
  const enrolled = await enrolledResponse.json() as EnrolledAgent
  const isolatedHumanRequest = await request.get('/api/v1/auth/me', { headers: { Authorization: `Agent ${enrolled.credential}` } })
  expect(isolatedHumanRequest.status()).toBe(401)

  // Profile delivery end to end: chosen in the browser, carried by the agent row,
  // handed to the agent with its decoding definition.
  const agentConfig = await request.get('/api/v1/agent/config', { headers: { Authorization: `Agent ${enrolled.credential}` } })
  expect(agentConfig.status()).toBe(200)
  const config = await agentConfig.json() as AgentConfig
  expect(config.vehicle_profile).toBe(profile.id)
  expect(config.vehicle_profile_definition?.signals?.[0]?.name).toBe('battery.soc')

  const samples = Array.from({ length: 6 }, (_, index) => sample({
    sequence: index,
    recordedAt: new Date(Date.now() - (5 - index) * 5_000).toISOString(),
    position: { latitude: 48.8566 + index * 0.002, longitude: 2.3522 + index * 0.003, speed: 24 + index * 7, heading: 35 + index * 8, altitude: 42, accuracy: 4.5 },
    metrics: { 'battery.soc': 82 - index, 'battery.pack_voltage': 330.5, 'battery.power': -11.8, 'charging.active': false, 'vehicle.speed': 24 + index * 7 },
    agent: { mobile_signal: -76, queue_depth: 0 },
  }))
  const bootId = randomUUID()
  const firstBatch = await request.post('/api/v1/agent/telemetry/batch', {
    headers: { Authorization: `Agent ${enrolled.credential}` },
    data: { boot_id: bootId, samples },
  })
  expect(firstBatch.status()).toBe(200)
  expect((await firstBatch.json()).accepted).toHaveLength(6)
  const retriedBatch = await request.post('/api/v1/agent/telemetry/batch', {
    headers: { Authorization: `Agent ${enrolled.credential}` },
    data: { boot_id: bootId, samples },
  })
  expect(retriedBatch.status()).toBe(200)
  expect((await retriedBatch.json()).duplicates).toHaveLength(6)

  await page.locator('.sidebar').getByRole('link', { name: 'Dashboards', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
  await expect(page.locator('[data-widget-type="battery-gauge"] .energy-value')).toHaveText('77')
  await expect(page.locator('.carhibou-position-marker')).toBeVisible()
  const initialDashboardAccessibility = await new AxeBuilder({ page }).analyze()
  expect(initialDashboardAccessibility.violations).toEqual([])

  const vehicleSelector = page.locator('[data-widget-type="vehicle-selector"]')
  await expect(vehicleSelector.getByRole('combobox')).toHaveCount(1)
  await vehicleSelector.getByRole('combobox').click()
  await page.getByPlaceholder('Search vehicles…').fill('Touring')
  await expect(page.getByRole('option')).toHaveCount(1)
  await page.getByRole('option', { name:'Touring', exact:true }).click()
  // Only the cards needing non-standard data hide: battery state, charging, a
  // charge curve, a photo. Cards built out of drives and charges hide with them,
  // because deriving either takes more than a vehicle merely reporting and a
  // card that can only say it found none is claiming something about the car.
  // Speed is standard, so both speed cards stay.
  for (const type of ['battery-gauge', 'charging', 'xy-chart', 'vehicle-media', 'telemetry-list',
    'activity-feed', 'segment-stats', 'period-stats']) {
    await expect(page.locator(`[data-widget-type="${type}"]`), type).toHaveCount(0)
  }
  // This vehicle has neither a CAN reading nor a fix yet, so the speed card says
  // so like any other card rather than vanishing.
  await expect(page.locator('[data-widget-type="metric-card"] .dashboard-widget-empty')).toContainText('No data yet')
  for (const type of ['vehicle-selector', 'online-status', 'metric-card', 'route-map', 'time-series']) {
    await expect(page.locator(`[data-widget-type="${type}"]`), type).toHaveCount(1)
  }
  await expect(page.locator('.grid-stack-item')).toHaveCount(5)
  await expect(page.locator('[data-widget-type="position-map"] .vehicle-map')).toHaveCount(0)
  await vehicleSelector.getByRole('combobox').click()
  await page.getByPlaceholder('Search vehicles…').fill('Éclair')
  await page.getByRole('option', { name:/Éclair/ }).click()
  await expect(page.locator('[data-widget-type="battery-gauge"] .energy-value')).toHaveText('77')
  // The EV reports battery state too, so the non-standard cards come back with it.
  for (const type of ['metric-card', 'charging', 'time-series', 'xy-chart']) {
    await expect(page.locator(`[data-widget-type="${type}"]`), type).toHaveCount(1)
  }
  // Every card in the preset is up. The photo is not one of them: it is decoration
  // rather than telemetry, and the Vehicles page already shows it.
  await expect(page.locator('[data-widget-type="vehicle-media"]')).toHaveCount(0)
  await expect(page.locator('.grid-stack-item')).toHaveCount(12)

  const liveSample = sample({
    sequence: 6,
    recordedAt: new Date().toISOString(),
    position: { latitude: 48.87, longitude: 2.37, speed: 18, heading: 102, altitude: 43, accuracy: 3.8 },
    metrics: { 'battery.soc': 61, 'battery.pack_voltage': 329.1, 'battery.power': -4.2, 'charging.active': false, 'vehicle.speed': 18 },
    agent: { mobile_signal: -73, queue_depth: 0 },
  })
  const liveBatch = await request.post('/api/v1/agent/telemetry/batch', {
    headers: { Authorization: `Agent ${enrolled.credential}` },
    data: { boot_id: bootId, samples: [liveSample] },
  })
  expect(liveBatch.status()).toBe(200)
  await page.reload()
  await expect(page.locator('[data-widget-type="battery-gauge"] .energy-value')).toHaveText('61')

  const dashboardAccessibility = await new AxeBuilder({ page }).analyze()
  expect(dashboardAccessibility.violations).toEqual([])
  await page.getByTitle('Theme').click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await expect.poll(() => page.getByRole('heading', { name: 'Overview' }).evaluate((element) => getComputedStyle(element).color)).toBe('rgb(242, 242, 242)')
  const darkDashboardAccessibility = await new AxeBuilder({ page }).analyze()
  expect(darkDashboardAccessibility.violations).toEqual([])
  await page.getByTitle('Theme').click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')

  await page.getByRole('link', { name: 'Vehicles', exact: true }).click()
  await page.locator('.vehicle-card', { hasText:'Éclair' }).getByRole('link', { name:'History' }).click()
  await expect(page.getByRole('heading', { name: 'Éclair · History' })).toBeVisible()

  // History opens on the timeline, which is what somebody means by history
  // before anyone explains how the data is stored.
  await expect(page.getByRole('button', { name: 'Timeline' })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('.snapshot tbody tr').first()).toBeVisible()
  // The step is chosen from the range, so nothing has to be understood first.
  await expect(page.locator('.history-table .app-select-trigger')).toContainText('5 minutes')
  // The help is a real button reachable and operable by keyboard, not a hover tip.
  const aged = page.locator('.history-table .app-help-button').first()
  await aged.focus()
  await expect(aged).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.locator('.app-help-bubble')).toContainText('dimmed')
  const helpAccessibility = await new AxeBuilder({ page }).analyze()
  expect(helpAccessibility.violations).toEqual([])
  await page.keyboard.press('Escape')
  await expect(page.locator('.app-help-bubble')).toHaveCount(0)

  await page.getByRole('button', { name: 'Raw reports' }).click()
  await expect(page.locator('.history-stat', { hasText:'Reports' })).toContainText('7')
  await expect(page.locator('.route-count')).toContainText('7')
  expect(await page.locator('select').count()).toBe(0)
  await page.getByRole('combobox', { name:'Metric' }).click()
  const metricMenu = page.locator('.app-select-menu')
  await expect(metricMenu).toBeVisible()
  const menuBounds = await metricMenu.boundingBox()
  expect(menuBounds).not.toBeNull()
  expect(menuBounds!.x + menuBounds!.width).toBeLessThanOrEqual(await page.evaluate(() => window.innerWidth))
  await page.keyboard.press('Escape')

  // Provenance comes from /observations, a different endpoint from the grid's, so
  // this is the only check that a row's detail resolves against the real one.
  await page.locator('.entries-section tbody .expand-cell button').first().click()
  await expect(page.locator('.provenance')).toBeVisible()
  await expect(page.locator('.provenance-facts')).toContainText('Agent')
  await expect(page.locator('.provenance-table')).toContainText('CAN')
  await expect(page.locator('.provenance-table')).toContainText('GNSS')
  const provenanceAccessibility = await new AxeBuilder({ page }).analyze()
  expect(provenanceAccessibility.violations).toEqual([])
  await page.locator('.entries-section tbody .expand-cell button').first().click()
  await expect(page.locator('.provenance')).toHaveCount(0)

  // The snapshot table is served by the reconstruction endpoint, so this is the
  // only check that the rows the server computes are the rows the page can read.
  await page.getByRole('button', { name: 'Timeline' }).click()
  await expect(page.getByRole('heading', { name: 'Timeline' })).toBeVisible()
  const snapshotRows = page.locator('.snapshot tbody tr')
  await expect(snapshotRows.first()).toBeVisible()
  // Newest first, and every row carries the whole car rather than one sample.
  await expect(page.locator('.snapshot thead th')).toContainText(['Time', 'Position'])
  await expect(snapshotRows.first()).toContainText('61')
  // Coarsening the step is a different question, and the server answers it.
  await page.getByRole('combobox', { name: 'One row per' }).click()
  await page.getByRole('option', { name: '1 hour' }).click()
  await expect(snapshotRows.first()).toBeVisible()
  const tableAccessibility = await new AxeBuilder({ page }).analyze()
  expect(tableAccessibility.violations).toEqual([])
  // The choice is remembered, so a reader who prefers the raw reports keeps them.
  await page.getByRole('button', { name: 'Raw reports' }).click()
  await expect(page.locator('.history-chart')).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: 'Raw reports' })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('.history-chart')).toBeVisible()

  await page.locator('.sidebar').getByRole('link', { name: 'Dashboards', exact: true }).click()
  await page.getByRole('button', { name: 'Dashboard actions' }).click()
  await page.getByRole('menuitem', { name: 'New dashboard' }).click()
  await page.locator('.app-modal').getByLabel('Dashboard name').fill('Diagnostics')
  await page.getByRole('button', { name: 'Create dashboard' }).click()
  await page.getByRole('button', { name: 'Add widget' }).click()
  await page.getByLabel('Title').fill('Battery at a glance')
  await page.locator('.app-modal').getByRole('button', { name: 'Add widget' }).click()
  await expect(page.getByText('Battery at a glance')).toBeVisible()
  await page.getByRole('button', { name: 'Make default' }).click()
  await page.getByRole('button', { name: 'Save', exact:true }).click()
  await expect(page.getByText('Dashboard saved.')).toBeVisible()
  await expect(page.getByRole('button', { name:'Dashboard actions' })).toBeVisible()
  await expect(page.locator('.widget-remove')).toHaveCount(0)
  await page.reload()
  await expect(page.getByText('Battery at a glance')).toBeVisible()
  await expect(page.getByRole('button', { name: /Diagnostics.*Default/ })).toBeVisible()

  const hooksLoaded = page.waitForResponse((response) => response.url().endsWith('/api/v1/hooks') && response.request().method() === 'GET')
  await page.getByRole('link', { name: 'Hooks' }).click()
  await hooksLoaded
  await page.locator('.page-header').getByRole('button', { name: 'New hook' }).click()
  // Creation asks for what only a person can supply, and hands the rest to the
  // detail panel: writing Python in a sheet is what the panel behind it is for.
  const hookModal = page.locator('.app-modal')
  await hookModal.getByLabel('Name', { exact:true }).fill('Browser state counter')
  await hookModal.getByLabel('Description').fill('Verifies persistent hook state through the browser flow')
  await expect(hookModal.locator('.cm-content')).toHaveCount(0)
  await hookModal.getByRole('button', { name: 'Create and edit' }).click()
  // The view closes this modal and refreshes its list only after the POST it
  // awaits resolves, so both are evidence the hook is committed. Reading the API
  // straight off the click raced the insert and saw an empty collection.
  await expect(hookModal).toBeHidden()
  await expect(page.locator('.hook-list').getByRole('button', { name: /Browser state counter/ })).toBeVisible()
  const [hook] = await browserJson<HookRecord[]>(page, 'get', '/api/v1/hooks')
  expect(hook?.id).toBeTruthy()

  // The new hook is already selected, so the code goes in where there is room.
  await expect(page.locator('.detail-identity h2')).toHaveText('Browser state counter')
  await page.locator('.hook-detail .cm-content').fill('ctx.state["runs"] = ctx.state.get("runs", 0) + 1\nctx.log.info("browser e2e", runs=ctx.state["runs"], dry_run=ctx.dry_run)')
  await page.locator('.detail-actions').getByRole('button', { name: 'Save', exact: true }).click()
  await expect(page.getByText('Saved')).toBeVisible()

  await page.getByRole('button', { name: 'Test with telemetry' }).click()
  await waitForExecutions(page, hook.id, 1)
  await page.getByRole('button', { name: 'Test with telemetry' }).click()
  const executions = await waitForExecutions(page, hook.id, 2)
  expect(JSON.stringify(executions[0]?.logs)).toContain('"runs":2')
  await page.reload()
  await page.locator('.hook-list').getByRole('button', { name: /Browser state counter/ }).click()
  await expect(page.getByText('success').first()).toBeVisible()

  await page.getByRole('link', { name: 'Data sources' }).click()
  await expect(page.getByRole('heading', { name: 'Vehicle agent' })).toBeVisible()
  // The row carries what identifies the agent and how it is doing; the build it
  // runs is one of the facts behind the disclosure.
  await expect(page.getByText('e2e-1.0.0')).toHaveCount(0)
  await page.getByRole('button', { name: 'Details' }).first().click()
  await expect(page.getByText('e2e-1.0.0')).toBeVisible()

  await page.setViewportSize({ width: 375, height: 812 })
  await page.locator('.sidebar').getByRole('link', { name: 'Dashboards', exact: true }).click()
  await page.getByRole('button', { name: /Overview/ }).click()
  await expect(page.locator('[data-widget-type="battery-gauge"] .energy-widget')).toBeVisible()
  const badgeGeometry = await page.locator('.status').evaluateAll((badges) => badges.map((badge) => {
    const bounds = badge.getBoundingClientRect()
    return { radius: getComputedStyle(badge).borderRadius, width: bounds.width, height: bounds.height }
  }))
  expect(badgeGeometry.length).toBeGreaterThan(0)
  expect(badgeGeometry.every((badge) => badge.radius === '6px' && badge.width > badge.height)).toBeTruthy()
  const mobileDimensions = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, viewport: window.innerWidth }))
  expect(mobileDimensions.scroll).toBeLessThanOrEqual(mobileDimensions.viewport)

  // Leaflet numbers its own panes from 200 to 700 and its controls up to 1000,
  // as plain z-indexes. The nav sits at 60, so unless the map keeps those
  // numbers inside a stacking context of its own they outrank the chrome and
  // the bar disappears under the tiles.
  const mapFrame = page.locator('.map-frame').first()
  await expect(mapFrame).toBeVisible()
  expect(await mapFrame.evaluate((frame) => getComputedStyle(frame).isolation)).toBe('isolate')

  /*
   * One vehicle on the map, not two.
   *
   * The route ends where the car is, so drawing both an end marker and the
   * position marker put two dots a stone's throw apart, one carrying a heading
   * needle and one not. A reader read that as two vehicles. The renderer paints
   * the endpoints into a canvas, so this asks it what it actually drew rather
   * than counting DOM nodes that no longer exist.
   */
  await expect(page.locator('.map-frame .carhibou-position-marker')).toHaveCount(1)
  const drawn = await page.evaluate(() => {
    const container = document.querySelector('.map-frame .vehicle-map') as unknown as {
      carhibouMap?: {
        queryRenderedFeatures: (box?: unknown, options?: { layers?: string[] }) => Array<{ properties?: Record<string, unknown> }>
      }
    }
    const map = container?.carhibouMap
    if (!map) return null
    const endpoints = map.queryRenderedFeatures(undefined, { layers: ['carhibou-endpoint'] })
    return { kinds: endpoints.map((feature) => String(feature.properties?.['kind'])) }
  })
  expect(drawn, 'the map exposes what it drew').not.toBeNull()
  expect(drawn!.kinds, 'no end marker while the car itself marks the end').not.toContain('end')

  /*
   * Sharpness, the vector equivalent of the old retina check: the drawing
   * surface carries one backing pixel per device pixel, so nothing is upscaled.
   */
  const surface = await page.evaluate(() => {
    const canvas = document.querySelector('.map-frame canvas.maplibregl-canvas') as HTMLCanvasElement | null
    if (!canvas) return null
    return { backing: canvas.width, css: Math.round(canvas.getBoundingClientRect().width), dpr: window.devicePixelRatio }
  })
  expect(surface, 'the map renders to a canvas').not.toBeNull()
  expect(surface!.backing).toBeGreaterThanOrEqual(Math.floor(surface!.css * surface!.dpr * 0.9))

  // The map opens to the whole viewport and closes again on Escape.
  await mapFrame.locator('.map-expand').click()
  await expect(page.locator('.map-frame.expanded')).toHaveCount(1)
  await expect(page.locator('.map-placeholder')).toHaveCount(1)
  await page.keyboard.press('Escape')
  await expect(page.locator('.map-frame.expanded')).toHaveCount(0)
  const overMap = await page.evaluate(() => {
    const frame = document.querySelector('.map-frame')!
    const nav = document.querySelector('.sidebar')!
    // Bring the map under the fixed bar, which is the one place on a phone
    // where chrome and map genuinely share pixels.
    frame.scrollIntoView({ block: 'end' })
    const navBox = nav.getBoundingClientRect()
    const mapBox = frame.getBoundingClientRect()
    const left = Math.max(navBox.left, mapBox.left)
    const right = Math.min(navBox.right, mapBox.right)
    const top = Math.max(navBox.top, mapBox.top)
    const bottom = Math.min(navBox.bottom, mapBox.bottom)
    if (left >= right || top >= bottom) return { overlaps: false, insideNav: false, insideMap: false }
    const hit = document.elementFromPoint(Math.round((left + right) / 2), Math.round((top + bottom) / 2))
    return { overlaps: true, insideNav: !!hit && nav.contains(hit), insideMap: !!hit && frame.contains(hit) }
  })
  expect(overMap.overlaps, 'the map has to reach under the nav bar for this to prove anything').toBe(true)
  expect(overMap.insideNav, 'the nav bar must paint above the map').toBe(true)
  expect(overMap.insideMap).toBe(false)

  // Every floating layer rides on the same fact: once the map holds its own
  // stacking context, anything the app raises at all sits above it. The nav
  // sheet covers the viewport, so its backdrop and the map always share pixels.
  await page.getByRole('button', { name: 'More' }).click()
  const overlayOverMap = await page.evaluate(() => {
    const frame = document.querySelector('.map-frame')!
    const backdrop = document.querySelector('.nav-sheet-backdrop')!
    const sheet = document.querySelector('.nav-sheet')!
    const box = frame.getBoundingClientRect()
    const hit = document.elementFromPoint(Math.round((box.left + box.right) / 2), Math.round((box.top + box.bottom) / 2))
    // Either half of the overlay may be the one over this point, depending on
    // where the map sits; what matters is that the map is not.
    return { onOverlay: hit === backdrop || (!!hit && sheet.contains(hit)), insideMap: !!hit && frame.contains(hit) }
  })
  expect(overlayOverMap.onOverlay, 'a floating layer must paint above the map').toBe(true)
  expect(overlayOverMap.insideMap).toBe(false)
  // The backdrop covers the bar that opened the sheet, so it is also the way out.
  await page.locator('.nav-sheet-backdrop').click({ position: { x: 40, y: 40 } })
  await expect(page.locator('.nav-sheet')).toHaveCount(0)

  await page.getByRole('link', { name: 'Vehicles', exact: true }).click()
  await expect(page.locator('.vehicle-card').first()).toBeVisible()
  await expect(page.locator('.vehicle-card img')).toBeVisible()
  const mobileGarageDimensions = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, viewport: window.innerWidth }))
  expect(mobileGarageDimensions.scroll).toBeLessThanOrEqual(mobileGarageDimensions.viewport)
})

/**
 * Every canonical key this build names in its own catalogues, so a note or a
 * label kept for a key the server has dropped can be caught against the running
 * registry rather than against another copy of the same assumption.
 */
function canonicalKeysNamedByTheInterface(): { notes: string[]; labels: string[] } {
  const english = readFileSync(new URL('../src/i18n/locales/en.ts', import.meta.url), 'utf8')
  const display = readFileSync(new URL('../src/vehicleDisplay.ts', import.meta.url), 'utf8')
  const notesBlock = /metricNotes: \{(.*?)\},\n/s.exec(english)?.[1] ?? ''
  // The notes are keyed with underscores because vue-i18n reads a dot as a step
  // into a nested message. That flattening is lossy, so the comparison happens
  // in the flattened space rather than by guessing where the dots were.
  const notes = [...notesBlock.matchAll(/'([a-z0-9_]+)':/g)].map((match) => match[1]!)
  const labels = [...display.matchAll(/key: '([a-z][a-z0-9_]*\.[a-z0-9_.]+)'/g)].map((match) => match[1]!)
  return { notes, labels }
}

test('a test run picks the newest sample that actually carries something', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill('browser-owner@example.com')
  await page.getByLabel('Password').fill('browser-e2e-password-2026')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL('/')

  const vehicle = await browserJson<VehicleRecord>(page, 'post', '/api/v1/vehicles', { name: 'Parked saloon' })
  const enrollment = await browserJson<Enrollment>(page, 'post', `/api/v1/vehicles/${vehicle.id}/enrollments`, { implementation_id: 'carhibou.go' })
  const enrolled = await browserJson<EnrolledAgent>(page, 'post', '/api/v1/agent/enroll', {
    token: enrollment.token, implementation_id: 'carhibou.go', protocol_version: 2,
    agent_version: 'e2e-1.0.0', hostname: 'parked-simulator', hardware: {},
  })

  /*
   * What a parked car on the delta wire actually stores: something real, and
   * then heartbeats carrying nothing at all. The newest sample is the emptiest
   * one, which is the whole point of this test.
   */
  const carrying = randomUUID()
  const heartbeat = randomUUID()
  const earlier = new Date(Date.now() - 120_000).toISOString()
  const later = new Date(Date.now() - 30_000).toISOString()
  const batch = await page.request.post('/api/v1/agent/telemetry/batch', {
    headers: { Authorization: `Agent ${enrolled.credential}` },
    data: { boot_id: randomUUID(), samples: [
      { id: carrying, sequence: 1, recorded_at: earlier,
        position: { value: { latitude: 48.85, longitude: 2.35, speed: 0, heading: 0, altitude: 40, accuracy: 5 }, observed_at: earlier, channel: 'gnss', method: 'direct' },
        observations: [{ key: 'battery.soc', value: 64, observed_at: earlier, channel: 'can', method: 'direct' }],
        agent: {} },
      { id: heartbeat, sequence: 2, recorded_at: later, position: null, observations: [], agent: { queue_depth: 0 } },
    ] },
  })
  expect(batch.status(), await batch.text()).toBe(200)
  expect((await batch.json()).accepted).toHaveLength(2)

  // The server really did store the empty one, and really did store it newest.
  const stored = await browserJson<{ samples: Array<{ id: string; observations: unknown[]; position: unknown }> }>(
    page, 'get', `/api/v1/vehicles/${vehicle.id}/history/observations?limit=10`)
  expect(stored.samples[0]?.id).toBe(heartbeat)
  expect(stored.samples[0]?.observations).toHaveLength(0)
  expect(stored.samples[0]?.position).toBeNull()

  const hook = await browserJson<HookRecord>(page, 'post', '/api/v1/hooks', {
    name: 'Needs triggering', description: '', enabled: false, trigger_type: 'telemetry.received',
    vehicle_id: vehicle.id, timeout_seconds: 10,
    // The guard the Traccar example uses, and the one that made this look broken.
    source: 'if not ctx.telemetry.triggering:\n    return\nctx.log.info("saw", count=len(ctx.telemetry.triggering))\n',
  })

  await page.goto('/hooks')
  await page.locator('.hook-list').getByRole('button', { name: /Needs triggering/ }).click()
  await expect(page.locator('.detail-identity h2')).toHaveText('Needs triggering')

  const testPost = page.waitForRequest((request) =>
    request.url().includes(`/hooks/${hook.id}/test`) && request.method() === 'POST')
  await page.getByRole('button', { name: 'Test with telemetry' }).click()
  const chosen = JSON.parse((await testPost).postData() ?? '{}')
  // The heartbeat is newer. Choosing it gives the hook nothing to trigger on.
  expect(chosen.telemetry_id, 'the test must not run on a bare heartbeat').toBe(carrying)
  expect(chosen.telemetry_id).not.toBe(heartbeat)

  const executions = await waitForExecutions(page, hook.id, 1)
  // Triggering is the sample's observations plus its position, so the count the
  // hook saw is derived from what the server stored rather than written out.
  const source = stored.samples.find((sample) => sample.id === carrying)!
  const carried = source.observations.length + (source.position ? 1 : 0)
  expect(carried).toBeGreaterThan(0)
  expect(JSON.stringify(executions[0]?.logs)).toContain(`"count":${carried}`)
})

test('a run that logged nothing says so rather than showing an empty cell', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill('browser-owner@example.com')
  await page.getByLabel('Password').fill('browser-e2e-password-2026')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL('/')

  const [vehicle] = await browserJson<VehicleRecord[]>(page, 'get', '/api/v1/vehicles')
  const hook = await browserJson<HookRecord>(page, 'post', '/api/v1/hooks', {
    name: 'Says nothing', description: '', enabled: false, trigger_type: 'telemetry.received',
    vehicle_id: vehicle!.id, source: 'return\n', timeout_seconds: 10,
  })

  await page.goto('/hooks')
  await page.locator('.hook-list').getByRole('button', { name: /Says nothing/ }).click()
  await page.getByRole('button', { name: 'Test with telemetry' }).click()
  await waitForExecutions(page, hook.id, 1)

  // An em dash in the logs column is indistinguishable from a page that failed
  // to draw, which is how a working hook got read as broken.
  const row = page.locator('.runs-table tbody tr').first()
  await expect(row.locator('.quiet-run')).toHaveText('Completed with no output')
  await expect(row.locator('details')).toHaveCount(0)
})

test('the hook list carries what tells hooks apart, and a hook can be deleted', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill('browser-owner@example.com')
  await page.getByLabel('Password').fill('browser-e2e-password-2026')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL('/')

  const [vehicle] = await browserJson<VehicleRecord[]>(page, 'get', '/api/v1/vehicles')
  const make = (name: string, description: string, enabled: boolean, scoped: boolean) =>
    browserJson<HookRecord>(page, 'post', '/api/v1/hooks', {
      name, description, enabled, trigger_type: 'telemetry.received',
      vehicle_id: scoped ? vehicle!.id : null, source: 'return\n', timeout_seconds: 10,
    })
  const described = await make('Zulu described hook', 'Explains itself in a sentence', true, false)
  const bare = await make('Zulu bare hook', '', false, false)
  await make('Zulu scoped hook', '', true, true)
  // One that has run and failed, so the list has all three states to show.
  const broken = await browserJson<HookRecord>(page, 'post', '/api/v1/hooks', {
    name: 'Zulu failing hook', description: '', enabled: true, trigger_type: 'telemetry.received',
    vehicle_id: null, source: 'raise RuntimeError("upstream refused")\n', timeout_seconds: 10,
  })
  const recent = await browserJson<{ samples: Array<{ id: string }> }>(
    page, 'get', `/api/v1/vehicles/${vehicle!.id}/history/observations?limit=5`)
  await browserJson(page, 'post', `/api/v1/hooks/${broken.id}/test`, { telemetry_id: recent.samples[0]!.id, dry_run: true })
  await expect.poll(async () => {
    const rows = await browserJson<Array<{ id: string; last_execution: { status: string } | null }>>(page, 'get', '/api/v1/hooks')
    return rows.find((hook) => hook.id === broken.id)?.last_execution?.status
  }, { timeout: 15_000 }).toBe('failed')
  // Enough of its own that the filter appears whatever other tests left behind.
  for (let index = 0; index < 6; index += 1) await make(`Zulu filler ${index}`, '', false, false)

  await page.goto('/hooks')
  const row = (name: string) => page.locator('.hook-row', { hasText: name })

  // A hook that is on and one that is off are told apart without a word for it,
  // and nothing is left to colour alone.
  await expect(row('Zulu described hook')).not.toHaveClass(/\boff\b/)
  await expect(row('Zulu bare hook')).toHaveClass(/\boff\b/)
  await expect(row('Zulu bare hook')).toContainText('Disabled')

  // Never run, ran, and ran and failed are three different things, and the row
  // says which without the reader opening the hook.
  await expect(row('Zulu described hook').locator('.hook-run')).toHaveText('Never run')
  await expect(row('Zulu described hook')).not.toHaveClass(/failing/)
  await expect(row('Zulu failing hook')).toHaveClass(/failing/)
  await expect(row('Zulu failing hook').locator('.hook-run')).toContainText('Failed')
  // Both facts the dot carries reach a reader who cannot see it.
  await expect(row('Zulu failing hook')).toContainText('Enabled, Failed')
  await expect(row('Zulu bare hook')).toContainText('Disabled, Never run')

  // "All vehicles" is the default and said nothing, so it no longer takes the
  // only line a row has; what the author wrote does.
  await expect(row('Zulu described hook').locator('.hook-note')).toHaveText('Explains itself in a sentence')
  await expect(row('Zulu bare hook').locator('.hook-note')).toHaveCount(0)
  await expect(row('Zulu scoped hook').locator('.hook-note')).toHaveText(vehicle!.name)

  // Past a handful of hooks the list is filtered rather than read through.
  await expect(page.locator('.hook-filter input')).toBeVisible()
  await page.locator('.hook-filter input').fill('Zulu described')
  await expect(page.locator('.hook-row')).toHaveCount(1)
  // It reads the description too, not only the name.
  await page.locator('.hook-filter input').fill('Explains itself')
  await expect(page.locator('.hook-row')).toHaveCount(1)
  await page.locator('.hook-filter input').fill('')

  // Deleting: behind the overflow, confirmed by name, and honest about the cost.
  await row('Zulu described hook').click()
  await expect(page.locator('.detail-identity h2')).toHaveText('Zulu described hook')
  await page.locator('.detail-actions').getByRole('button', { name: /More actions/ }).click()
  await page.getByRole('menuitem', { name: 'Delete' }).click()
  const confirm = page.getByRole('dialog', { name: 'Delete hook' })
  await expect(confirm).toContainText('Zulu described hook')
  await expect(confirm).toContainText('revision history')
  await confirm.getByRole('button', { name: 'Delete hook' }).click()

  await expect(row('Zulu described hook')).toHaveCount(0)
  const left = await browserJson<HookRecord[]>(page, 'get', '/api/v1/hooks')
  expect(left.some((hook) => hook.id === described.id)).toBe(false)
  expect(left.some((hook) => hook.id === bare.id)).toBe(true)
  // The panel lands on a neighbour rather than emptying, which would read as
  // the page having lost everything.
  await expect(page.locator('.detail-identity h2')).toBeVisible()
})

test('every canonical key the interface names is one the server still knows', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill('browser-owner@example.com')
  await page.getByLabel('Password').fill('browser-e2e-password-2026')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL('/')

  const registry = await browserJson<{
    metrics: Array<{ key: string }>
    position?: { fields: Array<{ key: string }> }
  }>(page, 'get', '/api/v1/metrics/registry')
  const known = new Set<string>(registry.metrics.map((metric) => metric.key))
  // A fix is described separately and is not a metric, but position.speed is a
  // real thing to hold a note about, so its fields count as known.
  for (const field of registry.position?.fields ?? []) known.add(`position.${field.key}`)
  expect(known.size).toBeGreaterThan(20)

  const { notes, labels } = canonicalKeysNamedByTheInterface()
  expect(notes.length).toBeGreaterThan(0)
  expect(labels.length).toBeGreaterThan(0)
  // Agent-map keys are not registry metrics and live in their own catalogue, so
  // anything left in the metric notes has to be a key the server publishes.
  const knownFlat = new Set([...known].map((key) => key.replaceAll('.', '_')))
  expect(notes.filter((key) => !knownFlat.has(key)), 'metric notes for keys the registry no longer has').toEqual([])

  /*
   * Keys the agent publishes today that the registry does not define yet: the
   * OBD-II PIDs decoded in agent/internal/providers/obd.go, the readiness metric
   * agent/internal/runtime/activity.go votes on, and the adapter's own supply
   * voltage. A display name for them is the only thing that makes them readable,
   * so the names stay and this list names the gap instead of hiding it. It is a
   * list, not a pattern, so a name invented for a key nobody sends still fails.
   */
  const awaitingRegistry = new Set<string>([])
  expect(
    labels.filter((key) => !known.has(key) && !awaitingRegistry.has(key)),
    'display names for keys neither the registry nor the known gap accounts for',
  ).toEqual([])
  // The gap is meant to shrink: once the server defines one of these, its entry
  // here is dead and has to go.
  expect([...awaitingRegistry].filter((key) => known.has(key)), 'gap entries the registry now covers').toEqual([])
})

test('mobile login keeps language, theme, keyboard access and reflow', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' })
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'languages', { configurable:true, get:() => ['fr-FR', 'en-US'] })
  })
  await page.goto('/login')
  await expect(page.getByRole('heading', { name: 'Connectez-vous à Carhibou' })).toBeVisible()

  await page.keyboard.press('Tab')
  const language = page.locator('.login-utilities [role="combobox"]')
  await expect(language).toBeFocused()
  await language.click()
  await page.getByRole('option', { name: 'EN' }).click()
  await language.click()
  await page.getByRole('option', { name: 'FR' }).click()
  await expect(page.getByRole('heading', { name: 'Connectez-vous à Carhibou' })).toBeVisible()
  await page.getByTitle('Thème').click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  const dimensions = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, viewport: window.innerWidth }))
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.viewport)

  // Two long labels side by side set a width the page could not go below, so a
  // French header pushed the whole page past the viewport and the phone zoomed
  // out to fit it. Every page is checked in the longer language.
  await page.getByLabel('E-mail').fill('browser-owner@example.com')
  await page.getByLabel('Mot de passe').fill('browser-e2e-password-2026')
  await page.getByRole('button', { name: 'Se connecter' }).click()
  await expect(page).toHaveURL('/')
  // The hooks page only overflowed once a hook was selected: the overflow is in
  // the detail panel's action row, and the page without one never renders it.
  // A sweep that visits the empty page reports it fitting and is telling the
  // truth about a state nobody with a hook ever sees.
  await browserJson(page, 'post', '/api/v1/hooks', {
    name: 'Sonde de mise en page', description: '', enabled: false,
    trigger_type: 'telemetry.received', vehicle_id: null, source: 'return\n', timeout_seconds: 10,
  })
  for (const path of ['/profiles', '/vehicles', '/data-sources', '/settings', '/hooks']) {
    await page.goto(path)
    await expect(page.locator('.page-header h1')).toBeVisible()
    const fits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
    expect(fits, `${path} overflows the phone viewport`).toBe(true)
  }

  // Map style is independent from interface theme. Following the interface
  // gives each tone its own provider style; fixed mode intentionally keeps one
  // style even when the interface changes.
  await page.goto('/settings')
  const mapMode = page.getByLabel('Comportement des cartes')
  await expect(mapMode).toContainText('Suivre l’interface')
  await expect(page.getByLabel('Avec l’interface claire')).toContainText('Liberty')
  await expect(page.getByLabel('Avec l’interface sombre')).toContainText('Dark')
  await mapMode.click()
  await page.getByRole('option', { name: 'Toujours utiliser un style' }).click()
  const fixedMapStyle = page.getByLabel('Style du fournisseur')
  await fixedMapStyle.click()
  await page.getByRole('option', { name: 'Fiord' }).click()
  await expect(fixedMapStyle).toContainText('Fiord')
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('carhibou.map-preferences') ?? '{}')))
    .toMatchObject({ providerId:'openfreemap', mode:'fixed', fixedStyleId:'fiord' })
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)

  /*
   * The phone journey through a hook, end to end.
   *
   * A phone shows one pane at a time: the list is the page until a hook is
   * opened, and then that hook is the page. Choosing one used to change
   * something below two cards and the shared secrets form, so the tap looked
   * like it had done nothing.
   */
  await page.goto('/hooks')
  await expect(page.locator('.hooks-rail')).toBeVisible()
  await expect(page.locator('.hook-detail')).toBeHidden()
  // Secrets belong to the page, not to a hook, so they stay with the list.
  await expect(page.getByText('Secrets')).toBeVisible()

  const chosen = page.locator('.hook-row').first()
  const chosenName = (await chosen.locator('.hook-name').innerText()).trim()
  await chosen.click()
  await expect(page).toHaveURL(/\/hooks\/[0-9a-f-]+$/)
  const opened = page.url()
  await expect(page.locator('.hooks-rail')).toBeHidden()
  await expect(page.locator('.detail-identity h2')).toHaveText(chosenName)
  await expect(page.locator('.detail-back')).toBeVisible()
  // The standing warning and the create button give the editor their pixels,
  // while the heading stays: it is the page's only h1.
  await expect(page.locator('.page-header h1')).toBeVisible()
  await expect(page.locator('.privilege-warning')).toBeHidden()
  await expect(page.locator('.page-header .header-actions')).toBeHidden()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)

  // Edits that were never saved are not lost to a stray tap.
  // Typed rather than filled: CodeMirror only hears real key events, and a
  // silent fill would leave the editor clean and this assertion vacuous.
  await page.locator('.hook-detail .cm-content').click()
  await page.keyboard.type('ctx.log.info("phone edit")')
  await page.locator('.detail-back').click()
  await expect(page.getByRole('dialog', { name: 'Modifications non enregistrées' })).toBeVisible()
  await page.getByRole('button', { name: 'Annuler' }).click()
  await expect(page).toHaveURL(opened)

  await page.locator('.detail-back').click()
  await page.getByRole('button', { name: 'Abandonner les modifications' }).click()
  await expect(page).toHaveURL(/\/hooks$/)
  await expect(page.locator('.hooks-rail')).toBeVisible()

  // The address is the state, so it survives a reload and can be linked to.
  await page.goto(opened)
  await expect(page.locator('.detail-identity h2')).toHaveText(chosenName)
  await page.goBack()
  await expect(page).toHaveURL(/\/hooks$/)

  // The sheet is anchored to the bottom of the screen, so any height it claims
  // beyond the visible viewport is spent above the top edge, taking the heading
  // and the first field label with it.
  await page.getByRole('button', { name: 'Nouveau hook' }).first().click()
  const sheet = page.locator('.app-modal')
  await expect(sheet).toBeVisible()
  const firstField = await page.evaluate(() => {
    const modal = document.querySelector('.app-modal')!
    const input = modal.querySelector('input.input')!
    const label = input.closest('label')!.querySelector('span')!
    const box = label.getBoundingClientRect()
    const sheetBox = modal.getBoundingClientRect()
    return { label: label.textContent, top: box.top, bottom: box.bottom, sheetTop: sheetBox.top, height: window.innerHeight }
  })
  expect(firstField.label).toBe('Nom')
  expect(firstField.sheetTop, 'the sheet must not start above the screen').toBeGreaterThanOrEqual(0)
  expect(firstField.top, 'the name label must not sit off the top of the screen').toBeGreaterThanOrEqual(0)
  expect(firstField.bottom).toBeLessThanOrEqual(firstField.height)

  // Creation asks for a name and a description and nothing else: the code, the
  // vehicle filter and the run time are the detail panel's job.
  await expect(sheet.locator('.cm-content')).toHaveCount(0)
  await expect(sheet.getByLabel('Filtre véhicule')).toHaveCount(0)
  await page.getByRole('dialog', { name: 'Créer un hook' }).getByRole('button', { name: 'Fermer' }).first().click()
  await expect(sheet).toHaveCount(0)

  // The keys the source code is about, reached from the editor that has it,
  // which on a phone means opening a hook first: the list route has no editor.
  await page.locator('.hook-row').first().click()
  await expect(page.locator('.hook-detail .source-label')).toBeVisible()
  await page.locator('.hook-detail .source-label .link-button').click()
  await expect(page.getByRole('dialog', { name: 'Clés de mesure' })).toBeVisible()
  await expect(page.locator('.key-list li').first()).toBeVisible()
  const keyCount = await page.locator('.key-list li').count()
  expect(keyCount).toBeGreaterThan(20)
  await page.locator('.key-reference input[type="search"]').fill('pneu')
  await expect.poll(() => page.locator('.key-list li').count()).toBeLessThan(keyCount)
  await page.locator('.key-reference input[type="search"]').fill('battery.soc')
  await expect(page.locator('.key-list .key-name')).toHaveText(['battery.soc'])
  const referenceFits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
  expect(referenceFits, 'the key reference overflows the phone viewport').toBe(true)
  // Position is a fix, not a metric, and the server's own words describe it.
  await page.locator('.key-reference input[type="search"]').fill('position')
  await expect(page.locator('.position-entry')).toBeVisible()
  await expect(page.locator('.position-entry .position-fields code').first()).toHaveText('position.latitude')
  await page.getByRole('dialog', { name: 'Clés de mesure' }).getByRole('button', { name: 'Fermer' }).first().click()
  await expect(page.locator('.key-reference')).toHaveCount(0)

  const accessibility = await new AxeBuilder({ page }).analyze()
  expect(accessibility.violations).toEqual([])
})

test('what the dashboard stores is what it draws', async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 1000 })
  await page.goto('/login')
  await page.getByLabel('Email').fill('browser-owner@example.com')
  await page.getByLabel('Password').fill('browser-e2e-password-2026')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL('/')
  // An earlier test leaves its own dashboard as the default, so this one names
  // the premade Overview rather than taking whatever opens.
  async function openOverview(): Promise<void> {
    await page.locator('.dashboard-tabs').getByRole('button', { name: /Overview/ }).click()
    await expect(page.locator('.grid-stack-item').first()).toBeVisible()
  }
  await openOverview()

  // Gridstack leaves an attribute off when it holds the default of 1, so the
  // missing ones read as 1 rather than as a difference.
  const drawn = () => page.$$eval('.grid-stack-item', (nodes) => nodes.map((node) => [
    node.getAttribute('data-widget-type'),
    node.getAttribute('gs-x') ?? '0', node.getAttribute('gs-y') ?? '0',
    node.getAttribute('gs-w') ?? '1', node.getAttribute('gs-h') ?? '1',
  ].join(',')).sort().join(' '))

  // The canvas animates into place, so a single read can catch it mid-flight.
  // Two identical reads in a row mean the layout has settled.
  async function settled(): Promise<string> {
    let previous = ''
    await expect.poll(async () => {
      const current = await drawn()
      const stable = Boolean(current) && current === previous
      previous = current
      return stable
    }).toBe(true)
    return previous
  }

  // What the server holds, in the same shape, for the cards actually on screen.
  async function stored(): Promise<string> {
    const rows = await browserJson<Array<{ layout: { preset?: string; widgets: DashboardWidgetRow[] } }>>(page, 'get', '/api/v1/dashboards')
    const overview = rows.find((row) => row.layout.preset)
    const onScreen = new Set((await drawn()).split(' ').map((entry) => entry.split(',')[0]))
    return overview!.layout.widgets
      .filter((widget) => onScreen.has(widget.type))
      .map((widget) => [widget.type, widget.x, widget.y, widget.w, widget.h].join(','))
      .sort().join(' ')
  }

  const wide = await settled()
  expect(await stored(), 'the layout on screen at load is not the one on the server').toBe(wide)

  // A canvas narrower than 1050px is remapped to six columns, and gridstack writes
  // that remap onto each item's gs-* attributes. Editing tears the grid down and
  // builds it again; nothing about drawing it at either width may reach the model.
  await page.setViewportSize({ width: 900, height: 1000 })
  await settled()
  for (const leaveWith of ['Cancel', 'Save']) {
    await page.getByRole('button', { name: 'Dashboard actions' }).click()
    await page.getByRole('menuitem', { name: 'Edit dashboard' }).click()
    await expect(page.locator('.dashboard-editor-bar')).toBeVisible()
    await page.locator('.canvas-controls').getByRole('button', { name: leaveWith }).click()
    await expect(page.locator('.dashboard-editor-bar')).toHaveCount(0)
    await settled()
  }

  await page.setViewportSize({ width: 1400, height: 1000 })
  expect(await settled(), 'editing on a narrow canvas rewrote the wide layout').toBe(wide)
  expect(await stored(), 'drawing the canvas narrow rewrote what the server holds').toBe(wide)

  await page.reload()
  await openOverview()
  expect(await settled()).toBe(wide)

  // And a card dragged somewhere new is drawn there afterwards, not pulled back
  // by a reflow that closes the gap a hidden card left.
  await page.getByRole('button', { name: 'Dashboard actions' }).click()
  await page.getByRole('menuitem', { name: 'Edit dashboard' }).click()
  await expect(page.locator('.dashboard-editor-bar')).toBeVisible()
  const card = page.locator('[data-widget-type="metric-card"]')
  const origin = await card.getAttribute('gs-x')
  const before = await card.boundingBox()
  await page.mouse.move(before!.x + 60, before!.y + 20)
  await page.mouse.down()
  await page.mouse.move(before!.x + 360, before!.y + 20, { steps: 20 })
  await page.mouse.up()
  await expect.poll(() => card.getAttribute('gs-x')).not.toBe(origin)
  const moved = await card.getAttribute('gs-x')
  await page.locator('.canvas-controls').getByRole('button', { name: 'Save' }).click()
  await expect(page.locator('.dashboard-editor-bar')).toHaveCount(0)
  await settled()
  expect(await card.getAttribute('gs-x'), 'the card moved back after saving').toBe(moved)
  await page.reload()
  await openOverview()
  await settled()
  expect(await card.getAttribute('gs-x'), 'the saved position did not survive a reload').toBe(moved)
  expect(await stored()).toBe(await drawn())
})
