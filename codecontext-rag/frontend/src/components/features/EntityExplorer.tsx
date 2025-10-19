// codecontext-rag/frontend/src/components/features/EntityExplorer.tsx
import React, { useState } from 'react'
import { Card } from '../shared/Card'
import { Button } from '../shared/Button'
import { Badge } from '../shared/Badge'
import { CodeBlock } from '../shared/CodeBlock'
import { api } from '../../services/api'
import { Search, Code } from 'lucide-react'

interface EntityExplorerProps {
  repoId: string
}

export const EntityExplorer: React.FC<EntityExplorerProps> = ({ repoId }) => {
  const [symbolName, setSymbolName] = useState('')
  const [contextFile, setContextFile] = useState('')
  const [definition, setDefinition] = useState<any>(null)
  const [usages, setUsages] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSearch = async () => {
    if (!symbolName) return

    try {
      setLoading(true)
      setError('')

      const [defData, usageData] = await Promise.all([
        api.getSymbolDefinition(repoId, symbolName, contextFile || undefined),
        api.getSymbolUsages(repoId, symbolName)
      ])

      setDefinition(defData)
      setUsages(usageData.usages || [])
    } catch (err: any) {
      setError(err.message || 'Failed to search symbol')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-3">
        <input
          type="text"
          value={symbolName}
          onChange={(e) => setSymbolName(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
          placeholder="Symbol name (function, class, variable)..."
          className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
        <input
          type="text"
          value={contextFile}
          onChange={(e) => setContextFile(e.target.value)}
          placeholder="Context file (optional)"
          className="w-64 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
        <Button
          icon={<Search className="w-4 h-4" />}
          onClick={handleSearch}
          loading={loading}
          disabled={!symbolName}
        >
          Search
        </Button>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {definition && (
        <Card title="Definition">
          <div className="space-y-4">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <Code className="w-5 h-5 text-primary-600" />
                <div>
                  <h4 className="font-semibold text-gray-900">{definition.name}</h4>
                  <p className="text-sm text-gray-600">
                    {definition.entity_type} in {definition.file_path}
                  </p>
                </div>
              </div>
              <Badge>{definition.language}</Badge>
            </div>

            <CodeBlock 
              code={definition.code} 
              language={definition.language} 
            />

            <div className="text-sm text-gray-600">
              Lines {definition.start_line}-{definition.end_line}
            </div>
          </div>
        </Card>
      )}

      {usages.length > 0 && (
        <Card title={`Usages (${usages.length})`}>
          <div className="space-y-3">
            {usages.map((usage, idx) => (
              <div key={idx} className="p-3 bg-gray-50 rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-gray-900">
                    {usage.file_path}
                  </span>
                  <span className="text-xs text-gray-500">
                    Lines {usage.start_line}-{usage.end_line}
                  </span>
                </div>
                {usage.lines_with_symbol && usage.lines_with_symbol.length > 0 && (
                  <pre className="text-xs bg-white p-2 rounded border border-gray-200 overflow-x-auto">
                    {usage.lines_with_symbol.join('\n')}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}