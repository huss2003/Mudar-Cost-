import { create } from 'zustand';
import { persist } from 'zustand/middleware';

// ── Build-time env vars (validated at build by vite.config.ts) ──────────────
// In production these MUST be set.  In dev the build‑env‑guard plugin warns
// but allows proxy‑based fallback.
const VITE_ENVIRONMENT = import.meta.env.VITE_ENVIRONMENT || 'development';
const KEYCLOAK_URL =
  import.meta.env.VITE_KEYCLOAK_URL || (VITE_ENVIRONMENT === 'production' ? '' : 'http://localhost:8080');
const KEYCLOAK_REALM =
  import.meta.env.VITE_KEYCLOAK_REALM || (VITE_ENVIRONMENT === 'production' ? '' : 'jasfo');
const KEYCLOAK_CLIENT_ID =
  import.meta.env.VITE_KEYCLOAK_CLIENT_ID || (VITE_ENVIRONMENT === 'production' ? '' : 'estimation-web');

// ── Runtime guard ───────────────────────────────────────────────────────────
// If we're in production and these are still empty, the app will be broken —
// fail fast rather than silently proxying to wrong endpoints.
if (VITE_ENVIRONMENT === 'production') {
  if (!KEYCLOAK_URL) throw new Error('VITE_KEYCLOAK_URL is required in production');
  if (!KEYCLOAK_REALM) throw new Error('VITE_KEYCLOAK_REALM is required in production');
  if (!KEYCLOAK_CLIENT_ID) throw new Error('VITE_KEYCLOAK_CLIENT_ID is required in production');
}

// ── Types ───────────────────────────────────────────────────────────────────

export interface AuthUser {
  sub: string;
  email: string;
  name: string;
  roles: string[];
}

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: AuthUser | null;
  isAuthenticated: boolean;
  isInitialized: boolean;

  // Computed-like
  loginUrl: string;

  // Actions
  setInitialized: () => void;
  loginWithKeycloak: (code: string, redirectUri: string) => Promise<void>;
  refreshAccessToken: () => Promise<void>;
  login: (token: string, refreshToken: string, user: AuthUser) => void;
  logout: () => void;
  setTokens: (token: string, refreshToken: string) => void;
}

function buildLoginUrl(): string {
  const redirectUri =
    import.meta.env.VITE_KEYCLOAK_REDIRECT_URI || window.location.origin + '/login';
  const params = new URLSearchParams({
    client_id: KEYCLOAK_CLIENT_ID,
    redirect_uri: redirectUri,
    response_type: 'code',
    scope: 'openid email profile',
  });
  return `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/auth?${params.toString()}`;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
      isInitialized: false,
      loginUrl: buildLoginUrl(),

      setInitialized: () => set({ isInitialized: true }),

      loginWithKeycloak: async (code: string, redirectUri: string) => {
        const response = await fetch('/api/v1/auth/token-exchange', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code, redirect_uri: redirectUri }),
        });

        if (!response.ok) {
          const errorData = await response.text();
          throw new Error(`Token exchange failed: ${errorData}`);
        }

        const data = await response.json();
        const { access_token, refresh_token } = data;

        // Decode JWT to get user info
        const payload = JSON.parse(atob(access_token.split('.')[1]));
        const realmAccess = payload.realm_access || {};
        const user: AuthUser = {
          sub: payload.sub || '',
          email: payload.email || '',
          name: payload.name || payload.preferred_username || payload.email || '',
          roles: realmAccess.roles || [],
        };

        set({
          token: access_token,
          refreshToken: refresh_token,
          user,
          isAuthenticated: true,
        });
      },

      refreshAccessToken: async () => {
        const { refreshToken: currentRefresh } = get();
        if (!currentRefresh) {
          throw new Error('No refresh token available');
        }

        const response = await fetch('/api/v1/auth/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: currentRefresh }),
        });

        if (!response.ok) {
          // Refresh failed — force logout
          get().logout();
          throw new Error('Token refresh failed');
        }

        const data = await response.json();
        set({
          token: data.access_token,
          refreshToken: data.refresh_token || currentRefresh,
        });
      },

      login: (token, refreshToken, user) =>
        set({ token, refreshToken, user, isAuthenticated: true }),

      logout: () =>
        set({
          token: null,
          refreshToken: null,
          user: null,
          isAuthenticated: false,
        }),

      setTokens: (token, refreshToken) =>
        set({ token, refreshToken }),
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        token: state.token,
        refreshToken: state.refreshToken,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    },
  ),
);
