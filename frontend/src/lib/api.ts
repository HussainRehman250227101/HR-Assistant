// Thin fetch wrapper for the Django REST API with JWT access/refresh handling.

const ACCESS_KEY = 'hr.access'
const REFRESH_KEY = 'hr.refresh'
export const API_BASE = '/api/v1'

export class ApiError extends Error {
  status: number
  data: unknown
  constructor(status: number, data: unknown, message: string) {
    super(message)
    this.status = status
    this.data = data
  }
}

export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS_KEY)
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY)
  },
  set(access: string, refresh?: string) {
    localStorage.setItem(ACCESS_KEY, access)
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

function flatten(data: unknown, prefix = ''): string[] {
  if (data == null) return []
  if (typeof data === 'string') return [prefix ? `${prefix}: ${data}` : data]
  if (Array.isArray(data)) return data.flatMap((item) => flatten(item, prefix))
  if (typeof data === 'object') {
    return Object.entries(data as Record<string, unknown>).flatMap(([key, value]) =>
      flatten(value, key === 'detail' || key === 'non_field_errors' ? prefix : key.replaceAll('_', ' ')),
    )
  }
  return [String(data)]
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const parts = flatten(error.data)
    return parts.length ? parts.join(' · ') : error.message
  }
  if (error instanceof Error) return error.message
  return 'Unexpected error'
}

let refreshing: Promise<boolean> | null = null

async function refreshAccess(): Promise<boolean> {
  const refresh = tokens.refresh
  if (!refresh) return false
  refreshing ??= fetch(`${API_BASE}/auth/token/refresh/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  })
    .then(async (res) => {
      if (!res.ok) return false
      const data = await res.json()
      tokens.set(data.access, data.refresh)
      return true
    })
    .catch(() => false)
    .finally(() => {
      refreshing = null
    })
  return refreshing
}

type RequestOptions = { method?: string; body?: unknown; form?: FormData; raw?: boolean }

async function send(path: string, opts: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (tokens.access) headers.Authorization = `Bearer ${tokens.access}`
  let body: BodyInit | undefined
  if (opts.form) body = opts.form
  else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.body)
  }
  return fetch(`${API_BASE}${path}`, { method: opts.method ?? (body ? 'POST' : 'GET'), headers, body })
}

export async function apiResponse(path: string, opts: RequestOptions = {}): Promise<Response> {
  let res = await send(path, opts)
  if (res.status === 401 && (await refreshAccess())) res = await send(path, opts)
  if (res.status === 401) {
    tokens.clear()
    window.dispatchEvent(new Event('hr:logout'))
  }
  if (!res.ok) {
    const data: unknown = await res.json().catch(() => null)
    throw new ApiError(res.status, data, `Request failed (${res.status})`)
  }
  return res
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await apiResponse(path, opts)
  if (res.status === 204) return undefined as T
  const text = await res.text()
  return (text ? JSON.parse(text) : undefined) as T
}

export async function downloadFile(path: string, filename: string) {
  const res = await apiResponse(path)
  const url = URL.createObjectURL(await res.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export function qs(params: Record<string, string | number | undefined | null>) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}
