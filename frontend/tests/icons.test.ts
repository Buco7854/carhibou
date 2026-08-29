import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { ICONS } from '../src/components/icons'

function sources(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    if (statSync(path).isDirectory()) return sources(path)
    return /\.(vue|ts)$/.test(path) ? [path] : []
  })
}

const code = sources('src').map((path) => readFileSync(path, 'utf8')).join('\n')

/**
 * Every name the interface asks for, however it asks. Half of these are literals
 * in a template and half are data: a metric definition carries `icon: 'battery'`
 * and reaches AppIcon at runtime, so a typo in either would quietly draw the
 * fallback instead of failing.
 */
function requestedNames(): string[] {
  const names = new Set<string>()
  for (const match of code.matchAll(/<AppIcon[^>]*\sname="([a-z-]+)"/g)) names.add(match[1]!)
  for (const match of code.matchAll(/\sicon="([a-z-]+)"/g)) names.add(match[1]!)
  for (const match of code.matchAll(/\bicon:\s*'([a-z-]+)'/g)) names.add(match[1]!)
  // Names chosen in a ternary, such as the copy button's check state.
  for (const match of code.matchAll(/:name="[^"]*\?\s*'([a-z-]+)'\s*:\s*'([a-z-]+)'"/g)) {
    names.add(match[1]!)
    names.add(match[2]!)
  }
  return [...names].sort()
}

describe('icon vocabulary', () => {
  it('draws every name the interface asks for', () => {
    const requested = requestedNames()
    expect(requested.length).toBeGreaterThan(20)
    expect(requested.filter((name) => !(name in ICONS))).toEqual([])
  })

  it('carries no glyph nothing asks for', () => {
    const requested = new Set(requestedNames())
    expect(Object.keys(ICONS).filter((name) => !requested.has(name))).toEqual([])
  })
})
