// codecontext-rag/frontend/src/pages/Context.tsx (Enhanced)
import React, { useState } from 'react'
import { Card } from '../components/shared/Card'
import { Button } from '../components/shared/Button'
import { Badge } from '../components/shared/Badge'
import { LoadingSpinner } from '../components/shared/LoadingSpinner'
import { ErrorMessage } from '../components/shared/ErrorMessage'
import { CodeBlock } from '../components/shared/CodeBlock'
import { MermaidDiagram } from '../components/shared/MermaidDiagram'
import { Tabs } from '../components/shared/Tabs'
import { api } from '../services/api'
import { FileCode, Layers, Settings } from 'lucide-react'
import type { Repository, ContextChunk } from '../types/index'

export const Context: React.FC = () => {
  const [repos, setRepos] = useState<Repository[]>([])
  const [selectedRepo, setSelectedRepo] = useState<string>('')
  const [query, setQuery] = useState('how does authentication work?')
  const [maxChunks, setMaxChunks] = useState(8)
  const [retrievalMode, setRetrievalMode] = useState<'vector' | 'callgraph' | 'slice'>('vector')
  const [expandNeighbors, setExpandNeighbors] = useState(true)
  const [callGraphDepth, setCallGraphDepth] = useState(2)
  const [sliceTarget, setSliceTarget] = useState('')
  const [sliceDirection, setSliceDirection] = useState<'forward' | 'backward'>('forward')
  const [sliceDepth, setSliceDepth] = useState(3)
  const [languages, setLanguages] = useState<string[]>([])
  const [chunks, setChunks] = useState<ContextChunk[]>([])
  const [summary, setSummary] = useState<any>(null)
  const [artifacts, setArtifacts] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')
  const [showAdvanced, setShowAdvanced] = useState(false)

  React.useEffect(() => {
    loadRepos()
  }, [])

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

  const getContext = async () => {
    if (!selectedRepo || !query) return

    try {
      setLoading(true)
      setError('')
      
      const requestData: any = {
        query,
        max_chunks: maxChunks,
        expand_neighbors: expandNeighbors,
        retrieval_mode: retrievalMode
      }

      // Add mode-specific options
      if (retrievalMode === 'callgraph') {
        requestData.call_graph_depth = callGraphDepth
      } else if (retrievalMode === 'slice') {
        requestData.slice_target = sliceTarget
        requestData.slice_direction = sliceDirection
        requestData.slice_depth = sliceDepth
      }

      // Add filters if specified
      if (languages.length > 0) {
        requestData.filters = { languages }
      }

      const data = await api.getContext(selectedRepo, requestData)
      setChunks(data.chunks || [])
      setSummary(data.summary || null)
      setArtifacts(data.artifacts || [])
    } catch (err: any) {
      setError(err.message || 'Failed to get context')
    } finally {
      setLoading(false)
    }
  }

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 80) return 'text-green-600'
    if (confidence >= 60) return 'text-yellow-600'
    return 'text-orange-600'
  }

  return (
    <div className="space-y-6">
      <Card title="Context Retrieval">
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
              Query
            </label>
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              rows={3}
              placeholder="What context do you need?"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Max Chunks
              </label>
              <input
                type="number"
                min="1"
                max="50"
                value={maxChunks}
                onChange={(e) => setMaxChunks(parseInt(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Retrieval Mode
              </label>
              <select
                value={retrievalMode}
                onChange={(e) => setRetrievalMode(e.target.value as any)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                <option value="vector">Vector Similarity</option>
                <option value="callgraph">Call Graph</option>
                <option value="slice">Program Slice</option>
              </select>
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={expandNeighbors}
                  onChange={(e) => setExpandNeighbors(e.target.checked)}
                  className="w-4 h-4"
                />
                <span className="text-sm text-gray-700">Expand Neighbors</span>
              </label>
            </div>
          </div>

          <div className="flex items-center justify-between">
            <Button
              size="sm"
              variant="ghost"
              icon={<Settings className="w-4 h-4" />}
              onClick={() => setShowAdvanced(!showAdvanced)}
            >
              {showAdvanced ? 'Hide' : 'Show'} Advanced Options
            </Button>
          </div>

          {showAdvanced && (
            <div className="p-4 bg-gray-50 rounded-lg space-y-4">
              {retrievalMode === 'callgraph' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Call Graph Depth
                  </label>
                  <input
                    type="range"
                    min="1"
                    max="5"
                    value={callGraphDepth}
                    onChange={(e) => setCallGraphDepth(parseInt(e.target.value))}
                    className="w-full"
                  />
                  <span className="text-sm text-gray-600">{callGraphDepth} levels</span>
                </div>
              )}

              {retrievalMode === 'slice' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Slice Target (function/variable name)
                    </label>
                    <input
                      type="text"
                      value={sliceTarget}
                      onChange={(e) => setSliceTarget(e.target.value)}
                      placeholder="target_function"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Direction
                      </label>
                      <select
                        value={sliceDirection}
                        onChange={(e) => setSliceDirection(e.target.value as any)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                      >
                        <option value="forward">Forward</option>
                        <option value="backward">Backward</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Depth
                      </label>
                      <input
                        type="number"
                        min="1"
                        max="10"
                        value={sliceDepth}
                        onChange={(e) => setSliceDepth(parseInt(e.target.value))}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                      />
                    </div>
                  </div>
                </>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Filter by Languages (comma-separated)
                </label>
                <input
                  type="text"
                  value={languages.join(', ')}
                  onChange={(e) => setLanguages(e.target.value.split(',').map(l => l.trim()).filter(Boolean))}
                  placeholder="python, javascript, typescript"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
            </div>
          )}

          <Button
            icon={<Layers className="w-4 h-4" />}
            onClick={getContext}
            loading={loading}
            disabled={!selectedRepo || !query}
          >
            Get Context
          </Button>
        </div>
      </Card>

      {error && <ErrorMessage message={error} onRetry={getContext} />}

      {loading ? (
        <LoadingSpinner text="Retrieving context..." />
      ) : (
        <>
          {summary && (
            <Card>
              <div className="grid grid-cols-3 gap-6">
                <div>
                  <p className="text-sm text-gray-600">Total Chunks</p>
                  <p className="text-2xl font-bold text-gray-900">{summary.total_chunks}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Avg Confidence</p>
                  <p className={`text-2xl font-bold ${getConfidenceColor(summary.avg_confidence)}`}>
                    {Math.round(summary.avg_confidence)}%
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Mode</p>
                  <p className="text-lg font-semibold text-gray-900 capitalize">
                    {summary.retrieval_mode}
                  </p>
                </div>
              </div>
            </Card>
          )}

          {artifacts.length > 0 && (
            <Card title="Artifacts">
              <Tabs
                tabs={artifacts.map((artifact, idx) => ({
                  id: `artifact-${idx}`,
                  label: artifact.label || `Artifact ${idx + 1}`,
                  content: (
                    <div>
                      {artifact.type === 'mermaid' ? (
                        <div className="space-y-4">
                          <MermaidDiagram chart={artifact.content} />
                          <details>
                            <summary className="cursor-pointer text-sm text-gray-600 hover:text-gray-900">
                              View raw content
                            </summary>
                            <CodeBlock code={artifact.content} language="text" />
                          </details>
                        </div>
                      ) : (
                        <CodeBlock code={artifact.content} language={artifact.type} />
                      )}
                    </div>
                  )
                }))}
              />
            </Card>
          )}

          {chunks.length > 0 && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-gray-900">
                  Retrieved Chunks ({chunks.length})
                </h3>
                <div className="text-sm text-gray-600">
                  Sorted by confidence
                </div>
              </div>

              {chunks.map((chunk, idx) => (
                <Card key={idx}>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <FileCode className="w-5 h-5 text-primary-600" />
                        <div>
                          <p className="font-semibold text-gray-900">{chunk.file_path}</p>
                          <p className="text-sm text-gray-600">
                            Lines {chunk.start_line}-{chunk.end_line} • {chunk.language}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant={
                          chunk.confidence >= 80 ? 'success' :
                          chunk.confidence >= 60 ? 'warning' : 'danger'
                        }>
                          {chunk.confidence}% confident
                        </Badge>
                        {chunk.distance !== undefined && (
                          <Badge variant="info">
                            Distance: {chunk.distance.toFixed(3)}
                          </Badge>
                        )}
                      </div>
                    </div>

                    <CodeBlock code={chunk.snippet} language={chunk.language} />

                    {chunk.reasons && chunk.reasons.length > 0 && (
                      <details className="text-sm">
                        <summary className="cursor-pointer text-gray-700 font-medium hover:text-gray-900">
                          View reasoning ({chunk.reasons.length} factors)
                        </summary>
                        <div className="mt-2 space-y-2 p-3 bg-gray-50 rounded-lg">
                          {chunk.reasons.map((reason, ridx) => (
                            <div key={ridx} className="flex items-start gap-2">
                              <span className="text-primary-600">•</span>
                              <div className="flex-1">
                                <span className="font-medium">{reason.type}</span>
                                <span className="text-gray-600"> (score: {reason.score.toFixed(2)})</span>
                                <p className="text-gray-700 mt-1">{reason.explanation}</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}