import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

const Pagination: React.FC<PaginationProps> = ({ page, totalPages, onPageChange }) => {
  if (totalPages <= 1) return null;

  return (
    <div className="flex items-center justify-between mt-4 bg-white rounded-xl border border-slate-200 p-3">
      <button
        disabled={page === 0}
        onClick={() => onPageChange(page - 1)}
        className="inline-flex items-center gap-1 px-4 py-2 border border-slate-300 rounded-lg text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        <ChevronLeft className="w-4 h-4" /> Назад
      </button>
      <span className="text-sm text-slate-500">
        {totalPages > 0 ? `Стр. ${page + 1} из ${totalPages}` : ''}
      </span>
      <button
        disabled={page >= totalPages - 1}
        onClick={() => onPageChange(page + 1)}
        className="inline-flex items-center gap-1 px-4 py-2 border border-slate-300 rounded-lg text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        Вперёд <ChevronRight className="w-4 h-4" />
      </button>
    </div>
  );
};

export default Pagination;
