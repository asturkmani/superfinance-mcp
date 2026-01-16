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

# Copy Python packages and CLI executables from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY server.py ./
COPY README.md ./
COPY pyproject.toml ./

# Expose port for SSE
EXPOSE 8080

# Run server with MCP CLI using HTTP transport
CMD ["mcp", "run", "server.py:yfinance_server", "--transport", "http", "--host", "0.0.0.0", "--port", "8080"]
