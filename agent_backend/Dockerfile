FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir . \
    && addgroup --system vinc \
    && adduser --system --ingroup vinc --home /home/vinc vinc

USER vinc

EXPOSE 8080

CMD ["sh", "-c", "exec gunicorn --bind :${PORT} --workers 1 --threads 8 --timeout 0 vinc_agent.cloud_run_app:app"]
