import React, { useEffect, useState, useCallback } from 'react';
import { auth } from '../api';
import toast from 'react-hot-toast';
import { History, Search } from 'lucide-react';
import { formatAction, formatDetails } from '../utils/audit';
import LoadingSpinner from './ui/LoadingSpinner';
import Pagination from './ui/Pagination';

interface ActivityEntry {
  id: number;
  user_id: number | null;
  username: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  details: any;
  ip_address: string | null;
  created_at: string;
}

const MyActivity: React.FC = () => {
  const [logs, setLogs] = useState<ActivityEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [actionFilter, setActionFilter] = useState('');
  const limit = 30;

  const fetchLogs = useCallback(async (skip: number, action?: string) => {
    setLoading(true);
    try {
      const res = await auth.myActivity(skip, limit, action);
      setLogs(res.data.items);
      setTotal(res.data.total);
    } catch {
      toast.error('Ошибка загрузки истории');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchLogs(page * limit, actionFilter || undefined); }, [page, actionFilter, fetchLogs]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(0);
    fetchLogs(0, actionFilter || undefined);
  };

  const totalPages = Math.ceil(total / limit);

  if (loading && logs.length === 0) {
    return <LoadingSpinner fullHeight />;
  }

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-slate-800">Мои действия</h2>
        <p className="text-sm text-slate-500 mt-1">Журнал ваших операций в системе</p>
      </div>

      <form onSubmit={handleSearch} className="mb-4 flex gap-2">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input type="text" placeholder="Поиск по типу действия..." value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            className="w-full border border-slate-300 rounded-xl pl-10 pr-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" />
        </div>
        <button type="submit"
          className="px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 transition-colors">Поиск</button>
      </form>

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        {logs.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
              <History className="w-7 h-7 text-slate-400" />
            </div>
            <p className="text-slate-500">История действий пуста</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {logs.map((log) => {
              const fmt = formatAction(log.action);
              return (
                <div key={log.id} className="p-4 hover:bg-slate-50 transition-colors">
                  <div className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <History className="w-4 h-4 text-indigo-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`inline-flex px-2.5 py-0.5 text-xs font-medium rounded-lg ${fmt.color}`}>
                          {fmt.label}
                        </span>
                        <span className="text-xs text-slate-400">{log.entity_type}</span>
                        {log.entity_id && (
                          <span className="text-xs text-slate-400 font-mono">#{log.entity_id}</span>
                        )}
                      </div>
                      <p className="text-xs text-slate-500 mt-1">
                        {new Date(log.created_at).toLocaleString('ru-RU')}
                      </p>
                      {log.details && Object.keys(log.details).length > 0 && (
                        <p className="mt-1.5 text-xs text-slate-500">
                          {formatDetails(log.action, log.details)}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
    </div>
  );
};

export default MyActivity;
