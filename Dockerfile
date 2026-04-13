# Multi-stage build for SuperFinance MCP server
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Copy application code (needed for -e install)
COPY server.py users.py ./
COPY tools/ ./tools/

# Install dependencies using the lockfile
RUN uv sync --frozen --no-dev

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY server.py users.py ./
COPY tools/ ./tools/
COPY pyproject.toml ./

# Use the venv
ENV PATH="/app/.venv/bin:$PATH"

# Expose port
EXPOSE 8080

# Run server
CMD ["python", "server.py"]
