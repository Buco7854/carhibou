import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'

interface VehicleRecord { id: string; name: string }
interface Enrollment { token: string }
interface EnrolledDevice { device_id: string; credential: string }
interface HookRecord { id: string }
interface HookExecution { status: string; logs: Array<Record<string, unknown>> }

async function csrfToken(page: Page): Promise<string> {
  const cookies = await page.context().cookies()
  const csrf = cookies.find((cookie) => cookie.name === 'vehinode_csrf')?.value
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
  await expect(page.getByRole('heading', { name: 'Sign in to VehiNode' })).toBeVisible()
  await expect(page.getByText('Open-source software · operated by you')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Create the initial administrator' })).toHaveCount(0)
  const loginAccessibility = await new AxeBuilder({ page }).analyze()
  expect(loginAccessibility.violations).toEqual([])

  await page.getByLabel('Email').fill('browser-owner@example.com')
  await page.getByLabel('Password').fill('browser-e2e-password-2026')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL('/')
  await expect(page.getByText('Your garage is quiet')).toBeVisible()

  const rejectedRegistration = await request.post('/api/v1/auth/register', {
    data: {
      email: 'second-owner@example.com',
      password: 'another-browser-password-2026',
      display_name: 'Second Owner',
    },
  })
  expect(rejectedRegistration.status()).toBe(403)

  await page.getByRole('link', { name: 'Add your first vehicle' }).click()
  await page.getByRole('button', { name: 'Add vehicle' }).click()
  await page.getByLabel('Name').fill('Éclair')
  await page.getByLabel('Year').fill('2018')
  await page.getByRole('button', { name: 'Create vehicle' }).click()
  await expect(page.getByRole('heading', { name: 'Éclair' })).toBeVisible()
  const [vehicle] = await browserJson<VehicleRecord[]>(page, 'get', '/api/v1/vehicles')
  expect(vehicle?.name).toBe('Éclair')

  await page.getByRole('link', { name: 'Devices' }).click()
  await page.getByRole('button', { name: 'Add tracker' }).click()
  const enrollmentResponse = page.waitForResponse((response) => response.url().includes('/enrollments') && response.request().method() === 'POST')
  await page.locator('.enrollment-panel').getByRole('button', { name: 'Add tracker' }).click()
  const enrollment = await (await enrollmentResponse).json() as Enrollment
  await expect(page.locator('.enrollment-panel pre')).toContainText('--token')

  const enrolledResponse = await request.post('/api/v1/device/enroll', {
    data: { token: enrollment.token, agent_version: 'e2e-1.0.0', hostname: 'browser-simulator', hardware: { model: 'simulated-pi-zero' } },
  })
  expect(enrolledResponse.status()).toBe(201)
  const enrolled = await enrolledResponse.json() as EnrolledDevice
  const isolatedHumanRequest = await request.get('/api/v1/auth/me', { headers: { Authorization: `Device ${enrolled.credential}` } })
  expect(isolatedHumanRequest.status()).toBe(401)

  const samples = Array.from({ length: 6 }, (_, index) => ({
    id: randomUUID(),
    sequence: index,
    recorded_at: new Date(Date.now() - (5 - index) * 5_000).toISOString(),
    position: { latitude: 48.8566 + index * 0.002, longitude: 2.3522 + index * 0.003, speed: 24 + index * 7, heading: 35 + index * 8, altitude: 42, accuracy: 4.5 },
    metrics: { 'battery.soc': 82 - index, 'battery.pack_voltage': 330.5, 'battery.power': -11.8, 'charging.active': false, 'vehicle.speed': 24 + index * 7 },
    device: { mobile_signal: -76, queue_depth: 0 },
  }))
  const bootId = randomUUID()
  const firstBatch = await request.post('/api/v1/device/telemetry/batch', {
    headers: { Authorization: `Device ${enrolled.credential}` },
    data: { boot_id: bootId, samples },
  })
  expect(firstBatch.status()).toBe(200)
  expect((await firstBatch.json()).accepted).toHaveLength(6)
  const retriedBatch = await request.post('/api/v1/device/telemetry/batch', {
    headers: { Authorization: `Device ${enrolled.credential}` },
    data: { boot_id: bootId, samples },
  })
  expect(retriedBatch.status()).toBe(200)
  expect((await retriedBatch.json()).duplicates).toHaveLength(6)

  await page.getByRole('link', { name: 'Dashboard', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Éclair' })).toBeVisible()
  await expect(page.locator('.energy-state strong')).toHaveText('77')
  await expect(page.locator('.map-heading strong')).toContainText('48.86660')
  await expect(page.locator('.vehinode-position-marker')).toBeVisible()
  await expect(page.getByText('Live updates')).toBeVisible()

  const liveSample = {
    id: randomUUID(),
    sequence: 6,
    recorded_at: new Date().toISOString(),
    position: { latitude: 48.87, longitude: 2.37, speed: 18, heading: 102, altitude: 43, accuracy: 3.8 },
    metrics: { 'battery.soc': 61, 'battery.pack_voltage': 329.1, 'battery.power': -4.2, 'charging.active': false, 'vehicle.speed': 18 },
    device: { mobile_signal: -73, queue_depth: 0 },
  }
  const liveBatch = await request.post('/api/v1/device/telemetry/batch', {
    headers: { Authorization: `Device ${enrolled.credential}` },
    data: { boot_id: bootId, samples: [liveSample] },
  })
  expect(liveBatch.status()).toBe(200)
  await expect(page.locator('.energy-state strong')).toHaveText('61')
  await expect(page.locator('.map-heading strong')).toContainText('48.87000')

  const dashboardAccessibility = await new AxeBuilder({ page }).analyze()
  expect(dashboardAccessibility.violations).toEqual([])
  await page.getByTitle('Theme').click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await expect.poll(() => page.getByRole('heading', { name: 'Éclair' }).evaluate((element) => getComputedStyle(element).color)).toBe('rgb(241, 243, 239)')
  const darkDashboardAccessibility = await new AxeBuilder({ page }).analyze()
  expect(darkDashboardAccessibility.violations).toEqual([])
  await page.getByTitle('Theme').click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')

  await page.getByRole('link', { name: 'History', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Éclair · History' })).toBeVisible()
  await expect(page.getByText('7 source samples')).toBeVisible()
  await expect(page.locator('.route-count')).toContainText('7')

  await page.getByRole('link', { name: 'Dashboards' }).click()
  await page.getByRole('button', { name: '+ Add widget' }).click()
  await page.getByLabel('Title').fill('Battery at a glance')
  await page.locator('.modal').getByRole('button', { name: '+ Add widget' }).click()
  await expect(page.getByText('Battery at a glance')).toBeVisible()
  await page.getByRole('button', { name: 'Save layout' }).click()
  await expect(page.getByText('Preferences are saved in this browser.')).toBeVisible()
  await page.reload()
  await expect(page.getByText('Battery at a glance')).toBeVisible()

  await page.getByRole('link', { name: 'Hooks' }).click()
  await page.getByLabel('Name').fill('Browser state counter')
  await page.getByLabel('Description').fill('Verifies persistent hook state through the browser flow')
  await page.locator('.cm-content').fill('ctx.state["runs"] = ctx.state.get("runs", 0) + 1\nctx.log.info("browser e2e", runs=ctx.state["runs"], dry_run=ctx.dry_run)')
  await page.locator('.editor-panel').getByRole('button', { name: 'Save', exact: true }).click()
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

  await page.getByRole('link', { name: 'Devices' }).click()
  await expect(page.getByRole('heading', { name: 'Vehicle tracker' })).toBeVisible()
  await expect(page.getByText('e2e-1.0.0')).toBeVisible()

  await page.setViewportSize({ width: 375, height: 812 })
  await page.getByRole('link', { name: 'Dashboard', exact: true }).click()
  await expect(page.getByText('Live updates')).toBeVisible()
  const badgeGeometry = await page.locator('.status').evaluateAll((badges) => badges.map((badge) => {
    const bounds = badge.getBoundingClientRect()
    return { radius: getComputedStyle(badge).borderRadius, width: bounds.width, height: bounds.height }
  }))
  expect(badgeGeometry.length).toBeGreaterThan(0)
  expect(badgeGeometry.every((badge) => badge.radius === '6px' && badge.width > badge.height)).toBeTruthy()
  const mobileDimensions = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, viewport: window.innerWidth }))
  expect(mobileDimensions.scroll).toBeLessThanOrEqual(mobileDimensions.viewport)
})

test('mobile login keeps language, theme, keyboard access and reflow', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' })
  await page.goto('/login')

  await page.keyboard.press('Tab')
  await expect(page.getByLabel('Language')).toBeFocused()
  await page.getByLabel('Language').selectOption('fr')
  await expect(page.getByRole('heading', { name: 'Connectez-vous à VehiNode' })).toBeVisible()
  await page.getByTitle('Thème').click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  const dimensions = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, viewport: window.innerWidth }))
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.viewport)
  const accessibility = await new AxeBuilder({ page }).analyze()
  expect(accessibility.violations).toEqual([])
})
