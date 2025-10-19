// codecontext-rag/frontend/src/components/shared/StreamingPatch.tsx
import React, { useState, useRef, useEffect } from 'react'
import { Button } from './Button'
import { Badge } from './Badge'
import { Copy, Check, StopCircle } from 'lucide-react'

interface StreamingPatchProps {
  repoId: string
  query: string
  onComplete?: (patch: string) => void
  api: any
}

export const StreamingPatch: React.FC<StreamingPatchProps> = ({ 
  repoId, 
  query, 
  onComplete,
  api 
}) => {
  const [streaming, setStreaming] = useState(false)
  const [patch, setPatch] = useState('')
  const [error, setError] = useState<string>('')
  const [copied, setCopied] = useState(false)
  const abortControllerRef = useRef<AbortController | null>(null)
  const preRef = useRef<HTMLPreElement>(null)

  useEffect(() => {
    // Auto-scroll to bottom as content streams
    if (preRef.current) {
      preRef.current.scrollTop = preRef.current.scrollHeight
    }
  }, [patch])

  const handleStream = async () => {
    if (!repoId || !query) return

    try {
      setStreaming(true)
      setError('')
      setPatch('')
      
      const controller = new AbortController()
      abortControllerRef.current = controller

      await api.streamPatch(
        repoId,
        {
          query,
          temperature: 0.2,
          max_output_tokens: 2000,
          force_unified_diff: true
        },
        (chunk: string) => {
          setPatch(prev => prev + chunk)
        },
        controller.signal
      )

      setStreaming(false)
      if (onComplete && patch) {
        onComplete(patch)
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        setError('Streaming cancelled')
      } else {
        setError(err.message || 'Streaming failed')
      }
      setStreaming(false)
    }
  }

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      setStreaming(false)
    }
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(patch)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {streaming ? (
            <Button
              icon={<StopCircle className="w-4 h-4" />}
              variant="danger"
              onClick={handleStop}
            >
              Stop Streaming
            </Button>
          ) : (
            <Button
              onClick={handleStream}
              disabled={!repoId || !query}
            >
              Stream Patch
            </Button>
          )}
          {streaming && <Badge variant="info">Streaming...</Badge>}
        </div>
        
        {patch && !streaming && (
          <Button
            size="sm"
            variant="ghost"
            icon={copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            onClick={handleCopy}
          >
            {copied ? 'Copied!' : 'Copy'}
          </Button>
        )}
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {(patch || streaming) && (
        <div className="relative">
          <pre
            ref={preRef}
            className="bg-gray-900 text-green-400 p-4 rounded-lg overflow-auto text-sm font-mono max-h-[600px]"
            aria-live="polite"
            aria-atomic="false"
          >
            {patch || 'Waiting for stream...'}
            {streaming && <span className="animate-pulse">▊</span>}
          </pre>
        </div>
      )}
    </div>
  )
}