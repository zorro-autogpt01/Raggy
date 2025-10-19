// codecontext-rag/frontend/src/pages/TaskAnalysis.tsx
import React, { useState, useEffect } from 'react'
import { Card } from '../components/shared/Card'
import { Button } from '../components/shared/Button'
import { Badge } from '../components/shared/Badge'
import { LoadingSpinner } from '../components/shared/LoadingSpinner'
import { ErrorMessage } from '../components/shared/ErrorMessage'
import { api } from '../services/api'
import { Brain, Zap, FileText, AlertTriangle } from 'lucide-react'
import type { Repository } from '../types/index'

export const TaskAnalysis: React.FC = () => {
  const [repos, setRepos] = useState<Repository[]>([])
  const [selectedRepo, setSelectedRepo] = useState<string>('')
  const [taskDescription, setTaskDescription] = useState('')
  const [analysis, setAnalysis] = useState<any>(null)
  const [strategy, setStrategy] = useState<any>(null)
  const [rules, setRules] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')

  useEffect(() => {
    loadRepos()
    loadRules()
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

  const loadRules = async () => {
    try {
      const data = await api.getStrategyRules()
      setRules(data.rules || [])
    } catch (err: any) {
      console.error('Failed to load rules:', err)
    }
  }

  const handleAnalyze = async () => {
    if (!selectedRepo || !taskDescription) return

    try {
      setLoading(true)
      setError('')
      const data = await api.analyzeTask({
        repo_id: selectedRepo,
        task_description: taskDescription
      })
      setAnalysis(data.analysis)
      
      // Automatically select strategy based on analysis
      if (data.analysis) {
        const strategyData = await api.selectStrategy({
          task_type: data.analysis.task_type,
          complexity: data.analysis.complexity,
          impact: data.analysis.impact,
          estimated_file_count: data.analysis.estimated_file_count,
          is_breaking_change: data.analysis.is_breaking_change,
          needs_database_migration: data.analysis.needs_database_migration,
          confidence_score: data.analysis.confidence_score,
          repo_id: selectedRepo,
          task_description: taskDescription
        })
        setStrategy(strategyData.decision)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to analyze task')
    } finally {
      setLoading(false)
    }
  }

  const getComplexityBadge = (complexity: string) => {
    switch (complexity?.toLowerCase()) {
      case 'simple':
        return <Badge variant="success">Simple</Badge>
      case 'moderate':
        return <Badge variant="warning">Moderate</Badge>
      case 'complex':
        return <Badge variant="danger">Complex</Badge>
      default:
        return <Badge>Unknown</Badge>
    }
  }

  const getImpactBadge = (impact: string) => {
    switch (impact?.toLowerCase()) {
      case 'low':
        return <Badge variant="success">Low Impact</Badge>
      case 'medium':
        return <Badge variant="warning">Medium Impact</Badge>
      case 'high':
        return <Badge variant="danger">High Impact</Badge>
      default:
        return <Badge>Unknown</Badge>
    }
  }

  return (
    <div className="space-y-6">
      <Card title="Task Analysis">
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
              Task Description
            </label>
            <textarea
              value={taskDescription}
              onChange={(e) => setTaskDescription(e.target.value)}
              rows={4}
              placeholder="Describe the task in detail..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>

          <Button
            icon={<Brain className="w-4 h-4" />}
            onClick={handleAnalyze}
            loading={loading}
            disabled={!selectedRepo || !taskDescription}
          >
            Analyze Task
          </Button>
        </div>
      </Card>

      {error && <ErrorMessage message={error} onRetry={handleAnalyze} />}

      {loading && <LoadingSpinner text="Analyzing task..." />}

      {analysis && (
        <>
          <Card title="Analysis Results">
            <div className="space-y-6">
              <div className="grid grid-cols-3 gap-6">
                <div>
                  <p className="text-sm text-gray-600 mb-2">Task Type</p>
                  <p className="text-lg font-semibold text-gray-900">{analysis.task_type}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600 mb-2">Complexity</p>
                  {getComplexityBadge(analysis.complexity)}
                </div>
                <div>
                  <p className="text-sm text-gray-600 mb-2">Impact</p>
                  {getImpactBadge(analysis.impact)}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-6">
                <div className="p-4 bg-blue-50 rounded-lg">
                  <div className="flex items-center gap-2 mb-2">
                    <FileText className="w-4 h-4 text-blue-600" />
                    <p className="text-sm font-medium text-gray-700">Estimated Files</p>
                  </div>
                  <p className="text-2xl font-bold text-gray-900">{analysis.estimated_file_count}</p>
                </div>
                <div className="p-4 bg-purple-50 rounded-lg">
                  <div className="flex items-center gap-2 mb-2">
                    <Zap className="w-4 h-4 text-purple-600" />
                    <p className="text-sm font-medium text-gray-700">Confidence Score</p>
                  </div>
                  <p className="text-2xl font-bold text-gray-900">
                    {Math.round(analysis.confidence_score * 100)}%
                  </p>
                </div>
              </div>

              {analysis.files_to_modify && analysis.files_to_modify.length > 0 && (
                <div>
                  <h4 className="font-semibold text-gray-900 mb-3">Files to Modify</h4>
                  <div className="flex flex-wrap gap-2">
                    {analysis.files_to_modify.map((file: string, idx: number) => (
                      <Badge key={idx}>{file}</Badge>
                    ))}
                  </div>
                </div>
              )}

              {analysis.summary && (
                <div className="p-4 bg-gray-50 rounded-lg">
                  <h4 className="font-semibold text-gray-900 mb-2">Summary</h4>
                  <p className="text-sm text-gray-700">{analysis.summary}</p>
                </div>
              )}

              {analysis.risks && analysis.risks.length > 0 && (
                <div className="p-4 bg-yellow-50 rounded-lg">
                  <div className="flex items-center gap-2 mb-3">
                    <AlertTriangle className="w-5 h-5 text-yellow-600" />
                    <h4 className="font-semibold text-gray-900">Risks</h4>
                  </div>
                  <ul className="space-y-1">
                    {analysis.risks.map((risk: string, idx: number) => (
                      <li key={idx} className="text-sm text-gray-700">• {risk}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={analysis.is_breaking_change}
                    disabled
                    className="w-4 h-4"
                  />
                  <span className="text-sm text-gray-700">Breaking Change</span>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={analysis.needs_database_migration}
                    disabled
                    className="w-4 h-4"
                  />
                  <span className="text-sm text-gray-700">Database Migration Required</span>
                </div>
              </div>
            </div>
          </Card>

          {strategy && (
            <Card title="Recommended Strategy">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-600">Strategy</p>
                    <p className="text-xl font-bold text-gray-900">{strategy.strategy}</p>
                  </div>
                  <Badge variant={strategy.confidence > 0.8 ? 'success' : 'warning'}>
                    {Math.round(strategy.confidence * 100)}% confident
                  </Badge>
                </div>

                <div className="p-4 bg-blue-50 rounded-lg">
                  <p className="text-sm font-medium text-gray-700 mb-2">Primary Reason</p>
                  <p className="text-sm text-gray-900">{strategy.primary_reason}</p>
                </div>

                {strategy.contributing_factors && strategy.contributing_factors.length > 0 && (
                  <div>
                    <h4 className="font-semibold text-gray-900 mb-2">Contributing Factors</h4>
                    <ul className="space-y-1">
                      {strategy.contributing_factors.map((factor: string, idx: number) => (
                        <li key={idx} className="text-sm text-gray-700">• {factor}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {strategy.rules_applied && strategy.rules_applied.length > 0 && (
                  <div>
                    <h4 className="font-semibold text-gray-900 mb-2">Rules Applied</h4>
                    <div className="flex flex-wrap gap-2">
                      {strategy.rules_applied.map((rule: string, idx: number) => (
                        <Badge key={idx} variant="info">{rule}</Badge>
                      ))}
                    </div>
                  </div>
                )}

                {strategy.risk_factors && strategy.risk_factors.length > 0 && (
                  <div className="p-4 bg-yellow-50 rounded-lg">
                    <h4 className="font-semibold text-gray-900 mb-2">Risk Factors</h4>
                    <ul className="space-y-1">
                      {strategy.risk_factors.map((risk: string, idx: number) => (
                        <li key={idx} className="text-sm text-gray-700">• {risk}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {strategy.explanation && (
                  <div className="p-4 bg-gray-50 rounded-lg">
                    <p className="text-sm text-gray-700">{strategy.explanation}</p>
                  </div>
                )}
              </div>
            </Card>
          )}
        </>
      )}

      {rules.length > 0 && (
        <Card title="Strategy Selection Rules">
          <div className="space-y-3">
            {rules.map((rule, idx) => (
              <div key={idx} className="p-4 bg-gray-50 rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <h5 className="font-semibold text-gray-900">{rule.name}</h5>
                  <Badge>{rule.suggested_strategy}</Badge>
                </div>
                <p className="text-sm text-gray-700 mb-2">{rule.reasoning}</p>
                <p className="text-xs text-gray-500">Priority: {rule.priority}</p>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}