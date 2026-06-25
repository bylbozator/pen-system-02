import React, { useEffect, useState } from 'react';
import { admin } from '../api';
import toast from 'react-hot-toast';
import LoadingSpinner from './ui/LoadingSpinner';
import {
  Users,
  UserCheck,
  Table2,
  Archive,
  Rows3,
  MessageSquareText,
} from 'lucide-react';

interface Stats {
  total_users: number;
  active_users: number;
  total_datasets: number;
  archived_datasets: number;
  total_rows: number;
  total_comments: number;
}

const cards = [
  { label: 'Пользователей всего', valueKey: 'total_users' as const, icon: Users, color: 'bg-blue-500' },
  { label: 'Активных пользователей', valueKey: 'active_users' as const, icon: UserCheck, color: 'bg-emerald-500' },
  { label: 'Таблиц всего', valueKey: 'total_datasets' as const, icon: Table2, color: 'bg-violet-500' },
  { label: 'Таблиц в архиве', valueKey: 'archived_datasets' as const, icon: Archive, color: 'bg-amber-500' },
  { label: 'Строк в таблицах', valueKey: 'total_rows' as const, icon: Rows3, color: 'bg-indigo-500' },
  { label: 'Комментариев', valueKey: 'total_comments' as const, icon: MessageSquareText, color: 'bg-rose-500' },
];

const AdminDashboard: React.FC = () => {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    admin.stats()
      .then((res) => setStats(res.data))
      .catch(() => toast.error('Ошибка загрузки статистики'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSpinner fullHeight />;
  if (!stats) return <div className="text-center py-10 text-slate-500">Нет данных</div>;

  return (
    <div>
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-slate-800">Панель управления</h2>
        <p className="text-slate-500 mt-1">Общая статистика системы</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {cards.map((card) => (
          <div
            key={card.label}
            className="bg-white rounded-2xl border border-slate-200 p-6 hover:shadow-md transition-shadow"
          >
            <div className="flex items-center justify-between mb-4">
              <div className={`w-12 h-12 rounded-xl ${card.color} bg-opacity-10 flex items-center justify-center`}>
                <card.icon className={`w-6 h-6 ${card.color.replace('bg-', 'text-')}`} />
              </div>
            </div>
            <div className="text-3xl font-bold text-slate-800">
              {stats[card.valueKey].toLocaleString()}
            </div>
            <div className="text-sm text-slate-500 mt-1">{card.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AdminDashboard;
