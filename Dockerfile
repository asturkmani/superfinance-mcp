# Multi-stage build for Yahoo Finance MCP server
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv pip install --system -e .

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install flyctl for MCP wrapper
RUN apt-get update && apt-get install -y curl && \
    curl -L https://fly.io/install.sh | sh && \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.fly/bin:${PATH}"

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy application code
COPY server.py ./
COPY README.md ./
COPY pyproject.toml ./

# Expose port for SSE
EXPOSE 8080

# Use flyctl mcp wrap (simple, works, no auth = unlimited clients)
CMD ["flyctl", "mcp", "wrap", "--", "/usr/local/bin/python3", "server.py"]
