import type { Envelope } from './types'

const API_ROOT = import.meta.env.VITE_API_ROOT ?? '/api/v1/command-center'

export async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(response.status === 404 ? 'The requested record was not found.' : `API request failed (${response.status}).`)
  const body = await response.json() as Envelope<T>
  return body.data
}
