import axios, { AxiosError } from 'axios'
import { sessionStore } from '@/features/auth/sessionStore'

/** Normalised error every screen can show without knowing about HTTP. */
export class ApiError extends Error {
  status: number
  code: string
  details: unknown
  fields: { field: string; message: string }[]

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
    const f = (details as { fields?: { field: string; message: string }[] } | undefined)?.fields
    this.fields = Array.isArray(f) ? f : []
  }
}

const baseURL = (process.env.NEXT_PUBLIC_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export const api = axios.create({ baseURL: `${baseURL}/api`, timeout: 60_000 })

api.interceptors.request.use((config) => {
  const token = sessionStore.get()?.accessToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err: AxiosError<{ error?: { code: string; message: string; details?: unknown } }>) => {
    if (!err.response) {
      return Promise.reject(new ApiError(0, 'NETWORK_ERROR', 'Cannot reach the server. Check your connection and try again.'))
    }
    const { status, data } = err.response
    const e = data?.error
    if (status === 401) sessionStore.expire()
    return Promise.reject(
      new ApiError(status, e?.code ?? 'HTTP_ERROR', e?.message ?? 'The request could not be completed.', e?.details),
    )
  },
)

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.fields.length) return `${err.message} ${err.fields.map((f) => `${f.field}: ${f.message}`).join('; ')}`
    return err.message
  }
  return 'Something unexpected happened.'
}

export type Paged<T> = { items: T[]; total: number }
