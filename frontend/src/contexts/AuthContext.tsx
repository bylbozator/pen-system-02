import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { auth, User, getAccessToken, setCurrentUser } from '../api';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  refreshUser: () => Promise<void>;
  setUser: (user: User | null) => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  refreshUser: async () => {},
  setUser: () => {},
});

export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    try {
      const res = await auth.me();
      setUser(res.data);
      setCurrentUser(res.data);
    } catch {
      setUser(null);
      setCurrentUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const updateUser = useCallback((newUser: User | null) => {
    setUser(newUser);
    setCurrentUser(newUser);
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  return (
    <AuthContext.Provider value={{ user, loading, refreshUser, setUser: updateUser }}>
      {children}
    </AuthContext.Provider>
  );
};
