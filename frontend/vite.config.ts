import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';

// ── Build-time env var guard ────────────────────────────────────────────────
// Throws during dev-server start / production build if required env vars are
// missing.  In non‑production environments a sensible default is allowed so
// the frontend can run without a full Keycloak setup for local dev.
// ────────────────────────────────────────────────────────────────────────────

const requiredBuildEnvVars = [
  'VITE_API_BASE_URL',
  'VITE_KEYCLOAK_URL',
  'VITE_KEYCLOAK_REALM',
] as const;

function buildEnvGuard(): Plugin {
  const plugin: Plugin = {
    name: 'build-env-guard',
    buildStart() {
      const environment = process.env.VITE_ENVIRONMENT || 'development';

      for (const varName of requiredBuildEnvVars) {
        const value = process.env[varName];

        if (!value) {
          if (environment === 'production') {
            throw new Error(
              `[build-env-guard] ${varName} is unset or empty. ` +
                `This variable is REQUIRED when VITE_ENVIRONMENT=production.`,
            );
          }
          // Non-production: warn but don't block
          this.warn(
            `[build-env-guard] ${varName} is unset. ` +
              `Falling back to proxy defaults. Set this in .env for local dev.`,
          );
        }
      }
    },
  };
  return plugin;
}

// ── Vite config ─────────────────────────────────────────────────────────────

export default defineConfig({
  plugins: [react(), buildEnvGuard()],

  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/auth': {
        target: process.env.VITE_KEYCLOAK_URL || 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },

  define: {
    // Expose to client-side for runtime import.meta.env checks
    __VITE_ENVIRONMENT__: JSON.stringify(process.env.VITE_ENVIRONMENT || 'development'),
  },
});
