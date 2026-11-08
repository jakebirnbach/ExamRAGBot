# API server with both local models built in, so starting it downloads nothing.
FROM python:3.12-slim

ENV UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    HF_HOME=/models \
    PATH=/app/.venv/bin:$PATH

RUN pip install --no-cache-dir "uv>=0.11.16,<0.12" \
    && useradd --create-home app \
    && mkdir -p /app /models \
    && chown app:app /app /models

WORKDIR /app
USER app

# Dependencies first, so changing the code doesn't reinstall them or download the models again.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

# Download the models before copying the code, so a code change doesn't download 6 GB again.
# Full snapshots, as the loaders expect: with files missing (BGE-M3's unused 2.2 GB ONNX export,
# say), the offline loader raises IncompleteSnapshotError and the server won't start.
# Keep these names in step with EMBEDDING_MODEL / RERANKER_MODEL in config.py.
RUN python -c "from huggingface_hub import snapshot_download; \
snapshot_download('BAAI/bge-m3'); snapshot_download('BAAI/bge-reranker-v2-m3')"

# From here on, a missing model file is an error rather than a surprise download.
ENV HF_HUB_OFFLINE=1 \
    API_HOST=0.0.0.0

COPY src ./src
RUN uv sync --frozen --no-dev

# Load both models offline, exactly as the app does, so a missing file fails the build.
RUN python -c "from study_assistant.infrastructure.config import get_settings; \
from study_assistant.main import Container; \
Container(get_settings()).load_models()"

EXPOSE 8000

# The server only answers once the models are warm, hence the long start period.
HEALTHCHECK --interval=15s --timeout=5s --start-period=180s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

CMD ["study-assistant-api"]
