// codecontext-rag/frontend/src/hooks/usePolling.ts
import { useState, useEffect, useCallback } from 'react'

interface PollingOptions<T> {
  url: string
  interval?: number
  stopWhen: (data: T) => boolean
  maxAttempts?: number
  enabled?: boolean
}

export function usePolling<T>({
  url,
  interval = 2000,
  stopWhen,
  maxAttempts = 60,
  enabled = true
}: PollingOptions<T>) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')
  const [attempts, setAttempts] = useState(0)

  useEffect(() => {
    if (!enabled || !url) return

    let cancelled = false
    let timeoutId: ReturnType<typeof setTimeout>

    const poll = async () => {
      if (cancelled || attempts >= maxAttempts) return

      try {
        setLoading(true)
        const response = await fetch(url)
        const result = await response.json()
        
        if (!cancelled) {
          setData(result)
          setAttempts(prev => prev + 1)

          if (!stopWhen(result)) {
            timeoutId = setTimeout(poll, interval)
          } else {
            setLoading(false)
          }
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err.message)
          setLoading(false)
        }
      }
    }

    poll()

    return () => {
      cancelled = true
      clearTimeout(timeoutId)
    }
  }, [url, interval, maxAttempts, enabled, attempts])

  const reset = useCallback(() => {
    setData(null)
    setError('')
    setAttempts(0)
  }, [])

  return { data, loading, error, attempts, reset }
}