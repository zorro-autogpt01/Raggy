// codecontext-rag/frontend/src/components/layout/Sidebar.tsx
import type React from 'react'
import { NavLink } from 'react-router-dom'
import {
  Code2,
  Database,
  Search,
  TrendingUp,
  Network,
  Map,
  FileCode,
  MessageSquare,
  GitPullRequest,
  Sparkles,
  LineChart,
  Beaker,
  Activity,
  PlayCircle,
  Brain,
  Target,
  CheckCircle
} from 'lucide-react'
import clsx from 'clsx'

const navItems = [
  { path: '/', icon: Activity, label: 'Dashboard' },
  { path: '/repositories', icon: Database, label: 'Repositories' },
  { 
    separator: true,
    label: 'Analysis & Search'
  },
  { path: '/search', icon: Search, label: 'Code Search' },
  { path: '/recommendations', icon: TrendingUp, label: 'Recommendations' },
  { path: '/dependencies', icon: Network, label: 'Dependencies' },
  { path: '/graphs', icon: Map, label: 'Graphs' },
  { path: '/context', icon: FileCode, label: 'Context' },
  { path: '/impact', icon: Activity, label: 'Impact Analysis' },
  {
    separator: true,
    label: 'Code Generation'
  },
  { path: '/prompts', icon: MessageSquare, label: 'Prompts' },
  { path: '/patches', icon: GitPullRequest, label: 'Patches' },
  { path: '/tests', icon: Beaker, label: 'Tests' },
  {
    separator: true,
    label: 'Product & AI'
  },
  { path: '/features', icon: Sparkles, label: 'Features' },
  { path: '/product-analysis', icon: LineChart, label: 'Product Analysis' },
  {
    separator: true,
    label: 'Automation'
  },
  { path: '/task-analysis', icon: Brain, label: 'Task Analysis' },
  { path: '/orchestration', icon: PlayCircle, label: 'Orchestration' },
  { path: '/runner-validation', icon: CheckCircle, label: 'Runner Validation' },
  { path: '/agent-feedback', icon: Target, label: 'AI Learning' },
]

export const Sidebar: React.FC = () => {
  return (
    <aside className="w-64 bg-white border-r border-gray-200 flex flex-col">
      <div className="p-6 border-b border-gray-200">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-primary-500 to-primary-700 rounded-lg flex items-center justify-center">
            <Code2 className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-gray-900">CodeContext</h1>
            <p className="text-xs text-gray-500">Intelligent RAG</p>
          </div>
        </div>
      </div>
      
      <nav className="flex-1 overflow-y-auto p-4">
        <div className="space-y-1">
          {navItems.map((item, idx) => {
            if ('separator' in item && item.separator) {
              return (
                <div key={idx} className="pt-4 pb-2">
                  <p className="px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    {item.label}
                  </p>
                </div>
              )
            }
            
            const navItem = item as { path: string; icon: any; label: string }
            return (
              <NavLink
                key={navItem.path}
                to={navItem.path}
                className={({ isActive }) =>
                  clsx(
                    'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-primary-50 text-primary-700'
                      : 'text-gray-700 hover:bg-gray-100'
                  )
                }
              >
                <navItem.icon className="w-5 h-5" />
                {navItem.label}
              </NavLink>
            )
          })}
        </div>
      </nav>
      
      <div className="p-4 border-t border-gray-200">
        <div className="text-xs text-gray-500">
          <p>Version 2.0.0</p>
          <p className="mt-1">API Status: <span className="text-green-600">●</span> Online</p>
        </div>
      </div>
    </aside>
  )
}