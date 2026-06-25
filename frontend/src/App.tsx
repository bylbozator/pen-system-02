// frontend/src/App.tsx
import { BrowserRouter, Routes, Route, Navigate, Link, useNavigate } from 'react-router-dom';
import { useEffect, lazy, Suspense } from 'react';
import { Toaster } from 'react-hot-toast';
import Login from './components/Login';
import DatasetList from './components/DatasetList';
import { useAuth } from './contexts/AuthContext';

const UniverList = lazy(() => import('./components/UniverList'));
import AdminUsers from './components/AdminUsers';
import AdminRoles from './components/AdminRoles';
import AdminDatasets from './components/AdminDatasets';
import AdminDashboard from './components/AdminDashboard';
import AdminAudit from './components/AdminAudit';
import UserDashboard from './components/UserDashboard';
import MyActivity from './components/MyActivity';
import ReportDashboard from './components/ReportDashboard';
import ErrorBoundary from './components/ErrorBoundary';
import Layout from './components/Layout';
import { AuthProvider } from './contexts/AuthContext';
import { auth, setOnUnauthorized, setAccessToken } from './api';

function PrivateRoute({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="flex justify-center items-center h-screen">Загрузка...</div>;
  }

  return user ? children : <Navigate to="/login" />;
}

function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center h-screen">
      <h1 className="text-6xl font-bold text-gray-300">404</h1>
      <p className="text-xl text-gray-500 mt-4">Страница не найдена</p>
      <Link to="/" className="mt-6 text-blue-500 hover:underline">Вернуться на главную</Link>
    </div>
  );
}

function AppRoutes() {
  const navigate = useNavigate();
  useEffect(() => {
    setOnUnauthorized(() => { setAccessToken(null); navigate('/login', { replace: true }); });
  }, [navigate]);
  return (
    <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <PrivateRoute>
                <Layout />
              </PrivateRoute>
            }
          >
            <Route index element={<Navigate to="/datasets" replace />} />
            <Route path="my" element={<UserDashboard />} />
            <Route path="datasets" element={<DatasetList />} />
            <Route path="datasets/:id" element={<Suspense fallback={<div className="flex justify-center items-center h-[80vh]">Загрузка редактора...</div>}><UniverList /></Suspense>} />
            <Route path="my-activity" element={<MyActivity />} />
            <Route path="reports" element={<ReportDashboard />} />
            <Route path="admin" element={<AdminDashboard />} />
            <Route path="admin/users" element={<AdminUsers />} />
            <Route path="admin/roles" element={<AdminRoles />} />
            <Route path="admin/datasets" element={<AdminDatasets />} />
            <Route path="admin/audit" element={<AdminAudit />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
  );
}

function App() {
  return (
    <>
      <Toaster position="top-right" />
      <ErrorBoundary>
      <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
      </AuthProvider>
      </ErrorBoundary>
    </>
  );
}

export default App;