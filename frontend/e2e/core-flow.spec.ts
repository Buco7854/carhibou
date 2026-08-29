import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'

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
  // charge curve, a photo. Speed is standard, so both speed cards stay.
  for (const type of ['battery-gauge', 'charging', 'xy-chart', 'vehicle-media', 'telemetry-list']) {
    await expect(page.locator(`[data-widget-type="${type}"]`), type).toHaveCount(0)
  }
  // This vehicle has neither a CAN reading nor a fix yet, so the speed card says
  // so like any other card rather than vanishing.
  await expect(page.locator('[data-widget-type="metric-card"] .dashboard-widget-empty')).toContainText('No data yet')
  for (const type of ['vehicle-selector', 'online-status', 'metric-card', 'route-map', 'activity-feed', 'segment-stats', 'period-stats', 'time-series']) {
    await expect(page.locator(`[data-widget-type="${type}"]`), type).toHaveCount(1)
  }
  await expect(page.locator('.grid-stack-item')).toHaveCount(8)
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
  const hookModal = page.locator('.app-modal')
  await hookModal.getByLabel('Name', { exact:true }).fill('Browser state counter')
  await hookModal.getByLabel('Description').fill('Verifies persistent hook state through the browser flow')
  await hookModal.locator('.cm-content').fill('ctx.state["runs"] = ctx.state.get("runs", 0) + 1\nctx.log.info("browser e2e", runs=ctx.state["runs"], dry_run=ctx.dry_run)')
  await hookModal.getByRole('button', { name: 'Save', exact: true }).click()
  // The view closes this modal and refreshes its list only after the POST it
  // awaits resolves, so both are evidence the hook is committed. Reading the API
  // straight off the click raced the insert and saw an empty collection.
  await expect(hookModal).toBeHidden()
  await expect(page.locator('.hook-list').getByRole('button', { name: /Browser state counter/ })).toBeVisible()
  const [hook] = await browserJson<HookRecord[]>(page, 'get', '/api/v1/hooks')
  expect(hook?.id).toBeTruthy()

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

  await page.getByRole('link', { name: 'Vehicles', exact: true }).click()
  await expect(page.locator('.vehicle-card').first()).toBeVisible()
  await expect(page.locator('.vehicle-card img')).toBeVisible()
  const mobileGarageDimensions = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, viewport: window.innerWidth }))
  expect(mobileGarageDimensions.scroll).toBeLessThanOrEqual(mobileGarageDimensions.viewport)
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
  for (const path of ['/profiles', '/vehicles', '/data-sources', '/settings']) {
    await page.goto(path)
    await expect(page.locator('.page-header h1')).toBeVisible()
    const fits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
    expect(fits, `${path} overflows the phone viewport`).toBe(true)
  }
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
