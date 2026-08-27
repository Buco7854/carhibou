export class APIError extends Error {
  constructor(
    public status: number,
    message: string,
    public requestId?: string,
  ) {
    super(message)
  }
}

/** The message to show a person for anything a request or handler threw. */
export function errorMessage(reason: unknown, fallback = 'Something went wrong'): string {
  return reason instanceof Error && reason.message ? reason.message : fallback
}

function cookie(name: string): string | undefined {
  return document.cookie
    .split('; ')
    .find((value) => value.startsWith(`${name}=`))
    ?.split('=')
    .slice(1)
    .join('=')
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const method = (options.method ?? 'GET').toUpperCase()
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrf = cookie('carhibou_csrf')
    if (csrf) headers.set('X-CSRF-Token', csrf)
  }
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers,
    credentials: 'same-origin',
  })
  if (response.status === 204) return undefined as T
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new APIError(
      response.status,
      payload.error?.message ?? `Request failed (${response.status})`,
      payload.request_id,
    )
  }
  return payload as T
}
