// codecontext-rag/frontend/src/pages/Orchestration.tsx
import React, { useState, useEffect } from 'react'
import { Card } from '../components/shared/Card'
import { Button } from '../components/shared/Button'
import { Badge } from '../components/shared/Badge'
import { ErrorMessage } from '../components/shared/ErrorMessage'
import { api } from '../services/api'
import { Play, Clock, CheckCircle, XCircle, AlertCircle } from 'lucide-react'
import type { Repository } from '../types/index'

interface OrchestrateStep {
  step_id: string
  type: 'branch_create' | 'patch_apply' | 'validate' | 'branch_merge'
  status: 'pending' | 'running' | 'success' | 'failed'
  params?: any
  result?: any
  error?: string
  timestamp: string
}

interface OrchestrateExecution {
  execution_id: string
  status: 'running' | 'completed' | 'failed'
  task_analysis?: any
  strategy?: any
  steps: OrchestrateStep[]
  final_result?: any
  started_at: string
  completed_at?: string
}

export const Orchestration: React.FC = () => {
  const [repos, setRepos] = useState<Repository[]>([])
  const [selectedRepo, setSelectedRepo] = useState<string>('')
  const [taskDescription, setTaskDescription] = useState('')
  const [execution, setExecution] = useState<OrchestrateExecution | null>(null)
  const [executions, setExecutions] = useState<OrchestrateExecution[]>([])
  const [loading, setLoading] = useState(false)
  // @ts-ignore - keeping for future use
  const [polling, setPolling] = useState(false)
  const [error, setError] = useState<string>('')

  useEffect(() => {
    loadRepos()
  }, [])

  useEffect(() => {
    if (selectedRepo) {
      loadExecutions()
    }
  }, [selectedRepo])

  useEffect(() => {
    if (execution && execution.status === 'running') {
      const interval = setInterval(() => {
        pollStatus(execution.execution_id)
      }, 2000)
      return () => clearInterval(interval)
    }
  }, [execution])

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

  const loadExecutions = async () => {
    try {
      const data = await api.listOrchestrations(selectedRepo)
      setExecutions(data.executions || [])
    } catch (err: any) {
      console.error('Failed to load executions:', err)
    }
  }

  const handleExecute = async () => {
    if (!selectedRepo || !taskDescription) return

    try {
      setLoading(true)
      setError('')
      const data = await api.executeOrchestration({
        repo_id: selectedRepo,
        task_description: taskDescription
      })
      setExecution(data)
    } catch (err: any) {
      setError(err.message || 'Failed to start orchestration')
    } finally {
      setLoading(false)
    }
  }

  const pollStatus = async (executionId: string) => {
    try {
      const data = await api.getOrchestrationStatus(executionId)
      setExecution(data)
      if (data.status !== 'running') {
        loadExecutions()
      }
    } catch (err: any) {
      console.error('Polling error:', err)
    } finally {
      setPolling(false)
    }
  }

  const getStepIcon = (step: OrchestrateStep) => {
    switch (step.status) {
      case 'success':
        return <CheckCircle className="w-5 h-5 text-green-500" />
      case 'failed':
        return <XCircle className="w-5 h-5 text-red-500" />
      case 'running':
        return <Clock className="w-5 h-5 text-blue-500 animate-spin" />
      default:
        return <AlertCircle className="w-5 h-5 text-gray-400" />
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <Badge variant="success">Completed</Badge>
      case 'running':
        return <Badge variant="info">Running</Badge>
      case 'failed':
        return <Badge variant="danger">Failed</Badge>
      default:
        return <Badge>Pending</Badge>
    }
  }

  return (
    <div className="space-y-6">
      <Card title="Orchestration Execution">
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
              placeholder="Describe the task you want to execute..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>

          <Button
            icon={<Play className="w-4 h-4" />}
            onClick={handleExecute}
            loading={loading}
            disabled={!selectedRepo || !taskDescription}
          >
            Execute Orchestration
          </Button>
        </div>
      </Card>

      {error && <ErrorMessage message={error} onRetry={handleExecute} />}

      {execution && (
        <Card title={`Execution: ${execution.execution_id}`}>
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">Status</p>
                {getStatusBadge(execution.status)}
              </div>
              <div>
                <p className="text-sm text-gray-600">Started</p>
                <p className="text-sm font-medium text-gray-900">
                  {new Date(execution.started_at).toLocaleString()}
                </p>
              </div>
              {execution.completed_at && (
                <div>
                  <p className="text-sm text-gray-600">Completed</p>
                  <p className="text-sm font-medium text-gray-900">
                    {new Date(execution.completed_at).toLocaleString()}
                  </p>
                </div>
              )}
            </div>

            {execution.task_analysis && (
              <div className="p-4 bg-blue-50 rounded-lg">
                <h4 className="font-semibold text-gray-900 mb-2">Task Analysis</h4>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-gray-600">Type</p>
                    <p className="font-medium">{execution.task_analysis.task_type}</p>
                  </div>
                  <div>
                    <p className="text-gray-600">Complexity</p>
                    <p className="font-medium">{execution.task_analysis.complexity}</p>
                  </div>
                </div>
              </div>
            )}

            {execution.strategy && (
              <div className="p-4 bg-purple-50 rounded-lg">
                <h4 className="font-semibold text-gray-900 mb-2">Strategy</h4>
                <div className="text-sm">
                  <p className="text-gray-700">{execution.strategy.strategy}</p>
                  <p className="text-gray-600 mt-1">{execution.strategy.primary_reason}</p>
                </div>
              </div>
            )}

            <div>
              <h4 className="font-semibold text-gray-900 mb-4">Execution Steps</h4>
              <div className="space-y-3">
                {execution.steps.map((step, idx) => (
                  <div
                    key={step.step_id}
                    className="flex items-start gap-4 p-4 bg-gray-50 rounded-lg"
                  >
                    <div className="flex-shrink-0 mt-1">
                      {getStepIcon(step)}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center justify-between mb-1">
                        <h5 className="font-medium text-gray-900">
                          Step {idx + 1}: {step.type.replace(/_/g, ' ')}
                        </h5>
                        <Badge variant={
                          step.status === 'success' ? 'success' :
                          step.status === 'failed' ? 'danger' :
                          step.status === 'running' ? 'info' : 'default'
                        }>
                          {step.status}
                        </Badge>
                      </div>
                      {step.error && (
                        <p className="text-sm text-red-600 mt-1">{step.error}</p>
                      )}
                      {step.result && (
                        <details className="text-sm text-gray-600 mt-2">
                          <summary className="cursor-pointer">View result</summary>
                          <pre className="mt-2 p-2 bg-white rounded text-xs overflow-auto">
                            {JSON.stringify(step.result, null, 2)}
                          </pre>
                        </details>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {execution.final_result && (
              <div className="p-4 bg-green-50 rounded-lg">
                <h4 className="font-semibold text-gray-900 mb-2">Final Result</h4>
                <pre className="text-sm text-gray-700 overflow-auto">
                  {JSON.stringify(execution.final_result, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </Card>
      )}

      {executions.length > 0 && (
        <Card title="Recent Executions">
          <div className="space-y-3">
            {executions.slice(0, 10).map(exec => (
              <div
                key={exec.execution_id}
                className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors cursor-pointer"
                onClick={() => setExecution(exec)}
              >
                <div className="flex-1">
                  <p className="font-medium text-gray-900">{exec.execution_id}</p>
                  <p className="text-sm text-gray-600">
                    {new Date(exec.started_at).toLocaleString()}
                  </p>
                </div>
                {getStatusBadge(exec.status)}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}