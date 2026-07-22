import { create } from 'zustand';

interface User {
  sub: string;
  email: string;
  name: string;
  roles: string[];
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  checkAuth: () => Promise<void>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>(() => ({
  user: { sub: 'anonymous', email: 'user@example.com', name: 'Demo User', roles: ['admin'] },
  isAuthenticated: true,
  isLoading: false,
  checkAuth: async () => { /* no-op */ },
  logout: () => { /* no-op */ },
}));
