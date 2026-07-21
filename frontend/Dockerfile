# =============================================================================
# Auto Cost Engine — Frontend Production Dockerfile
# =============================================================================
# Multi-stage build: Vite build → Caddy static file server
# =============================================================================

# Stage 1 — Build the SPA
# -----------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies (cached via layer)
COPY package.json package-lock.json ./
RUN npm ci

# Copy source and build
COPY . .
RUN npm run build

# Stage 2 — Serve static files with Caddy
# -----------------------------------------------------------------------------
FROM caddy:2-alpine

# Copy built assets from builder
COPY --from=builder /app/dist /srv

# Expose the port the main Caddy reverse proxy expects
EXPOSE 5173

# Use Caddy's built-in file server — no separate Caddyfile needed
CMD ["caddy", "file-server", "--listen", ":5173", "--root", "/srv"]
