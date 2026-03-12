# Build stage
FROM oven/bun:latest AS builder

WORKDIR /app

# Copy package files
COPY src/package.json ./package.json
COPY src/bun.lock ./bun.lock

# Install dependencies
RUN bun install --frozen-lockfile

# Copy source code
COPY src/ ./

# Ensure the image build does not reuse local Nuxt artifacts.
RUN rm -rf .nuxt .output

# Build the Nuxt application
RUN bun run build

# Production stage
FROM oven/bun:latest

WORKDIR /app

# Runtime configuration
ENV NITRO_HOST=0.0.0.0
ENV NITRO_PORT=3000

# Copy only necessary files from builder
COPY --from=builder /app/.output ./.output
COPY --from=builder /app/node_modules ./node_modules

# Expose port
EXPOSE 3000

# Start the application
CMD ["bun", ".output/server/index.mjs"]
