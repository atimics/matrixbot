# ui.Dockerfile - Next.js Standalone Build

# 1. Build Stage
FROM node:18-alpine AS builder
WORKDIR /app

# Copy dependency files
COPY ui-nextjs/package.json ui-nextjs/package-lock.json* ./

# Install dependencies
RUN npm ci --omit=dev

# Copy source code
COPY ui-nextjs/ .

# Build the application
RUN npm run build

# 2. Production Stage
FROM node:18-alpine AS runner
WORKDIR /app

# Set production environment
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Create system user for security
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copy standalone build output
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

# Set ownership
RUN chown -R nextjs:nodejs /app
USER nextjs

EXPOSE 3000

# Run the application
CMD ["node", "server.js"]
# Serve the contents of the 'dist' directory
CMD ["serve", "-s", "dist", "-l", "3000"]
