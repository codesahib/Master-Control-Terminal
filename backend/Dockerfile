FROM python:3.12-slim

WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["sh", "-c", "if [ \"${RUN_MIGRATIONS_ON_STARTUP:-0}\" = \"1\" ]; then alembic upgrade head; fi; exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
