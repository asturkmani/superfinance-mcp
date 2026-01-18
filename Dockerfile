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

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy application code
COPY server.py ./
COPY cache.py ./
COPY refresh.py ./
COPY helpers/ ./helpers/
COPY tools/ ./tools/
COPY services/ ./services/
COPY api/ ./api/
COPY README.md ./
COPY pyproject.toml ./

# Expose port
EXPOSE 8080

# Run server directly with Python (fastmcp handles HTTP transport)
CMD ["python", "server.py"]
