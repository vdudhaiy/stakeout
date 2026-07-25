# Stakeout frontend — Vite build served by nginx.
# Build context is the repo root.
FROM node:20-alpine AS build

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# VITE_API_URL stays empty: nginx proxies API paths to the backend container,
# mirroring the Vite dev proxy, so the SPA and API share one origin (no CORS).
ENV VITE_API_URL=
RUN npm run build

FROM nginx:1.27-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
