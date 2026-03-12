# Build stage
FROM oven/bun:latest AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./
COPY bun.lockb ./

# Install dependencies
RUN bun install

# Copy source code
COPY /src ./src
COPY nuxt.config.ts tsconfig.json ./

# Build the Nuxt application
RUN bun run build

# Production stage
FROM oven/bun:latest

WORKDIR /app

# Copy only necessary files from builder
COPY --from=builder /app/.nuxt ./.nuxt
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/bun.lockb ./

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD bun run -e "require('http').get('http://localhost:3000', (r) => {if (r.statusCode !== 200) throw new Error(r.statusCode)})"

# Start the application
CMD ["bun", "run", ".nuxt/dist/server/server.mjs"]
