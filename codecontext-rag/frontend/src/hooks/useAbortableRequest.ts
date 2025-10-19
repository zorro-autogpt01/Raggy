// codecontext-rag/frontend/src/hooks/useAbortableRequest.ts
import { useState, useCallback, useRef } from 'react'

export function useAbortableRequest<T>() {
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string>('')
  const abortControllerRef = useRef<AbortController | null>(null)

  const execute = useCallback(async (
    requestFn: (signal: AbortSignal) => Promise<T>
  ) => {
    try {
      // Abort any pending request
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }

      const controller = new AbortController()
      abortControllerRef.current = controller

      setLoading(true)
      setError('')
      
      const result = await requestFn(controller.signal)
      setData(result)
      return result
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setError(err.message || 'Request failed')
        throw err
      }
    } finally {
      setLoading(false)
    }
  }, [])

  const abort = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      setLoading(false)
    }
  }, [])

  return { data, loading, error, execute, abort }
}