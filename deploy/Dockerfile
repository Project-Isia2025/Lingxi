# Phase 7 指南规范 Campaign API 镜像
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FFMPEG_PATH=/usr/bin/ffmpeg \
    VIDEO_OUTPUT_DIR=/app/data/output/videos

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml requirements.txt ./
RUN pip install --upgrade pip \
    && (pip install -e . || pip install -r requirements.txt)

COPY . .

RUN mkdir -p /app/data/output/videos /app/data/state /app/data/db

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "api.routes:app", "--host", "0.0.0.0", "--port", "8000"]
