# ui.Dockerfile

# 1. Build Stage
FROM node:18-alpine AS builder
WORKDIR /app
COPY ui/package.json ./
# If package-lock.json exists, it will be copied. If not, npm install will create one.
COPY ui/package-lock.json* ./
RUN npm install
COPY ui/ .
RUN npm run build

# 2. Production Stage
FROM node:18-alpine
WORKDIR /app

# Install serve to run the built app
RUN npm install -g serve

# Copy built assets from builder stage
# Vite typically builds to a 'dist' directory
COPY --from=builder /app/dist ./dist 

# Copy package.json and node_modules if needed for serve or other runtime dependencies
# For a simple Vite static build, these might not be strictly necessary if serve is global
# and there are no runtime server-side dependencies from package.json.
# However, it's safer to include them if 'serve' or other tools might rely on local packages.
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules

EXPOSE 3000
# Serve the contents of the 'dist' directory
CMD ["serve", "-s", "dist", "-l", "3000"]
