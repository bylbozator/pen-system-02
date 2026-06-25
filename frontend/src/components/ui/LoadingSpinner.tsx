import React from 'react';

interface LoadingSpinnerProps {
  text?: string;
  fullHeight?: boolean;
}

const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ text = 'Загрузка...', fullHeight = false }) => (
  <div className={`flex items-center justify-center ${fullHeight ? 'h-64' : 'py-10'}`}>
    <div className="flex items-center gap-2 text-slate-500">
      <div className="w-5 h-5 border-2 border-slate-300 border-t-indigo-500 rounded-full animate-spin" />
      {text}
    </div>
  </div>
);

export default LoadingSpinner;
