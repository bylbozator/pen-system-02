import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { auth, setAccessToken } from '../api';
import { useAuth } from '../contexts/AuthContext';
import toast from 'react-hot-toast';
import { FileSpreadsheet, LogIn } from 'lucide-react';

const Login: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const { setUser } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await auth.login(username, password);
      if (res.data?.user) {
        setUser(res.data.user);
        if (res.data.access_token) {
          setAccessToken(res.data.access_token);
        }
        toast.success('Вход выполнен');
        navigate('/');
      } else {
        toast.error('Ошибка: не получены данные пользователя');
      }
    } catch {
      toast.error('Неверный логин или пароль');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* Left decorative panel */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-indigo-900 via-indigo-800 to-slate-900 items-center justify-center p-12">
        <div className="text-center">
          <div className="w-20 h-20 rounded-2xl bg-white/10 flex items-center justify-center mx-auto mb-8 backdrop-blur-sm">
            <FileSpreadsheet className="w-10 h-10 text-indigo-300" />
          </div>
          <h1 className="text-4xl font-bold text-white mb-4">ПЭН Система</h1>
          <p className="text-indigo-200 text-lg max-w-md">
             Учёт и контроль поставок МТР для производственно-эксплуатационных нужд с электронными таблицами, разграничением доступа и аудитом
          </p>
        </div>
      </div>

      {/* Right form panel */}
      <div className="flex-1 flex items-center justify-center p-8 bg-slate-50">
        <div className="w-full max-w-sm">
          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-3 justify-center mb-10">
            <div className="w-10 h-10 rounded-lg bg-indigo-600 flex items-center justify-center">
              <FileSpreadsheet className="w-6 h-6 text-white" />
            </div>
            <h1 className="text-2xl font-bold text-slate-800">ПЭН Система</h1>
          </div>

          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8">
            <h2 className="text-xl font-semibold text-slate-800 mb-1">Добро пожаловать</h2>
            <p className="text-sm text-slate-500 mb-8">Войдите, чтобы продолжить</p>

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">Логин</label>
                <input
                  type="text"
                  placeholder="Введите логин"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-shadow"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">Пароль</label>
                <input
                  type="password"
                  placeholder="Введите пароль"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-shadow"
                  required
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 bg-indigo-600 text-white py-2.5 rounded-xl hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
              >
                <LogIn className="w-4 h-4" />
                {loading ? 'Вход...' : 'Войти'}
              </button>
            </form>
          </div>

          <p className="text-center text-xs text-slate-400 mt-8">Версия 3.0</p>
        </div>
      </div>
    </div>
  );
};

export default Login;
