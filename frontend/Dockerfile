# Frontend Dockerfile
# Multi-stage: build with Node, serve with nginx.

# ------ builder ------
FROM node:24-alpine AS builder

WORKDIR /app

# Install dependencies first for better layer caching
COPY package.json package-lock.json* ./
RUN npm ci --frozen-lockfile

# Copy source and build
COPY . .
ARG VITE_AI_RUNTIME_READER_ENABLED=false
ENV VITE_AI_RUNTIME_READER_ENABLED=$VITE_AI_RUNTIME_READER_ENABLED
RUN npm run build
RUN printf '%s' "$VITE_AI_RUNTIME_READER_ENABLED" > /app/runtime-reader-enabled

# Output goes to /app/dist

# ------ runtime (nginx) ------
FROM nginxinc/nginx-unprivileged:1.25-alpine

# Remove default nginx config
# The unprivileged image runs as non-root by default.
USER root
RUN rm /etc/nginx/conf.d/default.conf
# Writes the /django-admin/ allowlist nginx.conf includes (IR-668). The image's
# entrypoint runs this directory when the command is nginx.
COPY docker-entrypoint.d/40-iris-django-admin.sh /docker-entrypoint.d/40-iris-django-admin.sh
RUN sed -i 's/\r$//' /docker-entrypoint.d/40-iris-django-admin.sh && chmod 755 /docker-entrypoint.d/40-iris-django-admin.sh
COPY docker-entrypoint.d/41-iris-runtime-reader.sh /docker-entrypoint.d/41-iris-runtime-reader.sh
RUN sed -i 's/\r$//' /docker-entrypoint.d/41-iris-runtime-reader.sh && chmod 755 /docker-entrypoint.d/41-iris-runtime-reader.sh
USER nginx
COPY --from=builder /app/runtime-reader-enabled /etc/nginx/iris/runtime-reader-enabled

# Our custom config -- handles SPA routing (all routes fall back to index.html)
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Browser security headers (IR-663). Outside conf.d, which nginx includes at
# http level on its own; nginx.conf includes this per location instead.
COPY security-headers.conf /etc/nginx/iris/security-headers.conf

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
