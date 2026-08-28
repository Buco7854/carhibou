import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import en from '../src/i18n/locales/en'
import fr from '../src/i18n/locales/fr'
import { widgetPresets, widgetRegistry } from '../src/widgets/registry'

function flatten(value: unknown, prefix = ''): string[] {
  if (!value || typeof value !== 'object') return [prefix]
  return Object.entries(value as Record<string, unknown>).flatMap(([key, item]) =>
    flatten(item, prefix ? `${prefix}.${key}` : key))
}

function sources(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    if (statSync(path).isDirectory()) return path.endsWith('locales') ? [] : sources(path)
    return /\.(vue|ts)$/.test(path) ? [path] : []
  })
}

const files = sources('src')
const code = files.map((path) => readFileSync(path, 'utf8')).join('\n')
const enKeys = new Set(flatten(en))
const frKeys = new Set(flatten(fr))

/**
 * Keys the templates build at runtime, paired with the value domain that
 * produces them. A widget or view that gains a new branch has to extend the
 * matching list here, which is the point: the branch cannot ship untranslated.
 */
const DYNAMIC: Array<[string, string[]]> = [
  ['agents.preset', ['live', 'standard', 'saver', 'frugal', 'minimal']],
  ['agents.compat', ['compatible', 'incompatible']],
  ['agents.setupKind', ['command', 'guided']],
  ['agents.stepDefaults', ['command', 'value', 'link', 'manual']],
  ['connectors.status', ['disabled', 'connecting', 'connected', 'error']],
  ['profiles.type', ['can', 'mapping']],
  ['profiles.transformKind', ['none', 'scale', 'enum', 'boolean', 'json']],
  ['dashboard.activity', ['driving', 'charging', 'parked', 'unknown']],
  ['dashboard.agent', ['online', 'stale', 'never']],
  ['insights.filterOption', ['all', 'drive', 'charge']],
  ['insights.kind', ['drive', 'charge']],
]

function referencedKeys(): string[] {
  const keys = new Set<string>()
  for (const match of code.matchAll(/(?<![\w.])\$?te?\(\s*'([^']+)'/g)) keys.add(match[1]!)
  for (const match of code.matchAll(/(?:labelKey|titleKey)\s*:\s*'([^']+)'/g)) {
    if (match[1]!.includes('.')) keys.add(match[1]!)
  }
  for (const definition of Object.values(widgetRegistry)) keys.add(definition.titleKey)
  for (const [namespace, values] of DYNAMIC) for (const value of values) keys.add(`${namespace}.${value}`)
  return [...keys].sort()
}

describe('translation coverage', () => {
  it('resolves every key the interface asks for, in both locales', () => {
    const referenced = referencedKeys()
    expect(referenced.length).toBeGreaterThan(400)
    expect(referenced.filter((key) => !enKeys.has(key))).toEqual([])
    expect(referenced.filter((key) => !frKeys.has(key))).toEqual([])
  })

  it('keeps the two locales in step with each other', () => {
    expect([...enKeys].filter((key) => !frKeys.has(key))).toEqual([])
    expect([...frKeys].filter((key) => !enKeys.has(key))).toEqual([])
  })

  it('gives every registered widget a title that resolves', () => {
    for (const definition of Object.values(widgetRegistry)) {
      expect(enKeys.has(definition.titleKey), definition.type).toBe(true)
      expect(frKeys.has(definition.titleKey), definition.type).toBe(true)
    }
  })

  it('titles an insight widget head from the same key its registry row uses', () => {
    // The head falls back to a literal key when the two drift apart.
    for (const type of ['route-map', 'activity-feed', 'segment-stats', 'period-stats']) {
      const source = readFileSync(files.find((path) => path.includes(fileFor(type)))!, 'utf8')
      expect(source, type).toContain(`t('${widgetRegistry[type]!.titleKey}')`)
    }
    // The generic chart names itself after the preset it matches, else its own key.
    const chart = readFileSync(files.find((path) => path.includes('XyChartWidget.vue'))!, 'utf8')
    expect(chart).toContain(`?? '${widgetRegistry['xy-chart']!.titleKey}'`)
  })

  it('resolves every widget preset title in both locales', () => {
    for (const preset of widgetPresets) {
      expect(enKeys.has(preset.titleKey), preset.id).toBe(true)
      expect(frKeys.has(preset.titleKey), preset.id).toBe(true)
      expect(widgetRegistry[preset.type], preset.id).toBeDefined()
    }
  })
})

function fileFor(type: string): string {
  return `${type.split('-').map((part) => part[0]!.toUpperCase() + part.slice(1)).join('')}Widget.vue`
}
