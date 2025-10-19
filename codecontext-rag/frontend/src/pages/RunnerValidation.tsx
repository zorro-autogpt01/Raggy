// codecontext-rag/frontend/src/pages/RunnerValidation.tsx
import React, { useState, useEffect } from 'react'
import { Card } from '../components/shared/Card'
import { Button } from '../components/shared/Button'
import { Badge } from '../components/shared/Badge'
import { LoadingSpinner } from '../components/shared/LoadingSpinner'
import { ErrorMessage } from '../components/shared/ErrorMessage'
import { CodeBlock } from '../components/shared/CodeBlock'
import { api } from '../services/api'
import { Play, RefreshCw, CheckCircle, XCircle } from 'lucide-react'
import type { Repository } from '../types/index'

export const RunnerValidation: React.FC = () => {
  const [repos, setRepos] = useState<Repository[]>([])
  const [selectedRepo, setSelectedRepo] = useState<string>('')
  const [patch, setPatch] = useState('')
  const [commitMessage, setCommitMessage] = useState('')
  const [branch, setBranch] = useState('main')
  const [waitForCompletion, setWaitForCompletion] = useState(false)
  const [skipExecution, setSkipExecution] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [polling, setPolling] = useState(false)
  const [error, setError] = useState<string>('')

  useEffect(() => {
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

  const handleValidate = async () => {
    if (!selectedRepo || !patch || !commitMessage) return

    try {
      setLoading(true)
      setError('')
      const data = await api.validateWithRunner({
        repo_id: selectedRepo,
        patch,
        commit_message: commitMessage,
        branch,
        wait_for_completion: waitForCompletion,
        skip_execution_analysis: skipExecution
      })
      setResult(data)
      
      if (!waitForCompletion && data.run_id) {
        // Start polling if not waiting
        startPolling(data.run_id)
      }
    } catch (err: any) {
      setError(err.message || 'Validation failed')
    } finally {
      setLoading(false)
    }
  }

  const startPolling = async (runId: string) => {
    setPolling(true)
    const interval = setInterval(async () => {
      try {
        const data = await api.getValidationStatus(runId)
        setResult(data)
        
        if (data.completed || data.status === 'completed' || data.status === 'failed') {
          clearInterval(interval)
          setPolling(false)
        }
      } catch (err) {
        console.error('Polling error:', err)
        clearInterval(interval)
        setPolling(false)
      }
    }, 2000)
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
      case 'success':
        return <Badge variant="success">Completed</Badge>
      case 'failed':
        return <Badge variant="danger">Failed</Badge>
      case 'running':
        return <Badge variant="info">Running</Badge>
      default:
        return <Badge>Started</Badge>
    }
  }

  return (
    <div className="space-y-6">
      <Card title="Runner Validation">
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

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Commit Message
              </label>
              <input
                type="text"
                value={commitMessage}
                onChange={(e) => setCommitMessage(e.target.value)}
                placeholder="feat: add validation"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Branch
              </label>
              <input
                type="text"
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                placeholder="main"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Patch
            </label>
            <textarea
              value={patch}
              onChange={(e) => setPatch(e.target.value)}
              rows={8}
              placeholder="Paste your patch here..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 font-mono text-sm"
            />
          </div>

          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={waitForCompletion}
                onChange={(e) => setWaitForCompletion(e.target.checked)}
                className="w-4 h-4"
              />
              <span className="text-sm text-gray-700">Wait for completion</span>
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={skipExecution}
                onChange={(e) => setSkipExecution(e.target.checked)}
                className="w-4 h-4"
              />
              <span className="text-sm text-gray-700">Skip execution analysis</span>
            </label>
          </div>

          <div className="flex items-center gap-3">
            <Button
              icon={<Play className="w-4 h-4" />}
              onClick={handleValidate}
              loading={loading}
              disabled={!selectedRepo || !patch || !commitMessage}
            >
              Start Validation
            </Button>
            {result && result.run_id && (
              <Button
                icon={<RefreshCw className="w-4 h-4" />}
                variant="secondary"
                onClick={() => startPolling(result.run_id)}
                loading={polling}
              >
                Refresh Status
              </Button>
            )}
          </div>
        </div>
      </Card>

      {error && <ErrorMessage message={error} onRetry={handleValidate} />}

      {(loading || polling) && <LoadingSpinner text="Running validation..." />}

      {result && (
        <Card title={`Validation: ${result.run_id}`}>
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600 mb-1">Status</p>
                {getStatusBadge(result.status)}
              </div>
              {result.execution_enabled !== undefined && (
                <div>
                  <p className="text-sm text-gray-600 mb-1">Execution Analysis</p>
                  <Badge variant={result.execution_enabled ? 'success' : 'default'}>
                    {result.execution_enabled ? 'Enabled' : 'Disabled'}
                  </Badge>
                </div>
              )}
            </div>

            {result.attempts !== undefined && (
              <div>
                <p className="text-sm text-gray-600">Attempts</p>
                <p className="text-lg font-semibold text-gray-900">{result.attempts}</p>
              </div>
            )}

            {result.execution_result && (
              <div className="space-y-4">
                <div className="flex items-center gap-2 mb-3">
                  {result.execution_result.success ? (
                    <CheckCircle className="w-5 h-5 text-green-500" />
                  ) : (
                    <XCircle className="w-5 h-5 text-red-500" />
                  )}
                  <h4 className="font-semibold text-gray-900">Execution Result</h4>
                </div>

                {result.execution_result.tests_run !== undefined && (
                  <div className="grid grid-cols-3 gap-4 mb-4">
                    <div className="p-3 bg-blue-50 rounded-lg">
                      <p className="text-sm text-gray-600">Tests Run</p>
                      <p className="text-xl font-bold text-gray-900">
                        {result.execution_result.tests_run}
                      </p>
                    </div>
                    <div className="p-3 bg-green-50 rounded-lg">
                      <p className="text-sm text-gray-600">Tests Passed</p>
                      <p className="text-xl font-bold text-green-700">
                        {result.execution_result.tests_passed}
                      </p>
                    </div>
                    <div className="p-3 bg-red-50 rounded-lg">
                      <p className="text-sm text-gray-600">Tests Failed</p>
                      <p className="text-xl font-bold text-red-700">
                        {result.execution_result.tests_failed}
                      </p>
                    </div>
                  </div>
                )}

                {result.execution_result.stdout && (
                  <div>
                    <h5 className="text-sm font-medium text-gray-700 mb-2">Standard Output</h5>
                    <CodeBlock code={result.execution_result.stdout} language="text" />
                  </div>
                )}

                {result.execution_result.stderr && (
                  <div>
                    <h5 className="text-sm font-medium text-gray-700 mb-2">Standard Error</h5>
                    <CodeBlock code={result.execution_result.stderr} language="text" />
                  </div>
                )}

                {result.execution_result.runtime_seconds !== undefined && (
                  <p className="text-sm text-gray-600">
                    Runtime: {result.execution_result.runtime_seconds.toFixed(2)}s
                  </p>
                )}
              </div>
            )}

            {result.result && typeof result.result === 'object' && (
              <details className="text-sm">
                <summary className="cursor-pointer font-medium text-gray-700 mb-2">
                  View full result
                </summary>
                <pre className="p-3 bg-gray-50 rounded-lg overflow-auto text-xs">
                  {JSON.stringify(result.result, null, 2)}
                </pre>
              </details>
            )}
          </div>
        </Card>
      )}
    </div>
  )
}