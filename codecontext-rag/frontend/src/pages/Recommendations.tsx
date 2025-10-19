// codecontext-rag/frontend/src/pages/Recommendations.tsx (Enhanced)
import React, { useState } from 'react'
import { Card } from '../components/shared/Card'
import { Button } from '../components/shared/Button'
import { Badge } from '../components/shared/Badge'
import { LoadingSpinner } from '../components/shared/LoadingSpinner'
import { ErrorMessage } from '../components/shared/ErrorMessage'
import { api } from '../services/api'
import { TrendingUp, FileCode, AlertCircle, ThumbsUp, ThumbsDown, RefreshCw } from 'lucide-react'
import type { Repository, FileRecommendation } from '../types/index'

export const Recommendations: React.FC = () => {
  const [repos, setRepos] = useState<Repository[]>([])
  const [selectedRepo, setSelectedRepo] = useState<string>('')
  const [query, setQuery] = useState('implement user authentication with email and password')
  const [maxResults, setMaxResults] = useState(10)
  const [recommendations, setRecommendations] = useState<FileRecommendation[]>([])
  const [sessionId, setSessionId] = useState<string>('')
  const [summary, setSummary] = useState<any>(null)
  const [explanation, setExplanation] = useState<string>('')
  const [canRefine, setCanRefine] = useState(false)
  const [loading, setLoading] = useState(false)
  const [interactive, setInteractive] = useState(false)
  const [error, setError] = useState<string>('')
  const [showFeedback, setShowFeedback] = useState(false)
  const [relevantFiles, setRelevantFiles] = useState<Set<string>>(new Set())
  const [irrelevantFiles, setIrrelevantFiles] = useState<Set<string>>(new Set())
  const [feedbackComments, setFeedbackComments] = useState('')
  const [refineContext, setRefineContext] = useState('')

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

  const getRecommendations = async () => {
    if (!selectedRepo || !query) return

    try {
      setLoading(true)
      setError('')
      
      const endpoint = interactive ? 'interactiveRecommendations' : 'getRecommendations'
      const data = await api[endpoint]({
        repository_id: selectedRepo,
        query,
        max_results: maxResults
      })
      
      setRecommendations(data.recommendations || [])
      setSessionId(data.session_id || '')
      setSummary(data.summary || null)
      setExplanation(data.explanation || '')
      setCanRefine(data.can_refine || false)
      setRelevantFiles(new Set())
      setIrrelevantFiles(new Set())
    } catch (err: any) {
      setError(err.message || 'Failed to get recommendations')
    } finally {
      setLoading(false)
    }
  }

  const handleRefine = async () => {
    if (!sessionId || !refineContext) return

    try {
      setLoading(true)
      setError('')
      
      const data = await api.refineRecommendations({
        session_id: sessionId,
        additional_context: refineContext,
        positive_examples: Array.from(relevantFiles),
        negative_examples: Array.from(irrelevantFiles),
        max_results: maxResults
      })
      
      setRecommendations(data.recommendations || [])
      setExplanation(data.explanation || '')
      setSummary(data.summary || null)
      setRefineContext('')
    } catch (err: any) {
      setError(err.message || 'Failed to refine recommendations')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmitFeedback = async () => {
    if (!sessionId || !selectedRepo) return

    try {
      setLoading(true)
      await api.submitRecommendationFeedback(sessionId, selectedRepo, {
        relevant_files: Array.from(relevantFiles),
        irrelevant_files: Array.from(irrelevantFiles),
        comments: feedbackComments
      })
      
      alert('Feedback submitted successfully!')
      setShowFeedback(false)
      setFeedbackComments('')
    } catch (err: any) {
      setError(err.message || 'Failed to submit feedback')
    } finally {
      setLoading(false)
    }
  }

  const toggleRelevant = (filePath: string) => {
    setRelevantFiles(prev => {
      const next = new Set(prev)
      if (next.has(filePath)) {
        next.delete(filePath)
      } else {
        next.add(filePath)
        irrelevantFiles.delete(filePath)
      }
      return next
    })
  }

  const toggleIrrelevant = (filePath: string) => {
    setIrrelevantFiles(prev => {
      const next = new Set(prev)
      if (next.has(filePath)) {
        next.delete(filePath)
      } else {
        next.add(filePath)
        relevantFiles.delete(filePath)
      }
      return next
    })
  }

  const getConfidenceVariant = (confidence: number) => {
    if (confidence >= 80) return 'success'
    if (confidence >= 60) return 'warning'
    return 'danger'
  }

  return (
    <div className="space-y-6">
      <Card title="Get File Recommendations">
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
              Feature Description
            </label>
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              rows={3}
              placeholder="Describe the feature you want to implement..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Max Results
              </label>
              <input
                type="number"
                min="1"
                max="50"
                value={maxResults}
                onChange={(e) => setMaxResults(parseInt(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={interactive}
                  onChange={(e) => setInteractive(e.target.checked)}
                  className="w-4 h-4"
                />
                <span className="text-sm text-gray-700">Use interactive mode (LLM explanations)</span>
              </label>
            </div>
          </div>

          <Button
            icon={<TrendingUp className="w-4 h-4" />}
            onClick={getRecommendations}
            loading={loading}
            disabled={!selectedRepo || !query}
          >
            Get Recommendations
          </Button>
        </div>
      </Card>

      {error && <ErrorMessage message={error} onRetry={getRecommendations} />}

      {loading && <LoadingSpinner text="Analyzing codebase..." />}

      {recommendations.length > 0 && (
        <>
          {summary && (
            <Card>
              <div className="grid grid-cols-3 gap-6">
                <div>
                  <p className="text-sm text-gray-600">Total Files</p>
                  <p className="text-2xl font-bold text-gray-900">{summary.total_files}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Avg Confidence</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {Math.round(summary.avg_confidence)}%
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">Session ID</p>
                  <p className="text-sm font-mono text-gray-600">{sessionId.slice(0, 8)}...</p>
                </div>
              </div>

              {explanation && (
                <div className="mt-4 p-4 bg-purple-50 border border-purple-200 rounded-lg">
                  <p className="text-sm text-purple-900">{explanation}</p>
                </div>
              )}
            </Card>
          )}

          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-gray-900">
              Recommendations ({recommendations.length})
            </h3>
            <div className="flex items-center gap-3">
              {canRefine && (
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<RefreshCw className="w-4 h-4" />}
                  onClick={() => setShowFeedback(!showFeedback)}
                >
                  {showFeedback ? 'Hide' : 'Refine / Feedback'}
                </Button>
              )}
            </div>
          </div>

          {showFeedback && (
            <Card title="Refine Recommendations">
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Additional Context
                  </label>
                  <textarea
                    value={refineContext}
                    onChange={(e) => setRefineContext(e.target.value)}
                    rows={3}
                    placeholder="Add more details to refine recommendations..."
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Feedback Comments (optional)
                  </label>
                  <textarea
                    value={feedbackComments}
                    onChange={(e) => setFeedbackComments(e.target.value)}
                    rows={2}
                    placeholder="Any additional feedback..."
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>

                <div className="flex items-center gap-3">
                  <Button
                    onClick={handleRefine}
                    loading={loading}
                    disabled={!refineContext}
                  >
                    Refine
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={handleSubmitFeedback}
                    loading={loading}
                  >
                    Submit Feedback
                  </Button>
                </div>

                <div className="pt-3 border-t border-gray-200">
                  <p className="text-sm text-gray-600 mb-2">
                    Mark files as relevant or irrelevant to improve future recommendations
                  </p>
                  <div className="flex items-center gap-4 text-sm text-gray-500">
                    <span>✓ {relevantFiles.size} relevant</span>
                    <span>✗ {irrelevantFiles.size} irrelevant</span>
                  </div>
                </div>
              </div>
            </Card>
          )}

          <div className="space-y-3">
            {recommendations.map((rec, idx) => (
              <Card key={idx}>
                <div className="space-y-3">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3 flex-1">
                      <div className={`w-2 h-2 rounded-full ${
                        rec.confidence >= 80 ? 'bg-green-400' :
                        rec.confidence >= 60 ? 'bg-yellow-400' :
                        'bg-orange-400'
                      }`}></div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <FileCode className="w-4 h-4 text-primary-600" />
                          <span className="text-white font-medium">{rec.file_path}</span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <Badge variant={getConfidenceVariant(rec.confidence)}>
                        {rec.confidence}%
                      </Badge>
                      {showFeedback && (
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => toggleRelevant(rec.file_path)}
                            className={`p-1 rounded ${
                              relevantFiles.has(rec.file_path)
                                ? 'bg-green-100 text-green-700'
                                : 'text-gray-400 hover:text-green-600'
                            }`}
                            title="Mark as relevant"
                          >
                            <ThumbsUp className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => toggleIrrelevant(rec.file_path)}
                            className={`p-1 rounded ${
                              irrelevantFiles.has(rec.file_path)
                                ? 'bg-red-100 text-red-700'
                                : 'text-gray-400 hover:text-red-600'
                            }`}
                            title="Mark as irrelevant"
                          >
                            <ThumbsDown className="w-4 h-4" />
                          </button>
                        </div>
                      )}
                    </div>
                  </div>

                  {rec.reasons && rec.reasons.length > 0 && (
                    <div className="space-y-2">
                      {rec.reasons.map((reason, ridx) => (
                        <div key={ridx} className="flex items-start gap-2 text-sm">
                          <AlertCircle className="w-4 h-4 text-primary-600 mt-0.5 flex-shrink-0" />
                          <div className="flex-1">
                            <span className="font-medium">{reason.type}:</span>{' '}
                            <span className="text-gray-600">{reason.explanation}</span>
                            <span className="text-gray-500 ml-2">
                              (score: {reason.score.toFixed(2)})
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {rec.metadata && (
                    <div className="pt-3 border-t border-gray-200 text-sm text-gray-600">
                      <span>Language: {rec.metadata.language || 'unknown'}</span>
                      {rec.metadata.lines_of_code && (
                        <span className="ml-4">Lines: {rec.metadata.lines_of_code}</span>
                      )}
                    </div>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  )
}