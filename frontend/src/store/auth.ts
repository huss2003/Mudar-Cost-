import { create } from 'zustand';

export interface User {
  sub: string;
  email: string;
  name: string;
  roles: string[];
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
}

const DEMO_USER: User = {
  sub: 'demo',
  email: 'estimator@autocost.engine',
  name: 'Estimator',
  roles: ['estimator'],
};

export const useAuthStore = create<AuthState>(() => ({
  user: DEMO_USER,
  isAuthenticated: true,
}));
