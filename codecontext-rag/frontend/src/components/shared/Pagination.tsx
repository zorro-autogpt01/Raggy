// codecontext-rag/frontend/src/components/shared/Pagination.tsx
import React from 'react'
import { Button } from './Button'
import { ChevronLeft, ChevronRight } from 'lucide-react'

interface PaginationProps {
  currentPage: number
  totalPages: number
  onPageChange: (page: number) => void
}

export const Pagination: React.FC<PaginationProps> = ({
  currentPage,
  totalPages,
  onPageChange
}) => {
  const pages = []
  const maxVisible = 5

  let start = Math.max(1, currentPage - Math.floor(maxVisible / 2))
  let end = Math.min(totalPages, start + maxVisible - 1)

  if (end - start + 1 < maxVisible) {
    start = Math.max(1, end - maxVisible + 1)
  }

  for (let i = start; i <= end; i++) {
    pages.push(i)
  }

  return (
    <div className="flex items-center justify-center gap-2">
      <Button
        size="sm"
        variant="ghost"
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
        icon={<ChevronLeft className="w-4 h-4" />}
      >
        Previous
      </Button>

      {start > 1 && (
        <>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onPageChange(1)}
          >
            1
          </Button>
          {start > 2 && <span className="text-gray-400">...</span>}
        </>
      )}

      {pages.map(page => (
        <Button
          key={page}
          size="sm"
          variant={page === currentPage ? 'primary' : 'ghost'}
          onClick={() => onPageChange(page)}
        >
          {page}
        </Button>
      ))}

      {end < totalPages && (
        <>
          {end < totalPages - 1 && <span className="text-gray-400">...</span>}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onPageChange(totalPages)}
          >
            {totalPages}
          </Button>
        </>
      )}

      <Button
        size="sm"
        variant="ghost"
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
        icon={<ChevronRight className="w-4 h-4" />}
      >
        Next
      </Button>
    </div>
  )
}