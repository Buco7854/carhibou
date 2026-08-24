let fallbackSequence = 0

export function clientId(prefix = 'client'): string {
  fallbackSequence += 1
  return `${prefix}-${Date.now().toString(36)}-${fallbackSequence.toString(36)}-${Math.random().toString(36).slice(2)}`
}
