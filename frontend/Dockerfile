# Frontend Dockerfile
# Multi-stage: build with Node, serve with nginx.

# ------ builder ------
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first for better layer caching
COPY package.json package-lock.json* ./
RUN npm ci --frozen-lockfile

# Copy source and build
COPY . .
RUN npm run build

# Output goes to /app/dist

# ------ runtime (nginx) ------
FROM nginxinc/nginx-unprivileged:1.25-alpine

# Remove default nginx config
# The unprivileged image runs as non-root by default.
USER root
RUN rm /etc/nginx/conf.d/default.conf
USER nginx

# Our custom config -- handles SPA routing (all routes fall back to index.html)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
