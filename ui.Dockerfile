# ui.Dockerfile

# 1. Build Stage
FROM node:18-alpine AS builder
WORKDIR /app
COPY ui/package.json ui/package-lock.json* ./
RUN npm install
COPY ui/ .
RUN npm run build

# 2. Production Stage
FROM node:18-alpine
WORKDIR /app
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["npm", "start"]
