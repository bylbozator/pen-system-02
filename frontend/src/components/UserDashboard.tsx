import React, { useEffect, useState } from 'react';
import { datasets } from '../api';
import { useAuth } from '../contexts/AuthContext';
import toast from 'react-hot-toast';
import LoadingSpinner from './ui/LoadingSpinner';
import {
  Table2,
  Rows3,
  CalendarClock,
  User,
  Activity,
  Clock,
} from 'lucide-react';

interface UserStats {
  totalDatasets: number;
  archivedDatasets: number;
}

const UserDashboard: React.FC = () => {
  const [stats, setStats] = useState<UserStats | null>(null);
  const [loading, setLoading] = useState(true);
  const { user } = useAuth();

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const [activeRes, archivedRes] = await Promise.all([
          datasets.list(0, 500, false),
          datasets.list(0, 500, true),
        ]);
        const active = activeRes.data.items || [];
        const archived = archivedRes.data.items || [];
        setStats({
          totalDatasets: active.length + archived.length,
          archivedDatasets: archived.length,
        });
      } catch {
        toast.error('Ошибка загрузки статистики');
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  if (loading) return <LoadingSpinner fullHeight />;

  const cards = [
    {
      label: 'Всего таблиц',
      value: stats?.totalDatasets ?? 0,
      icon: Table2,
      color: 'text-indigo-600',
      bg: 'bg-indigo-100',
    },
    {
      label: 'Активных таблиц',
      value: (stats?.totalDatasets ?? 0) - (stats?.archivedDatasets ?? 0),
      icon: Activity,
      color: 'text-emerald-600',
      bg: 'bg-emerald-100',
    },
    {
      label: 'Таблиц в архиве',
      value: stats?.archivedDatasets ?? 0,
      icon: Rows3,
      color: 'text-amber-600',
      bg: 'bg-amber-100',
    },
  ];

  return (
    <div>
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-slate-800">Моя панель</h2>
        <p className="text-slate-500 mt-1">Ваша личная статистика в системе</p>
      </div>

      {/* User info card */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 mb-6">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-indigo-100 flex items-center justify-center">
            <User className="w-7 h-7 text-indigo-600" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-slate-800">{user?.username || 'Пользователь'}</h3>
            <p className="text-sm text-slate-500">{user?.email || '—'}</p>
            <div className="flex items-center gap-4 mt-1.5 text-xs text-slate-400">
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                Роль: {user?.role_name || '—'}
              </span>
              {user?.last_login && (
                <span className="flex items-center gap-1">
                  <CalendarClock className="w-3 h-3" />
                  Последний вход: {new Date(user.last_login).toLocaleString('ru-RU')}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
        {cards.map((card) => (
          <div key={card.label} className="bg-white rounded-2xl border border-slate-200 p-6 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-4">
              <div className={`w-12 h-12 rounded-xl ${card.bg} flex items-center justify-center`}>
                <card.icon className={`w-6 h-6 ${card.color}`} />
              </div>
            </div>
            <div className="text-3xl font-bold text-slate-800">{card.value}</div>
            <div className="text-sm text-slate-500 mt-1">{card.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default UserDashboard;
