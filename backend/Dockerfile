FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Install dependencies before copying source (better layer caching)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application source
COPY . .

# Add venv binaries to PATH so uvicorn/celery are available without "uv run"
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
