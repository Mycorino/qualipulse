# Build stage
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci

# .dockerignore excludes node_modules from the build context so nothing
# committed at frontend/node_modules (it has happened: a symlink meant only
# for local worktree previews was tracked by git once) can clobber the
# node_modules npm ci just installed and silently break the build.
COPY . .
RUN npm run build

# Production stage — nginx with runtime env injection
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# Cloud Run uses port 8080
EXPOSE 8080

# Default backend URL (override via env var in Cloud Run)
ENV BACKEND_URL=http://localhost:8000
ENV BACKEND_HOST=localhost

# nginx:alpine auto-runs envsubst on /etc/nginx/templates/*.template → /etc/nginx/conf.d/
CMD ["nginx", "-g", "daemon off;"]
