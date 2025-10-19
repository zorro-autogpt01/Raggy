// codecontext-rag/frontend/src/pages/AgentFeedback.tsx
import React, { useState, useEffect } from 'react'
import { Card } from '../components/shared/Card'
import { LoadingSpinner } from '../components/shared/LoadingSpinner'
import { ErrorMessage } from '../components/shared/ErrorMessage'
import { api } from '../services/api'
import { TrendingUp, Target, Activity, Zap } from 'lucide-react'
import type { Repository } from '../types/index'

export const AgentFeedback: React.FC = () => {
  const [repos, setRepos] = useState<Repository[]>([])
  const [selectedRepo, setSelectedRepo] = useState<string>('')
  const [summary, setSummary] = useState<any>(null)
  const [profile, setProfile] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')

  useEffect(() => {
    loadRepos()
  }, [])

  useEffect(() => {
    if (selectedRepo) {
      loadData()
    }
  }, [selectedRepo])

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

  const loadData = async () => {
    if (!selectedRepo) return

    try {
      setLoading(true)
      setError('')
      
      const [summaryData, profileData] = await Promise.all([
        api.getFeedbackSummary(selectedRepo),
        api.getRetrievalProfile(selectedRepo)
      ])
      
      setSummary(summaryData)
      setProfile(profileData)
    } catch (err: any) {
      setError(err.message || 'Failed to load feedback data')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <Card title="AI Learning Dashboard">
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
        </div>
      </Card>

      {error && <ErrorMessage message={error} onRetry={loadData} />}

      {loading ? (
        <LoadingSpinner text="Loading feedback data..." />
      ) : (
        <>
          {summary && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <Card>
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-600">Retrieval Precision</p>
                    <p className="mt-2 text-3xl font-bold text-gray-900">
                      {Math.round((summary.avg_retrieval_precision || 0) * 100)}%
                    </p>
                  </div>
                  <div className="p-3 rounded-lg bg-blue-100">
                    <Target className="w-6 h-6 text-blue-600" />
                  </div>
                </div>
              </Card>

              <Card>
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-600">Execution Success</p>
                    <p className="mt-2 text-3xl font-bold text-gray-900">
                      {Math.round((summary.execution_success_rate || 0) * 100)}%
                    </p>
                  </div>
                  <div className="p-3 rounded-lg bg-green-100">
                    <Activity className="w-6 h-6 text-green-600" />
                  </div>
                </div>
              </Card>

              <Card>
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-600">Blast Radius Accuracy</p>
                    <p className="mt-2 text-3xl font-bold text-gray-900">
                      {Math.round((summary.avg_blast_radius_accuracy || 0) * 100)}%
                    </p>
                  </div>
                  <div className="p-3 rounded-lg bg-purple-100">
                    <Zap className="w-6 h-6 text-purple-600" />
                  </div>
                </div>
              </Card>

              <Card>
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-600">Change Success</p>
                    <p className="mt-2 text-3xl font-bold text-gray-900">
                      {Math.round((summary.change_success_rate || 0) * 100)}%
                    </p>
                  </div>
                  <div className="p-3 rounded-lg bg-yellow-100">
                    <TrendingUp className="w-6 h-6 text-yellow-600" />
                  </div>
                </div>
              </Card>
            </div>
          )}

          {profile && (
            <Card title="Current Retrieval Profile">
              <div className="space-y-6">
                <div>
                  <h4 className="font-semibold text-gray-900 mb-4">Retrieval Weights</h4>
                  <div className="space-y-3">
                    {profile.weights && Object.entries(profile.weights).map(([key, value]: [string, any]) => (
                      <div key={key}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm text-gray-700">{key}</span>
                          <span className="text-sm font-medium text-gray-900">
                            {typeof value === 'number' ? value.toFixed(2) : value}
                          </span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2">
                          <div
                            className="bg-primary-600 h-2 rounded-full"
                            style={{ width: `${typeof value === 'number' ? value * 100 : 0}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {profile.hybrid_alpha !== undefined && (
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-semibold text-gray-900">Hybrid Alpha</h4>
                      <span className="text-sm font-medium text-gray-900">
                        {profile.hybrid_alpha.toFixed(2)}
                      </span>
                    </div>
                    <div className="w-full bg-gray-200 rounded-full h-2">
                      <div
                        className="bg-purple-600 h-2 rounded-full"
                        style={{ width: `${profile.hybrid_alpha * 100}%` }}
                      />
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-200">
                  {profile.agentic_expansion_enabled !== undefined && (
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={profile.agentic_expansion_enabled}
                        disabled
                        className="w-4 h-4"
                      />
                      <span className="text-sm text-gray-700">Agentic Expansion</span>
                    </div>
                  )}
                  {profile.agentic_neighbor_enabled !== undefined && (
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={profile.agentic_neighbor_enabled}
                        disabled
                        className="w-4 h-4"
                      />
                      <span className="text-sm text-gray-700">Agentic Neighbors</span>
                    </div>
                  )}
                </div>

                {profile.last_updated && (
                  <div className="pt-4 border-t border-gray-200">
                    <p className="text-xs text-gray-500">
                      Last updated: {new Date(profile.last_updated).toLocaleString()}
                    </p>
                  </div>
                )}
              </div>
            </Card>
          )}

          {!loading && !summary && !profile && (
            <Card>
              <div className="text-center py-12">
                <Activity className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-600 mb-2">No feedback data available</p>
                <p className="text-sm text-gray-500">
                  Feedback data will appear here as the system learns from usage
                </p>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}