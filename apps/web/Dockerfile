# syntax=docker/dockerfile:1.7
FROM node:22-bookworm-slim AS build
WORKDIR /app
RUN --mount=type=secret,id=proxy_ca,required=false \
    if [ -s /run/secrets/proxy_ca ]; then cp /run/secrets/proxy_ca /usr/local/share/ca-certificates/session-proxy.crt; update-ca-certificates; fi
ENV ELECTRON_SKIP_BINARY_DOWNLOAD=1
COPY apps/web ./
RUN --mount=type=cache,target=/root/.npm \
    if [ -s /usr/local/share/ca-certificates/session-proxy.crt ]; then export NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/session-proxy.crt; fi; \
    npm ci --ignore-scripts
RUN npx quasar prepare && npm run build:pwa
FROM nginx:1.28-alpine
COPY infra/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/pwa /usr/share/nginx/html
EXPOSE 80
