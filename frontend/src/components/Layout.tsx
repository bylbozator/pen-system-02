import React, { useState } from 'react';
import { Link, Outlet, useNavigate, useLocation } from 'react-router-dom';
import toast from 'react-hot-toast';
import { auth, setAccessToken } from '../api';
import { useAuth } from '../contexts/AuthContext';
import Modal from './ui/Modal';
import {
  LayoutDashboard,
  Table2,
  ShieldCheck,
  Users,
  Database,
  FileSpreadsheet,
  LogOut,
  ChevronRight,
  Settings,
  BarChart3,
  History,
} from 'lucide-react';

const navItems = [
  { to: '/my', label: 'Моя панель', icon: LayoutDashboard },
  { to: '/reports', label: 'Отчёты', icon: BarChart3 },
  { to: '/datasets', label: 'Таблицы', icon: Table2 },
  { to: '/my-activity', label: 'Мои действия', icon: History },
];

const adminItems = [
  { to: '/admin', label: 'Панель управления', icon: LayoutDashboard },
  { to: '/admin/users', label: 'Пользователи', icon: Users },
  { to: '/admin/roles', label: 'Роли', icon: ShieldCheck },
  { to: '/admin/datasets', label: 'Управление таблицами', icon: Database },
  { to: '/admin/audit', label: 'Журнал аудита', icon: BarChart3 },
];

const Layout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const isAdmin = user?.role_name === 'администратор';
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      toast.error('Пароли не совпадают');
      return;
    }
    try {
      await auth.changePassword(oldPassword, newPassword);
      toast.success('Пароль изменён');
      setShowChangePassword(false);
      setOldPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Ошибка смены пароля');
    }
  };

  const handleLogout = async () => {
    try {
      await auth.logout();
    } catch {
      // ignore
    }
    setAccessToken(null);
    window.location.href = '/login';
  };

  const isActive = (path: string) => {
    if (path === '/admin') return location.pathname === '/admin';
    return location.pathname.startsWith(path);
  };

  const linkClass = (path: string) =>
    `group flex items-center gap-3 px-4 py-2.5 mx-2 rounded-lg text-sm font-medium transition-all duration-150 ${
      isActive(path)
        ? 'bg-indigo-500/10 text-indigo-300 shadow-sm'
        : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
    }`;

  return (
    <div className="flex h-screen bg-slate-50">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-900 flex flex-col flex-shrink-0">
        {/* Logo */}
        <div className="h-16 flex items-center gap-3 px-6 border-b border-slate-800">
          <div className="w-8 h-8 rounded-lg bg-indigo-500 flex items-center justify-center">
            <FileSpreadsheet className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-base font-bold text-white tracking-tight">ПЭН Система</h1>
            <p className="text-[10px] text-slate-500 leading-tight">Учёт МТР для ПЭН</p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-4 overflow-y-auto">
          {/* Main */}
          <div className="px-4 mb-2">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">
              Основное
            </p>
          </div>
          {navItems.map((item) => (
            <Link key={item.to} to={item.to} className={linkClass(item.to)}>
              <item.icon className="w-5 h-5 flex-shrink-0" />
              <span>{item.label}</span>
              {isActive(item.to) && (
                <ChevronRight className="w-4 h-4 ml-auto text-indigo-400" />
              )}
            </Link>
          ))}

          {/* Admin */}
          {isAdmin && (
            <>
              <div className="px-4 mt-6 mb-2">
                <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">
                  Администрирование
                </p>
              </div>
              {adminItems.map((item) => (
                <Link key={item.to} to={item.to} className={linkClass(item.to)}>
                  <item.icon className="w-5 h-5 flex-shrink-0" />
                  <span>{item.label}</span>
                  {isActive(item.to) && (
                    <ChevronRight className="w-4 h-4 ml-auto text-indigo-400" />
                  )}
                </Link>
              ))}
            </>
          )}
        </nav>

        {/* User section */}
        <div className="border-t border-slate-800 p-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-indigo-500/20 flex items-center justify-center text-indigo-300 text-sm font-semibold">
              {user?.username?.charAt(0).toUpperCase() || '?'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-slate-200 truncate">
                {user?.username || 'Пользователь'}
              </p>
              <p className="text-[11px] text-slate-500 truncate">
                {user?.role_name || '—'}
              </p>
            </div>
          </div>
          <button onClick={() => setShowChangePassword(true)}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm text-slate-400 hover:text-indigo-400 hover:bg-indigo-500/10 rounded-lg transition-colors">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" /></svg>
            Сменить пароль
          </button>
          <button
            onClick={handleLogout}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
          >
            <LogOut className="w-4 h-4" />
            Выйти
          </button>
        </div>
      </aside>

      {/* Main area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-6 flex-shrink-0">
          <div className="flex items-center gap-3">
            <Settings className="w-5 h-5 text-slate-400" />
            <h2 className="text-lg font-semibold text-slate-800">
              {[...navItems, ...adminItems].find((i) => isActive(i.to))?.label || 'ПЭН Система'}
            </h2>
          </div>
          <p className="text-sm text-slate-500">
            Привет, <span className="font-medium text-slate-700">{user?.username || 'пользователь'}</span>
          </p>
        </header>
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
      <Modal isOpen={showChangePassword} onClose={() => setShowChangePassword(false)}
        title="Смена пароля" subtitle="Введите текущий и новый пароль"
        icon={<svg className="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" /></svg>}
        width="max-w-md"
        footer={
          <>
            <button onClick={() => setShowChangePassword(false)}
              className="px-5 py-2.5 border border-slate-300 rounded-xl text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors">Отмена</button>
            <button onClick={handleChangePassword}
              className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 transition-colors">Сменить</button>
          </>
        }>
        <form onSubmit={handleChangePassword} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">Текущий пароль</label>
            <input type="password" value={oldPassword} onChange={e => setOldPassword(e.target.value)}
              className="w-full border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" required />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">Новый пароль</label>
            <input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)}
              className="w-full border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" required />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">Подтвердите новый пароль</label>
            <input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}
              className="w-full border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" required />
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default Layout;
