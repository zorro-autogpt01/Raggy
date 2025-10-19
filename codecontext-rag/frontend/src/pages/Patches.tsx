// codecontext-rag/frontend/src/pages/Patches.tsx (Enhanced)
import React, { useState, useRef } from 'react'
import { Card } from '../components/shared/Card'
import { Button } from '../components/shared/Button'
import { Badge } from '../components/shared/Badge'
import { LoadingSpinner } from '../components/shared/LoadingSpinner'
import { ErrorMessage } from '../components/shared/ErrorMessage'
import { api } from '../services/api'
import { GitPullRequest, CheckCircle, XCircle, Copy, Check, StopCircle, Layers } from 'lucide-react'
import type { Repository } from '../types/index'
import { useClipboard } from '../hooks/useClipboard'

export const Patches: React.FC = () => {
  const [repos, setRepos] = useState<Repository[]>([])
  const [selectedRepo, setSelectedRepo] = useState<string>('')
  const [query, setQuery] = useState('add input validation to the login form')
  const [useStreaming, setUseStreaming] = useState(false)
  const [patch, setPatch] = useState<string>('')
  const [validation, setValidation] = useState<any>(null)
  const [segments, setSegments] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState<string>('')
  const abortControllerRef = useRef<AbortController | null>(null)
  const preRef = useRef<HTMLPreElement>(null)
  const { copied, copy } = useClipboard()

  React.useEffect(() => {
    loadRepos()
  }, [])

  React.useEffect(() => {
    if (preRef.current && streaming) {
      preRef.current.scrollTop = preRef.current.scrollHeight
    }
  }, [patch, streaming])

  const loadRepos = async () => {
    try {
      const data = await api.listRepositories()
      setRepos(data)
      if (data.length > 0 && !selectedRepo) {
        setSelectedRepo(data[0].id)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load repositories')
    }
  }

  const handleGeneratePatch = async () => {
    if (!selectedRepo || !query) return

    if (useStreaming) {
      handleStreamPatch()
    } else {
      handleNonStreamPatch()
    }
  }

  const handleStreamPatch = async () => {
    if (!selectedRepo || !query) return

    try {
      setStreaming(true)
      setError('')
      setPatch('')
      setValidation(null)
      
      const controller = new AbortController()
      abortControllerRef.current = controller

      await api.streamPatch(
        selectedRepo,
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
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setError(err.message || 'Streaming failed')
      }
      setStreaming(false)
    }
  }

  const handleNonStreamPatch = async () => {
    if (!selectedRepo || !query) return

    try {
      setLoading(true)
      setError('')
      const data = await api.generatePatch(selectedRepo, {
        query,
        temperature: 0.2,
        max_output_tokens: 2000,
        force_unified_diff: true
      })
      setPatch(data.patch || '')
      setValidation(data.validation || null)
    } catch (err: any) {
      setError(err.message || 'Failed to generate patch')
    } finally {
      setLoading(false)
    }
  }

  const handleStopStreaming = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      setStreaming(false)
    }
  }

  const handleSegmentPatch = async () => {
    if (!patch) return

    try {
      setLoading(true)
      const data = await api.segmentPatch(selectedRepo, patch)
      setSegments(data)
    } catch (err: any) {
      setError(err.message || 'Failed to segment patch')
    } finally {
      setLoading(false)
    }
  }

  const applyPatch = async () => {
    if (!patch) return

    try {
      setApplying(true)
      setError('')
      await api.applyPatch(selectedRepo, {
        patch,
        commit_message: `Auto-patch: ${query}`,
        push: false,
        create_pr: false,
        dry_run: false
      })
      alert('Patch applied successfully!')
    } catch (err: any) {
      setError(err.message || 'Failed to apply patch')
    } finally {
      setApplying(false)
    }
  }

  return (
    <div className="space-y-6">
      <Card title="Patch Generator">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Repository
            </label>
            <select
              value={selectedRepo}
              onChange={(e) => setSelectedRepo(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="">Select repository...</option>
              {repos.map(repo => (
                <option key={repo.id} value={repo.id}>
                  {repo.full_name || repo.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Change Description
            </label>
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              rows={3}
              placeholder="Describe the changes you want..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="use-streaming"
              checked={useStreaming}
              onChange={(e) => setUseStreaming(e.target.checked)}
              className="w-4 h-4"
            />
            <label htmlFor="use-streaming" className="text-sm text-gray-700">
              Use streaming mode (real-time generation)
            </label>
          </div>

          <div className="flex items-center gap-3">
            {streaming ? (
              <Button
                icon={<StopCircle className="w-4 h-4" />}
                variant="danger"
                onClick={handleStopStreaming}
              >
                Stop Streaming
              </Button>
            ) : (
              <Button
                icon={<GitPullRequest className="w-4 h-4" />}
                onClick={handleGeneratePatch}
                loading={loading}
                disabled={!selectedRepo || !query}
              >
                Generate Patch
              </Button>
            )}
            
            {patch && !streaming && (
              <>
                <Button
                  icon={<Layers className="w-4 h-4" />}
                  variant="secondary"
                  onClick={handleSegmentPatch}
                  loading={loading}
                >
                  Segment Patch
                </Button>
                <Button
                  icon={copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  variant="ghost"
                  onClick={() => copy(patch)}
                  size="sm"
                >
                  {copied ? 'Copied!' : 'Copy'}
                </Button>
              </>
            )}
          </div>
        </div>
      </Card>

      {error && <ErrorMessage message={error} onRetry={handleGeneratePatch} />}

      {(loading && !streaming) && <LoadingSpinner text="Generating patch..." />}

      {streaming && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <Badge variant="info">Streaming in progress...</Badge>
            <Badge>{patch.length} characters</Badge>
          </div>
        </Card>
      )}

      {patch && (
        <>
          {validation && !streaming && (
            <Card title="Validation">
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  {validation.ok ? (
                    <>
                      <CheckCircle className="w-5 h-5 text-green-600" />
                      <span className="font-medium text-green-700">Valid patch</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="w-5 h-5 text-red-600" />
                      <span className="font-medium text-red-700">Issues found</span>
                    </>
                  )}
                </div>

                {validation.files && validation.files.length > 0 && (
                  <div>
                    <p className="text-sm font-medium text-gray-700 mb-2">Files affected:</p>
                    <div className="flex flex-wrap gap-2">
                      {validation.files.map((file: string, idx: number) => (
                        <Badge key={idx}>{file}</Badge>
                      ))}
                    </div>
                  </div>
                )}

                {validation.issues && validation.issues.length > 0 && (
                  <div>
                    <p className="text-sm font-medium text-gray-700 mb-2">Issues:</p>
                    <ul className="space-y-1">
                      {validation.issues.map((issue: string, idx: number) => (
                        <li key={idx} className="text-sm text-red-600">• {issue}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {validation.ok && (
                  <Button
                    variant="success"
                    onClick={applyPatch}
                    loading={applying}
                  >
                    Apply Patch
                  </Button>
                )}
              </div>
            </Card>
          )}

          <Card title="Generated Patch">
            <div className="relative">
              <pre
                ref={preRef}
                className="bg-gray-900 text-green-400 p-4 rounded-lg overflow-auto text-sm font-mono max-h-[600px]"
                aria-live="polite"
              >
                {patch}
                {streaming && <span className="animate-pulse">▊</span>}
              </pre>
            </div>
          </Card>

          {segments && (
            <Card title="Suggested Commit Plan">
              <div className="space-y-4">
                {segments.commit_plan?.map((commit: any, idx: number) => (
                  <div key={idx} className="p-4 bg-gray-50 rounded-lg">
                    <h4 className="font-semibold text-gray-900 mb-2">
                      Commit {idx + 1}: {commit.message}
                    </h4>
                    <div className="flex flex-wrap gap-2">
                      {commit.files.map((file: string, fidx: number) => (
                        <Badge key={fidx} variant="info">{file}</Badge>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}