FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    KLINK_DATABASE=/data/klink.db \
    PORT=5000

WORKDIR /app

# sqlite3 (CLI) é usado pela tarefa agendada de backup do DEPLOY.md — sem ele
# instalado, o backup falharia em silêncio todo dia.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY app.py ./
COPY klink ./klink
COPY templates ./templates
COPY static ./static
COPY supabase ./supabase

RUN mkdir -p /data \
    && groupadd --system klink \
    && useradd --system --gid klink --home-dir /app klink \
    && chown -R klink:klink /app /data

USER klink

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:5000/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--worker-class", "gthread", "--workers", "1", "--threads", "8", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
