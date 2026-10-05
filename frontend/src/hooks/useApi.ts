import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '@/services/api'

type State<T> = { data: T | undefined; error: ApiError | null; loading: boolean }

/**
 * Minimal data-fetching hook: GET `url` with `params`, expose loading / error /
 * reload. Pass `null` as url to skip. Stale responses from earlier calls are ignored.
 */
export function useApi<T>(url: string | null, params?: Record<string, unknown>) {
  const [state, setState] = useState<State<T>>({ data: undefined, error: null, loading: !!url })
  const seq = useRef(0)
  const key = url ? `${url}?${JSON.stringify(params ?? {})}` : null

  const load = useCallback(
    async (silent = false) => {
      if (!url) return
      const id = ++seq.current
      if (!silent) setState((s) => ({ ...s, loading: true, error: null }))
      try {
        const clean = Object.fromEntries(Object.entries(params ?? {}).filter(([, v]) => v !== '' && v !== undefined && v !== null))
        const res = await api.get<T>(url, { params: clean })
        if (id === seq.current) setState({ data: res.data, error: null, loading: false })
      } catch (e) {
        if (id === seq.current) setState((s) => ({ ...s, error: e as ApiError, loading: false }))
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key],
  )

  useEffect(() => {
    void load()
  }, [load])

  const setData = useCallback((updater: T | ((prev: T | undefined) => T)) => {
    setState((s) => ({ ...s, data: typeof updater === 'function' ? (updater as (p: T | undefined) => T)(s.data) : updater }))
  }, [])

  return { ...state, reload: load, setData }
}
