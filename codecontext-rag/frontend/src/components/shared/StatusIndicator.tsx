import React from 'react'
import { CheckCircle, XCircle, Clock, AlertCircle } from 'lucide-react'

interface StatusIndicatorProps {
  status: 'success' | 'error' | 'pending' | 'warning'
  label?: string
  size?: 'sm' | 'md' | 'lg'
}

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({
  status,
  label,
  size = 'md'
}) => {
  const icons = {
    success: CheckCircle,
    error: XCircle,
    pending: Clock,
    warning: AlertCircle
  }

  const colors = {
    success: 'text-green-500',
    error: 'text-red-500',
    pending: 'text-blue-500',
    warning: 'text-yellow-500'
  }

  const sizes = {
    sm: 'w-4 h-4',
    md: 'w-5 h-5',
    lg: 'w-6 h-6'
  }

  const Icon = icons[status]

  return (
    <div className="flex items-center gap-2">
      <Icon className={`${sizes[size]} ${colors[status]}`} />
      {label && <span className="text-sm text-gray-700">{label}</span>}
    </div>
  )
}