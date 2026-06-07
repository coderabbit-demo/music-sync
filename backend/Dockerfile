FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Place the virtualenv outside /app so a bind-mount of /app doesn't shadow it
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# Install dependencies before copying source (better layer caching)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application source
COPY . .

# Add venv binaries to PATH so uvicorn/celery are available without "uv run"
ENV PATH="/opt/venv/bin:$PATH"

EXPOSE 8000
