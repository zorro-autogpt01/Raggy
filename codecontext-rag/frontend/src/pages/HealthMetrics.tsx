// codecontext-rag/frontend/src/pages/HealthMetrics.tsx
import React, { useState, useEffect } from 'react'
import { Card } from '../components/shared/Card'
import { Button } from '../components/shared/Button'
import { Badge } from '../components/shared/Badge'
import { LoadingSpinner } from '../components/shared/LoadingSpinner'
import { ErrorMessage } from '../components/shared/ErrorMessage'
import { api } from '../services/api'
import { Activity, Database, RefreshCw, CheckCircle, XCircle, AlertCircle } from 'lucide-react'

export const HealthMetrics: React.FC = () => {
  const [health, setHealth] = useState<any>(null)
  const [searchHealth, setSearchHealth] = useState<any>(null)
  const [metrics, setMetrics] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      setLoading(true)
      setError('')
      
      const [healthData, searchHealthData, metricsData] = await Promise.allSettled([
        api.health(),
        api.searchHealth(),
        api.metrics().catch(() => ({ enabled: false }))
      ])
      
      if (healthData.status === 'fulfilled') {
        setHealth(healthData.value)
      }
      if (searchHealthData.status === 'fulfilled') {
        setSearchHealth(searchHealthData.value)
      }
      if (metricsData.status === 'fulfilled') {
        setMetrics(metricsData.value)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load health data')
    } finally {
      setLoading(false)
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'healthy':
      case 'available':
      case 'ok':
        return <CheckCircle className="w-5 h-5 text-green-500" />
      case 'unavailable':
      case 'error':
        return <XCircle className="w-5 h-5 text-red-500" />
      default:
        return <AlertCircle className="w-5 h-5 text-yellow-500" />
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'healthy':
      case 'available':
      case 'ok':
        return <Badge variant="success">{status}</Badge>
      case 'unavailable':
      case 'error':
        return <Badge variant="danger">{status}</Badge>
      default:
        return <Badge variant="warning">{status}</Badge>
    }
  }

  const formatUptime = (seconds: number) => {
    const days = Math.floor(seconds / 86400)
    const hours = Math.floor((seconds % 86400) / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    
    if (days > 0) {
      return `${days}d ${hours}h ${minutes}m`
    } else if (hours > 0) {
      return `${hours}h ${minutes}m`
    } else {
      return `${minutes}m`
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-gray-900">System Health & Metrics</h2>
            <p className="mt-1 text-sm text-gray-600">
              Monitor the status of all system components
            </p>
          </div>
          <Button 
            icon={<RefreshCw className="w-4 h-4" />}
            variant="secondary"
            onClick={loadData}
            loading={loading}
          >
            Refresh
          </Button>
        </div>
      </Card>

      {error && <ErrorMessage message={error} onRetry={loadData} />}

      {loading ? (
        <LoadingSpinner text="Loading health data..." />
      ) : (
        <>
          {health && (
            <Card title="API Health">
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    {getStatusIcon(health.status)}
                    <div>
                      <p className="font-semibold text-gray-900">Status</p>
                      <p className="text-sm text-gray-600">API Server</p>
                    </div>
                  </div>
                  {getStatusBadge(health.status)}
                </div>

                <div className="grid grid-cols-2 gap-6">
                  {health.version && (
                    <div>
                      <p className="text-sm text-gray-600 mb-1">Version</p>
                      <p className="text-lg font-semibold text-gray-900">{health.version}</p>
                    </div>
                  )}
                  {health.uptime !== undefined && (
                    <div>
                      <p className="text-sm text-gray-600 mb-1">Uptime</p>
                      <p className="text-lg font-semibold text-gray-900">
                        {formatUptime(health.uptime)}
                      </p>
                    </div>
                  )}
                </div>

                {health.dependencies && (
                  <div>
                    <h4 className="font-semibold text-gray-900 mb-3">Dependencies</h4>
                    <div className="space-y-3">
                      {Object.entries(health.dependencies).map(([name, status]: [string, any]) => (
                        <div key={name} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                          <div className="flex items-center gap-3">
                            <Database className="w-4 h-4 text-gray-600" />
                            <span className="font-medium text-gray-900 capitalize">{name}</span>
                          </div>
                          {getStatusBadge(typeof status === 'string' ? status : 'healthy')}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </Card>
          )}

          {searchHealth && (
            <Card title="Search Service Health">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    {getStatusIcon(searchHealth.status)}
                    <div>
                      <p className="font-semibold text-gray-900">Search Service</p>
                      <p className="text-sm text-gray-600">{searchHealth.service}</p>
                    </div>
                  </div>
                  {getStatusBadge(searchHealth.status)}
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="p-3 bg-gray-50 rounded-lg">
                    <p className="text-sm text-gray-600 mb-1">Vector Store</p>
                    {getStatusBadge(searchHealth.vector_store)}
                  </div>
                  <div className="p-3 bg-gray-50 rounded-lg">
                    <p className="text-sm text-gray-600 mb-1">Embedder</p>
                    {getStatusBadge(searchHealth.embedder)}
                  </div>
                </div>

                {searchHealth.search_types && (
                  <div>
                    <p className="text-sm font-medium text-gray-700 mb-2">Available Search Types</p>
                    <div className="flex flex-wrap gap-2">
                      {searchHealth.search_types.map((type: string) => (
                        <Badge key={type}>{type}</Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </Card>
          )}

          {metrics && metrics.enabled !== false && (
            <Card title="System Metrics">
              <div className="space-y-4">
                {Object.entries(metrics).map(([key, value]: [string, any]) => {
                  if (key === 'enabled') return null
                  
                  return (
                    <div key={key} className="p-4 bg-gray-50 rounded-lg">
                      <div className="flex items-center justify-between mb-2">
                        <h5 className="font-medium text-gray-900">{key.replace(/_/g, ' ')}</h5>
                        <Activity className="w-4 h-4 text-gray-600" />
                      </div>
                      {typeof value === 'object' ? (
                        <div className="grid grid-cols-2 gap-2 text-sm">
                          {Object.entries(value).map(([subKey, subValue]: [string, any]) => (
                            <div key={subKey}>
                              <p className="text-gray-600">{subKey}</p>
                              <p className="font-semibold text-gray-900">{String(subValue)}</p>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-lg font-semibold text-gray-900">{String(value)}</p>
                      )}
                    </div>
                  )
                })}
              </div>
            </Card>
          )}

          {metrics && metrics.enabled === false && (
            <Card>
              <div className="text-center py-12">
                <Activity className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-600 mb-2">Metrics not enabled</p>
                <p className="text-sm text-gray-500">
                  Enable metrics in server configuration to see detailed statistics
                </p>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}