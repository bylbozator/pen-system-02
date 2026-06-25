import React, { useEffect, useState, useCallback } from 'react';
import { admin } from '../api';
import { useAuth } from '../contexts/AuthContext';
import toast from 'react-hot-toast';
import { Search, User } from 'lucide-react';
import { formatAction, formatDetails } from '../utils/audit';
import LoadingSpinner from './ui/LoadingSpinner';
import Pagination from './ui/Pagination';

interface AuditEntry {
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

const AdminAudit: React.FC = () => {
  const [logs, setLogs] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [actionFilter, setActionFilter] = useState('');
  const [showMine, setShowMine] = useState(false);
  const limit = 50;
  const { user: currentUser } = useAuth();

  const fetchLogs = useCallback(async (skip: number) => {
    setLoading(true);
    try {
      const filters: any = {};
      if (actionFilter.trim()) filters.action = actionFilter.trim();
      if (showMine && currentUser) filters.user_id = currentUser.id;
      const res = await admin.audit(skip, limit, filters);
      setLogs(res.data.items);
      setTotal(res.data.total);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || '';
      toast.error(`Ошибка загрузки аудита${msg ? ': ' + msg : ''}`);
    } finally {
      setLoading(false);
    }
  }, [actionFilter, showMine, currentUser]);

  useEffect(() => { fetchLogs(page * limit); }, [page, fetchLogs]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(0);
    fetchLogs(0);
  };

  const totalPages = Math.ceil(total / limit);

  if (loading && logs.length === 0) {
    return <LoadingSpinner fullHeight />;
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Журнал аудита</h2>
          <p className="text-sm text-slate-500 mt-1">{showMine ? 'Ваши действия в системе' : 'Все действия пользователей'}</p>
        </div>
        <button onClick={() => { setShowMine(!showMine); setPage(0); }}
          className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors ${
            showMine ? 'bg-indigo-100 text-indigo-700' : 'bg-white border border-slate-300 text-slate-700 hover:bg-slate-50'
          }`}>
          <User className="w-4 h-4" />
          {showMine ? 'Мои действия' : 'Все действия'}
        </button>
      </div>

      <form onSubmit={handleSearch} className="mb-4 flex gap-2">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input type="text" placeholder="Фильтр по действию..." value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            className="w-full border border-slate-300 rounded-xl pl-10 pr-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" />
        </div>
        <button type="submit" className="px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 transition-colors">Поиск</button>
      </form>

      <div className="bg-white rounded-2xl border border-slate-200 overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              {['Дата', 'Пользователь', 'Действие', 'Тип', 'Детали', 'IP'].map(h => (
                <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {logs.map((log) => {
              const fmt = formatAction(log.action);
              return (
                <tr key={log.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-5 py-3.5 text-sm text-slate-600 whitespace-nowrap">{new Date(log.created_at).toLocaleString('ru-RU')}</td>
                  <td className="px-5 py-3.5 text-sm text-slate-700">{log.username || <span className="text-slate-400">#{log.user_id}</span>}</td>
                  <td className="px-5 py-3.5">
                    <span className={`inline-flex px-2.5 py-1 text-xs font-medium rounded-lg ${fmt.color}`}>{fmt.label}</span>
                  </td>
                  <td className="px-5 py-3.5 text-sm text-slate-500">{log.entity_type || '—'}</td>
                  <td className="px-5 py-3.5 text-sm text-slate-500 max-w-xs">
                    {log.details && Object.keys(log.details).length > 0
                      ? formatDetails(log.action, log.details)
                      : '—'}
                  </td>
                  <td className="px-5 py-3.5 text-sm text-slate-500 font-mono text-xs">{log.ip_address || '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
    </div>
  );
};

export default AdminAudit;
